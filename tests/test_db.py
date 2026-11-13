"""Storage: WAL, forward-only migrations, concurrent first open."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conftest import TINY
from sf_grove import db
from sf_grove.db import MIGRATIONS, connect, enable_wal
from sf_grove.errors import GroveError
from sf_grove.service import Grove


def test_database_is_wal_and_migrated(home: Path) -> None:
    conn = connect(home)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")}
        assert {"projects", "blueprint_items", "findings", "knowledge", "knowledge_fts", "work_items"} <= tables
    finally:
        conn.close()
    assert sorted(path.name for path in home.iterdir() if path.suffix == ".db") == ["grove.db"]


def test_reopening_keeps_data_and_does_not_rerun_migrations(home: Path) -> None:
    with Grove(home) as grove:
        grove.project_create("tiny", str(TINY))
        grove.knowledge_write(None, "note", "Note", "kept")
    with Grove(home) as grove:
        assert grove.status()["project_count"] == 1
        assert grove.knowledge_get("note")["body"] == "kept"


def test_a_newer_schema_is_refused_not_downgraded(home: Path) -> None:
    connect(home).close()
    raw = sqlite3.connect(home / "grove.db")
    raw.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    raw.close()
    with pytest.raises(GroveError) as raised:
        connect(home)
    assert raised.value.code == "io"


def test_concurrent_first_open_and_writes(home: Path) -> None:
    errors: list[BaseException] = []
    barrier = threading.Barrier(8)

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            with Grove(home) as grove:
                for revision in range(5):
                    grove.knowledge_write(None, "shared", "Shared", f"writer {index} revision {revision}")
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not errors, errors
    with Grove(home) as grove:
        latest = grove.knowledge_get("shared")
        assert latest["revision"] == 40  # every write got its own revision; none was overwritten
        revisions = [grove.knowledge_get("shared", revision=number)["revision"] for number in range(1, 41)]
        assert revisions == list(range(1, 41))


def test_installed_console_script_speaks_the_envelope(home: Path) -> None:
    script = Path(sys.executable).parent / "grove"
    command = [str(script)] if script.exists() else [sys.executable, "-m", "sf_grove.cli"]
    good = subprocess.run(command + ["--home", str(home), "status"], capture_output=True, text=True, timeout=30)
    assert good.returncode == 0 and '"ok": true' in good.stdout and good.stderr == ""
    bad = subprocess.run(command + ["--home", str(home), "project", "get", "nope"], capture_output=True, text=True, timeout=30)
    assert bad.returncode == 1 and '"code": "not_found"' in bad.stdout


def test_a_version_1_database_is_upgraded_in_place(home: Path) -> None:
    from sf_grove.db import _split_statements

    home.mkdir(parents=True)
    raw = sqlite3.connect(home / "grove.db")
    for statement in _split_statements(MIGRATIONS[0]):
        raw.execute(statement)
    raw.execute("PRAGMA user_version = 1")
    raw.execute("INSERT INTO projects (name, root_path, created_at) VALUES ('old', '/tmp', '2026-01-01T00:00:00Z')")
    raw.execute(
        "INSERT INTO work_items (project_id, title, created_at, updated_at) VALUES (1, 'Old item', 'x', 'x')"
    )
    raw.execute("INSERT INTO knowledge (key, title, body, revision, created_at) VALUES ('n', 'N', 'old body', 1, 'x')")
    raw.commit()
    raw.close()

    with Grove(home) as grove:
        assert grove.work_get(1)["author"] is None
        assert grove.knowledge_get("n")["author"] is None
        assert grove.project_get("old")["findings_cap"]["applied"] is False
        assert grove.knowledge_search("old")["total"] == 1
    conn = connect(home)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    finally:
        conn.close()


def _database_at(home: Path, version: int) -> sqlite3.Connection:
    """A database built by the first ``version`` migrations only, as an older Grove left it."""
    from sf_grove.db import _split_statements

    home.mkdir(parents=True)
    raw = sqlite3.connect(home / "grove.db")
    for script in MIGRATIONS[:version]:
        for statement in _split_statements(script):
            raw.execute(statement)
    raw.execute(f"PRAGMA user_version = {version}")
    return raw


def test_a_version_2_database_gains_the_exclude_list(home: Path, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "vendor").mkdir(parents=True)
    (root / "README.md").write_text("# Proj\n\nParses a config file.\n")
    (root / "vendor" / "zork.py").write_text("def zork():\n    pass\n")
    old_report = '{"caps": {"hit": []}, "files_seen": 2, "warnings": []}'  # a version 2 report has no "excluded"
    raw = _database_at(home, 2)
    raw.execute(
        "INSERT INTO projects (name, root_path, created_at, last_scanned_at, last_scan) "
        "VALUES ('old', ?, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', ?)",
        (str(root), old_report),
    )
    raw.execute(
        "INSERT INTO work_items (project_id, title, created_at, updated_at, author) VALUES (1, 'Old item', 'x', 'x', 'ana')"
    )
    raw.commit()
    raw.close()

    with Grove(home) as grove:
        # Old rows read as before; the old report is passed through unchanged.
        project = grove.project_get("old")
        assert project["last_scanned_at"] == "2026-01-02T00:00:00Z" and project["last_scan"]["files_seen"] == 2
        assert "excluded" not in project["last_scan"]
        assert grove.work_get(1)["author"] == "ana"
        assert grove.conn.execute("SELECT exclude FROM projects WHERE name = 'old'").fetchone()[0] is None
        # No list is stored for an upgraded project until a scan sets one.
        assert grove.scan("old")["excluded"] == {"patterns": [], "files": 0}
        assert grove.scan("old", exclude=["vendor/"])["excluded"] == {"patterns": ["vendor/"], "files": 1}
        assert grove.conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_a_version_3_database_gains_the_work_history(home: Path) -> None:
    raw = _database_at(home, 3)
    raw.execute("INSERT INTO projects (name, root_path, created_at) VALUES ('old', '/nowhere', '2026-01-01T00:00:00Z')")
    raw.execute(
        "INSERT INTO work_items (project_id, title, status, notes, created_at, updated_at, author) "
        "VALUES (1, 'Old item', 'in_progress', 'old notes', 'x', 'x', 'ana')"
    )
    raw.commit()
    raw.close()

    with Grove(home) as grove:
        # Old rows read as before. Nothing is invented for the time before the history existed.
        old = grove.work_get(1)
        assert (old["status"], old["notes"], old["author"]) == ("in_progress", "old notes", "ana")
        assert old["history"] == {"total": 0, "events": []}
        grove.work_update(1, status="review", note="picked up after the upgrade", author="sam")
        event = grove.work_get(1)["history"]["events"][0]
        assert (event["old_status"], event["new_status"], event["author"]) == ("in_progress", "review", "sam")
        assert grove.conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_a_version_4_database_gains_the_references(home: Path) -> None:
    raw = _database_at(home, 4)
    raw.execute("INSERT INTO projects (name, root_path, created_at) VALUES ('old', '/nowhere', '2026-01-01T00:00:00Z')")
    raw.execute(
        "INSERT INTO work_items (project_id, title, status, notes, created_at, updated_at, author) "
        "VALUES (1, 'Old item', 'in_progress', 'old notes', 'x', 'x', 'ana')"
    )
    raw.execute(
        "INSERT INTO work_events (work_item_id, created_at, author, old_status, new_status, note) "
        "VALUES (1, 'x', 'ana', 'ready', 'in_progress', 'started before the upgrade')"
    )
    raw.commit()
    raw.close()

    with Grove(home) as grove:
        # Old rows read as before: an item without references, an event that changed none.
        old = grove.work_get(1)
        assert (old["status"], old["notes"], old["author"], old["refs"]) == ("in_progress", "old notes", "ana", [])
        assert old["history"]["total"] == 1
        event = old["history"]["events"][0]
        assert (event["note"], event["author"], event["refs"]) == ("started before the upgrade", "ana", None)
        assert grove.work_list("old")["items"][0]["refs"] == []
        assert grove.work_list("old", ref="R-HOME-2")["total"] == 0
        # Nothing is invented for the old item; it takes references like a new one.
        assert grove.work_update(1, refs=["R-HOME-2"], author="sam")["refs"] == ["R-HOME-2"]
        assert grove.work_list("old", ref="R-HOME-2")["total"] == 1
        newest = grove.work_get(1)["history"]["events"][0]
        assert (newest["author"], newest["refs"], newest["note"]) == ("sam", ["R-HOME-2"], None)
        assert grove.conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) == 5


def _schema(home: Path) -> dict:
    conn = sqlite3.connect(home / "grove.db")
    try:
        objects = conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name").fetchall()
        tables = [row[1] for row in objects if row[0] == "table"]
        return {
            "user_version": conn.execute("PRAGMA user_version").fetchone()[0],
            "objects": objects,
            "columns": {table: conn.execute(f"PRAGMA table_info({table})").fetchall() for table in tables},
        }
    finally:
        conn.close()


def test_a_database_migrated_step_by_step_has_the_schema_of_a_fresh_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect(tmp_path / "fresh").close()

    # Open the same home with one more migration each time, as successive Grove versions would.
    stepped = tmp_path / "stepped"
    for count in range(1, len(MIGRATIONS) + 1):
        monkeypatch.setattr(db, "MIGRATIONS", MIGRATIONS[:count])
        conn = connect(stepped)
        try:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == count
            if count == 1:
                conn.execute("INSERT INTO projects (name, root_path, created_at) VALUES ('first', '/nowhere', 'x')")
        finally:
            conn.close()
    monkeypatch.setattr(db, "MIGRATIONS", MIGRATIONS)

    assert _schema(stepped) == _schema(tmp_path / "fresh")
    assert _schema(stepped)["user_version"] == len(MIGRATIONS)
    with Grove(stepped) as grove:  # a row written at version 1 is still there, readable by today's code
        assert grove.project_get("first")["root_path"] == "/nowhere"


# -- concurrent first open (R-HOME-8) --------------------------------------------


class _LockedThenFree:
    """Stands in for a connection whose journal-mode switch meets a lock a few times."""

    def __init__(self, failures: int, message: str = "database is locked") -> None:
        self.failures = failures
        self.message = message
        self.calls: list[str] = []

    def execute(self, sql: str):
        self.calls.append(sql)
        if self.failures > 0:
            self.failures -= 1
            raise sqlite3.OperationalError(self.message)
        return None


def test_the_switch_to_wal_is_retried_while_the_file_is_locked() -> None:
    conn = _LockedThenFree(failures=3)
    enable_wal(conn, retry_seconds=5.0)  # type: ignore[arg-type]
    assert conn.calls == ["PRAGMA journal_mode = WAL"] * 4


def test_the_retry_gives_up_after_its_budget_and_does_not_hide_other_errors() -> None:
    stuck = _LockedThenFree(failures=10**9)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        enable_wal(stuck, retry_seconds=0.05)  # type: ignore[arg-type]
    assert len(stuck.calls) >= 2

    broken = _LockedThenFree(failures=1, message="disk I/O error")
    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        enable_wal(broken, retry_seconds=5.0)  # type: ignore[arg-type]
    assert broken.calls == ["PRAGMA journal_mode = WAL"]


def test_many_fresh_homes_survive_a_concurrent_first_open(tmp_path: Path) -> None:
    # Before the retry, about one fresh home in 25 failed here with "database is locked".
    for run in range(60):
        home = tmp_path / f"home-{run}"
        errors: list[BaseException] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            try:
                barrier.wait(timeout=10)
                connect(home).close()
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert not errors, (run, errors)
