"""SQLite storage: one database file, WAL mode, FTS5, forward-only migrations."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .errors import GroveError

DB_FILENAME = "grove.db"
HOME_ENV = "GROVE_HOME"
HOME_SOURCES = ("flag", "env", "default")
# How long opening a database keeps retrying the switch to WAL while another
# connection holds the file (the same budget as the busy timeout).
LOCK_RETRY_SECONDS = 5.0

# Forward-only. Never edit a migration that has shipped; append a new one.
# PRAGMA user_version records how many entries of this list have been applied.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE projects (
        id              INTEGER PRIMARY KEY,
        name            TEXT NOT NULL UNIQUE,
        root_path       TEXT NOT NULL,
        created_at      TEXT NOT NULL,
        last_scanned_at TEXT,
        last_scan       TEXT            -- JSON summary of the last scan, including caps hit
    );

    CREATE TABLE blueprint_items (
        id          INTEGER PRIMARY KEY,
        project_id  INTEGER NOT NULL REFERENCES projects(id),
        layer       TEXT NOT NULL CHECK (layer IN ('declared', 'actual', 'tests')),
        title       TEXT NOT NULL,
        body        TEXT NOT NULL DEFAULT '',
        source_path TEXT,
        source_line INTEGER,
        origin      TEXT NOT NULL DEFAULT 'scan' CHECK (origin IN ('scan', 'map')),
        origin_ref  TEXT,               -- knowledge key of the map for origin = 'map'
        extra       TEXT                -- JSON
    );
    CREATE INDEX blueprint_items_project ON blueprint_items(project_id, layer, id);

    CREATE TABLE findings (
        id          INTEGER PRIMARY KEY,
        project_id  INTEGER NOT NULL REFERENCES projects(id),
        kind        TEXT NOT NULL,
        summary     TEXT NOT NULL,
        evidence    TEXT NOT NULL DEFAULT '{}',   -- JSON
        confidence  TEXT NOT NULL DEFAULT 'heuristic',
        origin      TEXT NOT NULL DEFAULT 'scan' CHECK (origin IN ('scan', 'map')),
        origin_ref  TEXT,
        created_at  TEXT NOT NULL
    );
    CREATE INDEX findings_project ON findings(project_id, kind, id);

    CREATE TABLE knowledge (
        id          INTEGER PRIMARY KEY,
        project_id  INTEGER REFERENCES projects(id),  -- NULL for workspace-level notes
        key         TEXT NOT NULL,
        title       TEXT NOT NULL,
        body        TEXT NOT NULL,
        revision    INTEGER NOT NULL,
        created_at  TEXT NOT NULL
    );
    CREATE UNIQUE INDEX knowledge_key_revision
        ON knowledge(COALESCE(project_id, 0), key, revision);

    CREATE VIRTUAL TABLE knowledge_fts USING fts5(
        title, body,
        content = 'knowledge', content_rowid = 'id',
        tokenize = 'porter unicode61'
    );
    CREATE TRIGGER knowledge_ai AFTER INSERT ON knowledge BEGIN
        INSERT INTO knowledge_fts(rowid, title, body) VALUES (new.id, new.title, new.body);
    END;
    CREATE TRIGGER knowledge_ad AFTER DELETE ON knowledge BEGIN
        INSERT INTO knowledge_fts(knowledge_fts, rowid, title, body)
        VALUES ('delete', old.id, old.title, old.body);
    END;

    CREATE TABLE work_items (
        id          INTEGER PRIMARY KEY,
        project_id  INTEGER NOT NULL REFERENCES projects(id),
        title       TEXT NOT NULL,
        issue_url   TEXT,               -- stored as text only; Grove never fetches it
        status      TEXT NOT NULL DEFAULT 'ready'
                    CHECK (status IN ('ready', 'in_progress', 'review', 'done', 'blocked')),
        plan        TEXT NOT NULL DEFAULT '',
        notes       TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    CREATE INDEX work_items_project ON work_items(project_id, status, id);
    """,
    """
    ALTER TABLE projects ADD COLUMN findings_cap TEXT;   -- JSON: what a findings cap left out, per kind
    ALTER TABLE work_items ADD COLUMN author TEXT;       -- optional short name; NULL when none was given
    ALTER TABLE knowledge ADD COLUMN author TEXT;
    """,
    """
    ALTER TABLE projects ADD COLUMN exclude TEXT;        -- JSON list of gitignore-style patterns; NULL when none
    """,
    """
    CREATE TABLE work_events (
        id            INTEGER PRIMARY KEY,
        work_item_id  INTEGER NOT NULL REFERENCES work_items(id),
        created_at    TEXT NOT NULL,
        author        TEXT,               -- NULL when none was given
        old_status    TEXT NOT NULL,      -- the item's status before the update
        new_status    TEXT NOT NULL,      -- and after it; the same when only a note was added
        note          TEXT                -- NULL when the update carried none
    );
    CREATE INDEX work_events_item ON work_events(work_item_id, id);
    """,
    """
    ALTER TABLE findings ADD COLUMN key TEXT;            -- stable across rescans; see finding_key. Filled in the same transaction
    CREATE INDEX findings_key ON findings(project_id, key);
    """,
    """
    CREATE TABLE prism_lessons (
        key         TEXT PRIMARY KEY,   -- 12 hex digits of a SHA-256 over the normalised link; see prism.lesson_key
        title       TEXT NOT NULL,      -- the text as the lesson was first seen; never updated
        summary     TEXT NOT NULL DEFAULT '',
        source_url  TEXT NOT NULL,      -- stored as text only; Grove never fetches it
        source_list TEXT NOT NULL,      -- LIST:LINE
        tags        TEXT NOT NULL DEFAULT '[]',   -- JSON list
        origin      TEXT NOT NULL CHECK (origin IN ('seed', 'refresh'))
    );

    CREATE TABLE prism_events (
        id          INTEGER PRIMARY KEY,
        key         TEXT NOT NULL REFERENCES prism_lessons(key),
        event       TEXT NOT NULL CHECK (event IN ('added', 'retired', 'revived', 'changed')),
        source_ref  TEXT,               -- the commit of the copy that was read, 'seed', or NULL
        at          TEXT NOT NULL,
        title       TEXT,               -- the lesson's text from this event on; NULL when the event changes no text
        summary     TEXT,
        source_list TEXT,
        tags        TEXT
    );
    CREATE INDEX prism_events_key ON prism_events(key, id);
    """,
    """
    CREATE TABLE prism_touch (
        project_id       INTEGER NOT NULL REFERENCES projects(id),
        key              TEXT NOT NULL REFERENCES prism_lessons(key),
        fingerprint      TEXT NOT NULL,   -- JSON: what the lesson rests on in this project, part by part, at the last scan
        changed_at       TEXT,            -- when a scan last found it different; NULL when it never did
        changed          TEXT,            -- JSON list: the parts that differed then
        verdict_revision INTEGER,         -- the revision of the lesson's verdict at that moment; 0 when it had none
        PRIMARY KEY (project_id, key)
    );
    """,
]

FINDING_KEY_CHARS = 12
DECLARED_FINDING_KINDS = ("declared_untested", "declared_unseen")


def finding_key(*parts: str | None) -> str:
    """The stable reference of a finding: the first 12 hex digits of a SHA-256 over its inputs.

    The inputs are joined with a NUL, so no two different lists of inputs
    read as the same text. Which inputs a kind uses is decided in
    :func:`assign_finding_keys`.
    """
    joined = "\0".join(part or "" for part in parts)
    return hashlib.sha256(joined.encode("utf-8", errors="replace")).hexdigest()[:FINDING_KEY_CHARS]


def normalise_key_text(text: str | None) -> str:
    """Lower case, with every run of whitespace as one space."""
    return " ".join((text or "").lower().split())


def assign_finding_keys(conn: sqlite3.Connection, project_id: int | None = None) -> None:
    """Give every finding of a project (or of every project) its ``key``. Call inside a write transaction.

    The inputs, by kind:

    * ``declared_untested`` and ``declared_unseen``: kind, source path, and the
      normalised title of the linked blueprint item (``evidence.item_ids[0]``);
    * ``actual_undocumented``: kind and ``evidence.paths[0]``;
    * ``map_untested``: kind, the map's knowledge key and the normalised block text.

    A key never takes the source line, an item id or the summary: those move
    when a line is inserted above the statement, and the key must not. Findings
    of one project with the same inputs are told apart in source order: the
    first keeps the plain key, the next ones get ``#2``, ``#3``, ...

    The migration that added the column and every later write of findings go
    through this one function, so an upgraded row and a fresh one get the same key.
    """
    sql = (
        "SELECT f.id, f.project_id, f.kind, f.key, i.id AS item_id, i.title AS item_title, "
        "json_extract(f.evidence, '$.source_path') AS source_path, "
        "json_extract(f.evidence, '$.paths[0]') AS path, "
        "json_extract(f.evidence, '$.knowledge_key') AS knowledge_key, "
        "json_extract(f.evidence, '$.text') AS text "
        "FROM findings f LEFT JOIN blueprint_items i "
        "ON i.id = json_extract(f.evidence, '$.item_ids[0]') AND i.project_id = f.project_id"
    )
    params: tuple[int, ...] = ()
    if project_id is not None:
        sql += " WHERE f.project_id = ?"
        params = (project_id,)
    rows = []
    # Read by position: a migration may run on a connection without a row factory.
    for finding_id, project, kind, stored, item_id, item_title, source_path, path, knowledge_key, text in conn.execute(
        sql, params
    ).fetchall():
        position = 0
        if kind in DECLARED_FINDING_KINDS:
            base = finding_key(kind, source_path, normalise_key_text(item_title))
            position = item_id or 0  # items are stored in source order
        elif kind == "actual_undocumented":
            base = finding_key(kind, path)
        elif kind == "map_untested":
            base = finding_key(kind, knowledge_key, normalise_key_text(text))
        else:
            base = finding_key(kind, source_path)
        rows.append((project, base, position, finding_id, stored))
    rows.sort(key=lambda entry: entry[:4])
    changed: list[tuple[str, int]] = []
    previous: tuple[int, str] | None = None
    count = 0
    for project, base, _position, finding_id, stored in rows:
        count = count + 1 if (project, base) == previous else 1
        previous = (project, base)
        key = base if count == 1 else f"{base}#{count}"
        if key != stored:
            changed.append((key, finding_id))
    conn.executemany("UPDATE findings SET key = ? WHERE id = ?", changed)


# Work a migration needs that SQL cannot do, by the schema version it leads
# to. It runs in the migration's own transaction, right after its statements.
# Like a shipped migration, a shipped entry is never edited.
MIGRATION_STEPS: dict[int, Callable[[sqlite3.Connection], None]] = {5: assign_finding_keys}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_home_source(home: str | os.PathLike[str] | None = None) -> tuple[Path, str]:
    """The data directory and how it was chosen.

    An explicit home wins (source ``flag``), then $GROVE_HOME (``env``), then
    ~/.grove (``default``).
    """
    if home:
        return Path(home).expanduser().resolve(), "flag"
    env = os.environ.get(HOME_ENV)
    if env:
        return Path(env).expanduser().resolve(), "env"
    return (Path.home() / ".grove").resolve(), "default"


def resolve_home(home: str | os.PathLike[str] | None = None) -> Path:
    """Explicit home wins, then $GROVE_HOME, then ~/.grove."""
    return resolve_home_source(home)[0]


def db_path(home: Path) -> Path:
    return home / DB_FILENAME


def connect(home: Path) -> sqlite3.Connection:
    """Open the database under ``home``, creating and migrating it as needed."""
    try:
        home.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path(home), timeout=5.0, isolation_level=None)
    except (OSError, sqlite3.Error) as exc:
        raise GroveError("io", f"cannot open the Grove database under {home}: {exc}") from exc
    try:
        conn.row_factory = sqlite3.Row
        enable_wal(conn)
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        migrate(conn)
    except sqlite3.Error as exc:
        conn.close()
        raise GroveError("io", f"cannot prepare the Grove database under {home}: {exc}") from exc
    except GroveError:
        conn.close()
        raise
    return conn


def connect_read_only(home: Path) -> sqlite3.Connection:
    """Open the database under ``home`` for reading only (``mode=ro``): for ``grove view``.

    Nothing is created and nothing is migrated. A data directory without a
    database is ``not_found``; a database of another schema version is ``io``,
    with the remedy, because a reader cannot upgrade it.
    """
    path = db_path(home)
    if not path.is_file():
        raise GroveError(
            "not_found",
            f"no Grove database under {home}; check the data directory with `grove status` (--home or GROVE_HOME)",
        )
    try:
        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5.0, isolation_level=None)
    except (OSError, sqlite3.Error) as exc:
        raise GroveError("io", f"cannot open the Grove database under {home} for reading: {exc}") from exc
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        current = conn.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error as exc:
        conn.close()
        raise GroveError("io", f"cannot read the Grove database under {home}: {exc}") from exc
    if current != len(MIGRATIONS):
        conn.close()
        raise GroveError(
            "io",
            f"database schema version {current} is not the version this Grove reads ({len(MIGRATIONS)}), and a "
            "read-only connection cannot upgrade it; run `grove status` once with this Grove (or upgrade Grove)",
        )
    return conn


def enable_wal(conn: sqlite3.Connection, retry_seconds: float = LOCK_RETRY_SECONDS) -> None:
    """Switch the database to WAL, retrying while another connection holds the file.

    Changing the journal mode needs an exclusive lock, and SQLite reports a
    conflict on it at once instead of waiting for the busy timeout. Without the
    retry, several processes opening a fresh data directory together fail now
    and then with "database is locked".
    """
    deadline = time.monotonic() + retry_seconds
    delay = 0.005
    while True:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" not in message and "busy" not in message:
                raise
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 0.1)


def migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > len(MIGRATIONS):
        raise GroveError(
            "io",
            f"database schema version {current} is newer than this Grove understands "
            f"({len(MIGRATIONS)}); upgrade Grove rather than downgrading the data",
        )
    if current == len(MIGRATIONS):
        return
    # Take the write lock before re-reading the version, so two processes that
    # start together cannot both apply the same migration.
    conn.execute("BEGIN IMMEDIATE")
    try:
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for index in range(current, len(MIGRATIONS)):
            for statement in _split_statements(MIGRATIONS[index]):
                conn.execute(statement)
            step = MIGRATION_STEPS.get(index + 1)
            if step:
                step(conn)
            conn.execute(f"PRAGMA user_version = {index + 1}")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _split_statements(script: str) -> list[str]:
    """Split a migration into statements, keeping CREATE TRIGGER ... END; whole.

    ``executescript`` would commit the surrounding transaction, so migrations
    are run statement by statement instead.
    """
    statements: list[str] = []
    buffer: list[str] = []
    in_trigger = False
    for raw in script.splitlines():
        line = raw.split("--", 1)[0].rstrip()
        if not line.strip():
            continue
        buffer.append(line)
        upper = line.strip().upper()
        if upper.startswith("CREATE TRIGGER"):
            in_trigger = True
        if in_trigger:
            if upper == "END;":
                in_trigger = False
                statements.append("\n".join(buffer))
                buffer = []
        elif upper.endswith(";"):
            statements.append("\n".join(buffer))
            buffer = []
    if buffer:
        statements.append("\n".join(buffer))
    return statements
