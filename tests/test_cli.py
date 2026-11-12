"""The CLI: JSON envelope on stdout, exit 0 or 1, --home beats GROVE_HOME."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import MAP_SAMPLE, TINY, tree_snapshot
from sf_grove.cli import main


@pytest.fixture
def cli(home: Path, capsys: pytest.CaptureFixture[str]):
    def invoke(*args: str, expect: int = 0, with_home: bool = True) -> dict:
        argv = (["--home", str(home)] if with_home else []) + list(args)
        code = main(argv)
        captured = capsys.readouterr()
        assert code == expect, captured.out
        envelope = json.loads(captured.out)
        assert envelope["ok"] is (expect == 0)
        return envelope["data"] if expect == 0 else envelope["error"]

    return invoke


def test_first_walk(cli, home: Path, tmp_path: Path) -> None:
    before = tree_snapshot(TINY)
    assert cli("status")["project_count"] == 0
    assert cli("project", "create", "tiny", "--root", str(TINY))["root_path"] == str(TINY.resolve())
    assert cli("project", "list")["total"] == 1
    assert cli("project", "get", "tiny")["last_scanned_at"] is None

    scanned = cli("scan", "tiny")
    assert scanned["findings"]["declared_untested"] >= 1
    assert cli("blueprint", "tiny", "--layer", "tests")["total"] == 2
    gaps = cli("gaps", "tiny", "--kind", "declared_untested")
    assert any("greet" in finding["summary"].lower() for finding in gaps["items"])
    assert cli("recommend", "tiny")["finding"]["kind"] == "declared_untested"

    assert cli("ingest-map", "tiny", str(MAP_SAMPLE))["knowledge"]["key"] == "map_sample"
    assert cli("recommend", "tiny")["finding"]["kind"] == "map_untested"

    note = tmp_path / "note.md"
    note.write_text("Greeting tests live in tests/test_greet.py once written.\n")
    assert cli("knowledge", "write", "tiny", "--key", "greet-plan", "--title", "Greet plan", "--file", str(note))["revision"] == 1
    assert cli("knowledge", "write", "tiny", "--key", "greet-plan", "--title", "Greet plan", "--file", str(note))["revision"] == 2
    assert cli("knowledge", "get", "greet-plan")["revision"] == 2
    assert cli("knowledge", "write", "-", "--key", "shared", "--title", "Shared", "--file", str(note))["project"] is None
    assert {hit["key"] for hit in cli("search", "greeting")["items"]} >= {"greet-plan", "shared"}

    work = cli("work", "create", "tiny", "--title", "Test greet", "--issue", "https://example.invalid/1")
    assert work["status"] == "ready"
    assert cli("work", "update", str(work["id"]), "--status", "in_progress")["status"] == "in_progress"
    assert cli("work", "list", "tiny")["items"][0]["status"] == "in_progress"
    assert cli("work", "get", str(work["id"]))["issue_url"] == "https://example.invalid/1"

    assert cli("project", "get", "tiny")["counts"]["work_items"]["in_progress"] == 1
    assert tree_snapshot(TINY) == before
    assert (home / "grove.db").exists()


def test_errors_exit_1_with_an_envelope(cli) -> None:
    assert cli("project", "get", "missing", expect=1)["code"] == "not_found"
    assert cli("scan", "missing", expect=1)["code"] == "not_found"
    assert cli("project", "create", "x", "--root", "/definitely/not/here", expect=1)["code"] == "invalid"
    assert cli("work", "update", "1", "--status", "done", expect=1)["code"] == "not_found"
    # Usage mistakes are envelopes too, not argparse's exit code 2.
    assert cli("no-such-command", expect=1)["code"] == "invalid"
    assert cli("project", "create", expect=1)["code"] == "invalid"
    assert cli(expect=1)["code"] == "invalid"
    assert cli("blueprint", "x", "--layer", "nonsense", expect=1)["code"] == "invalid"


def test_home_flag_beats_environment(cli, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_home = tmp_path / "env-home"
    monkeypatch.setenv("GROVE_HOME", str(env_home))
    assert cli("status", with_home=False)["data_dir"] == str(env_home.resolve())
    assert cli("status")["data_dir"] == str(home.resolve())
    # --home is accepted after the command as well.
    assert cli("status", "--home", str(tmp_path / "late"), with_home=False)["data_dir"] == str((tmp_path / "late").resolve())


def test_paging_limits(cli) -> None:
    cli("project", "create", "tiny", "--root", str(TINY))
    cli("scan", "tiny")
    assert cli("blueprint", "tiny", "--limit", "500")["limit"] == 200
    assert cli("blueprint", "tiny")["limit"] == 50
    assert cli("blueprint", "tiny", "--limit", "0", expect=1)["code"] == "invalid"
    assert cli("blueprint", "tiny", "--offset", "-1", expect=1)["code"] == "invalid"
    page = cli("blueprint", "tiny", "--limit", "2", "--offset", "3")
    assert (page["limit"], page["offset"], len(page["items"])) == (2, 3, 2)


def test_text_mode_is_not_json(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--home", str(home), "--text", "status"]) == 0
    out = capsys.readouterr().out
    assert "version: " in out and not out.lstrip().startswith("{")
    assert main(["--home", str(home), "project", "get", "missing", "--text"]) == 1
    assert capsys.readouterr().out.startswith("error [not_found]")
