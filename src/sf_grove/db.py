"""SQLite storage: one database file, WAL mode, FTS5, forward-only migrations."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .errors import GroveError

DB_FILENAME = "grove.db"

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
]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_home(home: str | os.PathLike[str] | None = None) -> Path:
    """Explicit home wins, then $GROVE_HOME, then ~/.grove."""
    if home:
        return Path(home).expanduser().resolve()
    env = os.environ.get("GROVE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / ".grove").resolve()


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
        conn.execute("PRAGMA journal_mode = WAL")
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
