"""Storage: WAL, forward-only migrations, concurrent first open."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conftest import TINY
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
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) == 2
    finally:
        conn.close()


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
