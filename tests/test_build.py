"""R-GROK-9: `status` names the running build, on both surfaces.

The build is the version and, when Grove runs from a git checkout, the commit
of the source. The commit is read from git's own files, because Grove starts
no process; here it is compared with what git itself reports, in temporary
repositories. Three things are shown besides: an installed copy and a
directory that is no checkout report the version alone and never fail; a
process that is still running after its checkout moved on keeps the commit
it started from; and no value of the field can be a path.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO
from sf_grove import BUILD, COMMIT_CHARS, __version__, read_commit
from sf_grove.cli import main
from sf_grove.tools import call_tool
from test_gates import GIT, GIT_ENV

PACKAGE = REPO / "src" / "sf_grove"
A, B = "a" * 40, "b" * 40


def assert_build_shape(build: object) -> None:
    """`version` always, `commit` after it or not at all; a commit is hexadecimal digits and nothing else."""
    assert isinstance(build, dict)
    assert list(build) in (["version"], ["version", "commit"])
    assert build["version"] == __version__
    if "commit" in build:
        assert re.fullmatch(r"[0-9a-f]{%d}" % COMMIT_CHARS, build["commit"]), build
    # Neither value can be a path, whatever the machine: no separator is among the characters allowed.
    assert re.fullmatch(r"[0-9A-Za-z.+!-]+", build["version"]), build


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run([*GIT, *args], cwd=repo, env=GIT_ENV, check=True, capture_output=True, text=True, timeout=60)
    return done.stdout.strip()


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", f"--short={COMMIT_CHARS}", "HEAD")


def _repository(root: Path) -> Path:
    root.mkdir(parents=True)
    _git(root, "init", "--quiet", "--initial-branch=main")
    return root


def _commit(repo: Path, message: str) -> str:
    _git(repo, "commit", "--quiet", "--allow-empty", "-m", message)
    return _head(repo)


def test_status_names_the_build_on_both_surfaces(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--home", str(home), "status"]) == 0
    by_cli = json.loads(capsys.readouterr().out)["data"]
    by_tool = call_tool(str(home), "grove_status", {})["data"]
    for status in (by_cli, by_tool):
        assert_build_shape(status["build"])
        assert status["build"] == BUILD and status["build"]["version"] == status["version"]
        # The paths of a status are in data_dir and db_path, and nowhere in the build.
        text = json.dumps(status["build"])
        assert "/" not in text and "\\" not in text
        assert str(REPO) not in text and str(home) not in text
    # The tests run from this repository's source, so the build is the one this checkout gives.
    commit = read_commit(REPO)
    assert BUILD == ({"version": __version__, "commit": commit} if commit else {"version": __version__})

    assert main(["--home", str(home), "--text", "status"]) == 0
    assert "build:\n  version: " in capsys.readouterr().out


def test_status_hands_out_a_copy_of_the_build(home: Path) -> None:
    before = dict(BUILD)
    call_tool(str(home), "grove_status", {})["data"]["build"]["commit"] = "changed by a caller"
    assert BUILD == before == call_tool(str(home), "grove_status", {})["data"]["build"]


def test_the_commit_is_the_one_git_reports(tmp_path: Path) -> None:
    repo = _repository(tmp_path / "repo")
    assert read_commit(repo) is None, "a branch without a commit has no commit to report"

    first = _commit(repo, "one")
    assert len(first) == COMMIT_CHARS and read_commit(repo) == first  # a branch, kept as a file of its own
    _git(repo, "pack-refs", "--all")
    assert not (repo / ".git" / "refs" / "heads" / "main").exists()
    assert read_commit(repo) == first  # the same branch, listed in packed-refs
    second = _commit(repo, "two")
    assert second != first and read_commit(repo) == second  # the file of its own wins over the stale list
    _git(repo, "checkout", "--quiet", "--detach", first)
    assert read_commit(repo) == first  # no branch at all
    _git(repo, "checkout", "--quiet", "main")

    # A linked worktree: `.git` is a file, HEAD is its own, the branches are the main checkout's.
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "--quiet", "-b", "side", str(linked), first)
    assert (linked / ".git").is_file()
    assert read_commit(linked) == first and read_commit(repo) == second
    third = _commit(linked, "three")
    assert read_commit(linked) == third and read_commit(repo) == second
    _git(linked, "pack-refs", "--all")
    assert read_commit(linked) == third

    # The git directory kept elsewhere, as for a submodule.
    apart = tmp_path / "apart"
    apart.mkdir()
    _git(apart, "init", "--quiet", "--initial-branch=main", f"--separate-git-dir={tmp_path / 'apart.git'}")
    assert read_commit(apart) is None
    assert read_commit(apart) != _commit(apart, "four") and read_commit(apart) == _head(apart)


def _fake_checkout(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / ".git" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / ".git" / name).write_text(text, encoding="utf-8")
    return root


def test_a_commit_is_cut_to_twelve_digits_whatever_the_object_format(tmp_path: Path) -> None:
    assert COMMIT_CHARS == 12
    assert read_commit(_fake_checkout(tmp_path / "sha1", {"HEAD": "0123456789abcdef" * 2 + "01234567\n"})) == "0123456789ab"
    assert read_commit(_fake_checkout(tmp_path / "sha256", {"HEAD": "fedcba9876543210" * 4 + "\n"})) == "fedcba987654"
    # A symbolic ref may point at another one.
    chained = {"HEAD": "ref: refs/heads/alias\n", "refs/heads/alias": "ref: refs/heads/main\n", "refs/heads/main": B + "\n"}
    assert read_commit(_fake_checkout(tmp_path / "chained", chained)) == B[:12]


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"HEAD": ""},
        {"HEAD": "not a commit\n"},
        {"HEAD": A[:39] + "\n"},
        {"HEAD": A.upper() + "\n"},
        {"HEAD": A + "0\n"},
        {"HEAD": "ref: refs/heads/main\n"},
        {"HEAD": "ref: refs/heads/main\n", "refs/heads/main": "/path/to/grove\n"},
        {"HEAD": "ref: refs/heads/main\n", "packed-refs": f"{A} refs/heads/other\n^{B}\n"},
        {"HEAD": "ref: refs/heads/main\n", "packed-refs": "/path/to/grove refs/heads/main\n"},
        {"HEAD": "ref: refs/heads/.invalid\n", "reftable/tables.list": "0x000000000001-0x000000000002-abcdef.ref\n"},
        {"HEAD": "ref: refs/heads/a\n", "refs/heads/a": "ref: refs/heads/b\n", "refs/heads/b": "ref: refs/heads/a\n"},
        {"HEAD": "ref: refs/../../outside\n", "refs/heads/main": B + "\n", "../outside": A + "\n"},
        {"HEAD": "ref: outside\n", "outside": A + "\n"},
        {"HEAD": "/etc/hostname\n"},
        {"HEAD": "\x00\x01\x02 \udcff"},
    ],
    ids=[
        "empty-git-directory", "empty-head", "words", "too-short", "upper-case", "too-long", "branch-without-commit",
        "path-in-a-ref", "branch-not-in-packed-refs", "path-in-packed-refs", "reftable", "ref-loop", "ref-climbs-out",
        "ref-outside-refs", "path-in-head", "bytes",
    ],
)  # fmt: skip
def test_what_cannot_be_read_gives_no_commit_and_no_error(tmp_path: Path, files: dict[str, str]) -> None:
    root = tmp_path / "checkout"
    (root / ".git").mkdir(parents=True)
    for name, text in files.items():
        path = root / ".git" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8", errors="surrogateescape"))
    assert read_commit(root) is None


def test_a_directory_that_is_no_checkout_gives_no_commit_and_no_error(tmp_path: Path) -> None:
    assert read_commit(tmp_path) is None
    assert read_commit(tmp_path / "missing") is None
    assert read_commit("\x00") is None
    for pointer in ("", "somewhere else\n", "gitdir: missing\n", f"gitdir: {tmp_path / 'missing'}\n"):
        root = tmp_path / f"pointer-{len(pointer)}"
        root.mkdir()
        (root / ".git").write_text(pointer, encoding="utf-8")
        assert read_commit(root) is None, pointer
    unreadable = tmp_path / "head-is-a-directory"
    (unreadable / ".git" / "HEAD").mkdir(parents=True)
    assert read_commit(unreadable) is None


# A separate process that runs a copy of the package: it prints the status once
# through the CLI and, after one line arrives on its input, once through the
# MCP tool handler. So the second status is from a process that was running
# while the test changed the checkout.
_TWO_STATUSES = """
import json, sys
sys.path.insert(0, sys.argv[1])
import sf_grove
from sf_grove.cli import main
from sf_grove.tools import call_tool
assert sf_grove.__file__.startswith(sys.argv[1]), sf_grove.__file__
assert main(["--home", sys.argv[2], "status"]) == 0
sys.stdin.readline()
print(json.dumps(call_tool(sys.argv[2], "grove_status", {})), flush=True)
"""


class _Copy:
    """Grove's package copied to ``parent``, and processes that run that copy."""

    def __init__(self, parent: Path, home: Path) -> None:
        shutil.copytree(PACKAGE, parent / "sf_grove", ignore=shutil.ignore_patterns("__pycache__"))
        self.arguments = [sys.executable, "-c", _TWO_STATUSES, str(parent), str(home)]

    def start(self) -> subprocess.Popen[str]:
        return subprocess.Popen(self.arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    @staticmethod
    def build(process: subprocess.Popen[str], go_on: bool = False) -> dict:
        assert process.stdin is not None and process.stdout is not None and process.stderr is not None
        if go_on:
            process.stdin.write("\n")
            process.stdin.close()
        line = process.stdout.readline()
        if go_on:
            assert process.wait(timeout=60) == 0, process.stderr.read()
        envelope = json.loads(line or "null")
        assert envelope and envelope["ok"] is True, process.stderr.read()
        assert_build_shape(envelope["data"]["build"])
        return envelope["data"]["build"]

    def builds(self) -> tuple[dict, dict]:
        process = self.start()
        return self.build(process), self.build(process, go_on=True)


def test_a_running_process_keeps_the_commit_it_started_from(tmp_path: Path) -> None:
    checkout = _repository(tmp_path / "checkout")
    started_at = _commit(checkout, "the build that is started")
    (checkout / "src").mkdir()
    copy = _Copy(checkout / "src", tmp_path / "home")

    running = copy.start()
    assert copy.build(running) == {"version": __version__, "commit": started_at}  # the CLI
    upgraded_to = _commit(checkout, "the checkout moves on; the process is not restarted")
    assert upgraded_to != started_at
    assert copy.build(running, go_on=True) == {"version": __version__, "commit": started_at}  # the MCP tool

    # A process started now is the restarted connector: it reports the new commit on both surfaces.
    assert copy.builds() == ({"version": __version__, "commit": upgraded_to},) * 2


def test_an_installed_copy_reports_the_version_alone(tmp_path: Path) -> None:
    # A repository two levels up, where the package's own checkout would be: a
    # virtualenv inside some checkout looks like this. It is not Grove's source.
    around = _repository(tmp_path / "around")
    _commit(around, "another project")
    (around / "site-packages").mkdir()
    copy = _Copy(around / "site-packages", tmp_path / "home")
    assert copy.builds() == ({"version": __version__},) * 2


def test_source_that_is_not_in_a_git_checkout_reports_the_version_alone(tmp_path: Path) -> None:
    (tmp_path / "unpacked" / "src").mkdir(parents=True)
    copy = _Copy(tmp_path / "unpacked" / "src", tmp_path / "home")
    assert copy.builds() == ({"version": __version__},) * 2
