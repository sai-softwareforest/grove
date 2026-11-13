"""R-HOME-1, R-HOME-2: status says which data directory is in use and how it was chosen."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import TINY
from sf_grove.cli import main
from sf_grove.db import HOME_SOURCES
from sf_grove.service import Grove
from sf_grove.tools import TOOLS_BY_NAME, call_tool


def test_explicit_home_is_reported_as_flag(home: Path) -> None:
    with Grove(home) as grove:
        status = grove.status()
    assert status["home_source"] == "flag"
    assert status["data_dir"] == str(home.resolve())


def test_environment_home_is_reported_as_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROVE_HOME", str(tmp_path / "from-env"))
    with Grove() as grove:
        status = grove.status()
    assert status["home_source"] == "env"
    assert status["data_dir"] == str((tmp_path / "from-env").resolve())


def test_default_home_is_reported_as_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Point the user's home at a temporary directory, so the default never touches a real ~/.grove.
    monkeypatch.delenv("GROVE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    with Grove() as grove:
        status = grove.status()
    assert status["home_source"] == "default"
    assert status["data_dir"] == str((tmp_path / "user" / ".grove").resolve())


def test_empty_home_carries_a_hint_that_names_the_source(home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with Grove(home) as grove:
        empty = grove.status()
        assert empty["project_count"] == 0
        assert "wrong directory" in empty["hint"] and "--home flag" in empty["hint"]
        grove.project_create("tiny", str(TINY))
        used = grove.status()
        assert used["project_count"] == 1 and used["hint"] is None

    monkeypatch.setenv("GROVE_HOME", str(tmp_path / "from-env"))
    with Grove() as grove:
        assert "GROVE_HOME environment variable" in grove.status()["hint"]


def test_status_fields_are_stable_and_sources_are_a_closed_set(home: Path) -> None:
    with Grove(home) as grove:
        status = grove.status()
    assert list(status) == ["name", "version", "data_dir", "db_path", "home_source", "project_count", "hint"]
    assert status["home_source"] in HOME_SOURCES == ("flag", "env", "default")


def test_cli_and_mcp_tool_report_the_source(home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch) -> None:
    assert main(["--home", str(home), "status"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["home_source"] == "flag"

    monkeypatch.setenv("GROVE_HOME", str(tmp_path / "from-env"))
    assert main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["home_source"] == "env"

    # The MCP server passes on what --home was given (here: nothing), so the tool sees the environment.
    via_tool = call_tool(None, "grove_status", {})["data"]
    assert via_tool["home_source"] == "env" and via_tool["hint"]
    description = TOOLS_BY_NAME["grove_status"].description
    assert "home_source" in description and "hint" in description
