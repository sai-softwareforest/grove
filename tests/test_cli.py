"""The CLI: JSON envelope on stdout, exit 0 or 1, --home beats GROVE_HOME."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import MAP_SAMPLE, REPO, TINY, tree_snapshot
from sf_grove.cli import main
from sf_grove.service import MAX_TEXT_BYTES


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


def test_cli_author_and_full_flags(cli, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli("project", "create", "tiny", "--root", str(TINY))
    assert cli("work", "create", "tiny", "--title", "T", "--author", "ana")["author"] == "ana"
    assert cli("work", "create", "tiny", "--title", "U")["author"] is None
    monkeypatch.setenv("GROVE_AUTHOR", "sam")
    assert cli("work", "create", "tiny", "--title", "V")["author"] == "sam"

    note = tmp_path / "long.md"
    note.write_text("# Long\n\n" + "A sentence about the parser. " * 400)
    written = cli("knowledge", "write", "tiny", "--key", "long", "--title", "Long", "--file", str(note), "--author", "ana")
    assert written["author"] == "ana"
    excerpt = cli("knowledge", "get", "long")
    assert excerpt["excerpted"] is True and len(excerpt["body"]) < excerpt["body_chars"]
    whole = cli("knowledge", "get", "long", "--full")
    assert whole["excerpted"] is False and whole["body"] == note.read_text()


# -- WO-21: a note from standard input, an author on ingest-map, grove on PATH ----


@pytest.fixture
def stdin(monkeypatch: pytest.MonkeyPatch):
    """Give the next command these bytes on standard input, as a pipe would."""

    def give(data: bytes) -> None:
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))

    return give


def test_knowledge_write_reads_the_body_from_stdin(cli, stdin, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cli("project", "create", "tiny", "--root", str(TINY))
    body = "# Greet plan\n\nGrüße: tests live in tests/test_greet.py.\n  Indented last line, no newline at the end"
    stdin(body.encode("utf-8"))
    written = cli("knowledge", "write", "tiny", "--key", "greet-plan", "--title", "Greet plan", "--file", "-", "--author", "ana")
    assert (written["revision"], written["project"], written["author"]) == (1, "tiny", "ana")
    assert cli("knowledge", "get", "greet-plan", "--full")["body"] == body  # stored as piped, nothing stripped

    # Again adds a revision; NAME "-" (no project) and --file "-" (stdin) do not get in each other's way.
    stdin(b"second\n")
    assert cli("knowledge", "write", "tiny", "--key", "greet-plan", "--title", "Greet plan", "--file", "-")["revision"] == 2
    stdin(b"for every project\n")
    shared = cli("knowledge", "write", "-", "--key", "shared", "--title", "Shared", "--file", "-")
    assert (shared["project"], shared["revision"]) == (None, 1)
    assert cli("knowledge", "get", "shared")["body"] == "for every project\n"

    # Bytes that are not UTF-8 are replaced, as they are when read from a file.
    stdin(b"caf\xe9 au lait\n")
    cli("knowledge", "write", "-", "--key", "latin", "--title", "Latin", "--file", "-")
    assert cli("knowledge", "get", "latin")["body"] == "caf\ufffd au lait\n"

    assert not list(tmp_path.glob("*.md")) and not (tmp_path / "-").exists(), "no file is created for the body"


def test_stdin_that_gives_no_usable_body_is_an_error_and_writes_nothing(cli, stdin, monkeypatch: pytest.MonkeyPatch) -> None:
    def write() -> dict:
        return cli("knowledge", "write", "-", "--key", "k", "--title", "T", "--file", "-", expect=1)

    for nothing in (b"", b" \n\t\n"):
        stdin(nothing)
        error = write()
        assert error["code"] == "invalid" and "empty" in error["message"]

    monkeypatch.setattr(sys, "stdin", None)  # started with standard input closed
    assert write()["code"] == "invalid"

    # A terminal is refused at once: waiting for typed text would be a prompt (R-IF-9).
    class Terminal(io.TextIOWrapper):
        def isatty(self) -> bool:
            return True

    typed = Terminal(io.BytesIO(b"never read\n"), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", typed)
    error = write()
    assert error["code"] == "invalid" and "standard input" in error["message"] and "terminal" in error["message"]
    assert typed.buffer.tell() == 0, "nothing was read from the terminal"

    # The 2 MB cap on a text argument holds, and no more than the cap plus one byte is taken from the pipe.
    pipe = io.BytesIO(b"x" * (MAX_TEXT_BYTES + 4096))
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(pipe, encoding="utf-8"))
    error = write()
    assert error["code"] == "invalid" and str(MAX_TEXT_BYTES) in error["message"]
    assert pipe.tell() == MAX_TEXT_BYTES + 1

    class Broken(io.RawIOBase):
        def readable(self) -> bool:
            return True

        def readinto(self, buffer) -> int:
            raise OSError("the pipe broke")

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BufferedReader(Broken()), encoding="utf-8"))
    error = write()
    assert error["code"] == "io" and "standard input" in error["message"]

    assert cli("search")["total"] == 0  # none of the refused bodies was stored

    stdin(b"x" * MAX_TEXT_BYTES)  # exactly the cap is accepted
    assert cli("knowledge", "write", "-", "--key", "k", "--title", "T", "--file", "-")["revision"] == 1


def test_a_file_named_dash_is_still_reachable(cli, stdin, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "-").write_text("from the file named dash\n")
    stdin(b"from standard input\n")
    cli("knowledge", "write", "-", "--key", "dash", "--title", "Dash", "--file", "./-")
    assert cli("knowledge", "get", "dash")["body"] == "from the file named dash\n"
    # A missing file is still not_found; only a bare "-" means standard input.
    assert cli("knowledge", "write", "-", "--key", "x", "--title", "X", "--file", "./--", expect=1)["code"] == "not_found"


def _run(command: list[str], *, cwd: Path, env: dict[str, str], data: bytes | None = None) -> dict:
    done = subprocess.run(command, input=data, capture_output=True, cwd=cwd, env=env, timeout=60)
    assert done.returncode == 0, done.stdout.decode() + done.stderr.decode()
    envelope = json.loads(done.stdout)
    assert envelope["ok"] is True
    return envelope["data"]


def test_a_real_pipe_feeds_knowledge_write(home: Path, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = {**os.environ, "GROVE_HOME": str(home), "GROVE_AUTHOR": "piper"}
    grove = [sys.executable, "-m", "sf_grove.cli"]
    body = "Piped, not saved to a file first.\n".encode("utf-8") * 3
    written = _run(grove + ["knowledge", "write", "-", "--key", "piped", "--title", "Piped", "--file", "-"], cwd=elsewhere, env=env, data=body)
    assert (written["revision"], written["author"], written["body"]) == (1, "piper", body.decode("utf-8"))
    assert _run(grove + ["knowledge", "get", "piped"], cwd=elsewhere, env=env)["body"] == body.decode("utf-8")
    assert list(elsewhere.iterdir()) == [], "nothing is written where the command was started"

    # With nothing on standard input, the answer is still one envelope, not a hang or a traceback.
    command = grove + ["knowledge", "write", "-", "--key", "none", "--title", "None", "--file", "-"]
    done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, cwd=elsewhere, env=env, timeout=60)
    assert done.returncode == 1 and json.loads(done.stdout)["error"]["code"] == "invalid"


def test_ingest_map_takes_an_author(cli, monkeypatch: pytest.MonkeyPatch) -> None:
    cli("project", "create", "tiny", "--root", str(TINY))

    def author_of(revision: int) -> str | None:
        return cli("knowledge", "get", "map_sample", "--revision", str(revision))["author"]

    assert cli("ingest-map", "tiny", str(MAP_SAMPLE), "--author", "ana")["knowledge"]["revision"] == 1
    assert cli("ingest-map", "tiny", str(MAP_SAMPLE))["knowledge"]["revision"] == 2
    monkeypatch.setenv("GROVE_AUTHOR", "sam")
    cli("ingest-map", "tiny", str(MAP_SAMPLE))
    cli("ingest-map", "tiny", "--author", "ana", str(MAP_SAMPLE))  # the flag wins over the environment
    cli("ingest-map", "tiny", str(MAP_SAMPLE), "--author", " ")  # a blank name is no name: the environment applies
    assert [author_of(revision) for revision in (1, 2, 3, 4, 5)] == ["ana", None, "sam", "ana", "sam"]

    # A name Grove would not store is refused before anything is written.
    seeded = cli("blueprint", "tiny")["total"]
    for bad in ("x" * 65, "two\nlines"):
        assert cli("ingest-map", "tiny", str(MAP_SAMPLE), "--author", bad, expect=1)["code"] == "invalid"
    assert cli("search")["items"][0]["revision"] == 5 and cli("blueprint", "tiny")["total"] == seeded


def test_grove_runs_by_name_from_another_directory(home: Path, tmp_path: Path) -> None:
    """The README's way of putting `grove` on PATH: a link to the command that `uv sync` made (R-CC-5)."""
    script = Path(sys.executable).parent / "grove"
    if os.name == "nt" or not script.exists():
        pytest.skip("needs the grove command that `uv sync` installs next to the interpreter (not on Windows)")
    on_path = tmp_path / "bin"
    on_path.mkdir()
    (on_path / "grove").symlink_to(script)
    elsewhere = tmp_path / "another-repository"
    elsewhere.mkdir()
    env = {**os.environ, "PATH": f"{on_path}{os.pathsep}/usr/bin{os.pathsep}/bin", "GROVE_HOME": str(home)}
    env.pop("VIRTUAL_ENV", None)

    status = _run(["grove", "status"], cwd=elsewhere, env=env)
    assert status["data_dir"] == str(home.resolve()) and status["home_source"] == "env"
    _run(["grove", "project", "create", "tiny", "--root", str(TINY)], cwd=elsewhere, env=env)
    note = b"Written from another repository, with no file in it.\n"
    command = ["grove", "knowledge", "write", "tiny", "--key", "elsewhere", "--title", "Elsewhere", "--file", "-"]
    assert _run(command, cwd=elsewhere, env=env, data=note)["revision"] == 1
    assert _run(["grove", "search", "another repository"], cwd=elsewhere, env=env)["items"][0]["key"] == "elsewhere"
    assert list(elsewhere.iterdir()) == []

    # The README names this link; if the section goes, this test should go with it.
    section = (REPO / "README.md").read_text(encoding="utf-8").split("### `grove` from any directory", 1)[1].split("\n## ", 1)[0]
    assert "ln -s" in section and ".venv/bin/grove" in section and "~/.local/bin" in section
