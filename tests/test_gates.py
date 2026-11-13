"""The repository's gates: the CI workflow, the publish check and the one
check script with its linter.

The workflow's rules are the acceptance criteria of WO-08 (R-QUAL-9). They
are checked as text, with the standard library, so that a later edit which
adds a secret, a floating action version or a pull-request value in a script
fails the suite before it reaches a public repository.

The publish check (R-SEC-6, R-INV-15) is run for real in a temporary
repository. Only the session-id rule is covered here; tokens, file names and
private paths are WO-26.

`scripts/check` (R-QUAL-8, WO-12) is run for real too, in a temporary
repository with stand-ins for `uv` and `shellcheck` on a search path that
holds nothing else it does not need, so the test neither starts the suite
inside itself nor depends on what the machine has installed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from conftest import REPO

WORKFLOWS = REPO / ".github" / "workflows"
CHECK_PUBLISH = REPO / "scripts" / "check-publish"
CHECK = REPO / "scripts" / "check"
# First-party actions, plus the uv installer (WO-08, rule 4).
ALLOWED_ACTION_OWNERS = {"actions", "astral-sh"}


def _code_lines(text: str) -> list[str]:
    """The workflow without comments and blank lines."""
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def test_there_is_one_workflow_with_one_job() -> None:
    assert [path.name for path in WORKFLOWS.iterdir()] == ["ci.yml"]
    lines = _code_lines((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
    jobs = lines[lines.index("jobs:") + 1 :]
    assert [line for line in jobs if re.match(r"^  \S", line)] == ["  test:"]


def test_the_workflow_runs_on_pull_requests_and_main_with_a_read_only_token() -> None:
    lines = _code_lines((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
    triggers = lines[lines.index("on:") + 1 : lines.index("permissions:")]
    assert triggers == ["  pull_request:", "  push:", "    branches: [main]"]
    # The only permissions block is the top-level one, and it grants one read scope.
    assert [line for line in lines if "permissions" in line] == ["permissions:"]
    assert lines[lines.index("permissions:") + 1 : lines.index("jobs:")] == ["  contents: read"]


def test_the_workflow_expands_no_expression_and_names_no_secret() -> None:
    code = "\n".join(_code_lines((WORKFLOWS / "ci.yml").read_text(encoding="utf-8")))
    # No "${{ ... }}" at all: nothing from a pull request (a title, a branch
    # name) can be pasted into a script, and no secret can be referenced.
    assert "${{" not in code
    assert "pull_request_target" not in code
    assert "secrets" not in code.lower()


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    lines = _code_lines((WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
    uses = [line.split("uses:", 1)[1].split("#", 1)[0].strip() for line in lines if "uses:" in line]
    assert len(uses) == 2, uses
    for action in uses:
        match = re.fullmatch(r"([\w.-]+)/[\w./-]+@[0-9a-f]{40}", action)
        assert match, f"{action} is not pinned to a full commit SHA"
        assert match.group(1) in ALLOWED_ACTION_OWNERS, action


def test_the_workflow_runs_the_locked_install_the_linter_the_tests_and_the_publish_check() -> None:
    code = "\n".join(_code_lines((WORKFLOWS / "ci.yml").read_text(encoding="utf-8")))
    steps = ["uv sync --locked", "uv run ruff check", "uv run pytest -q", "scripts/check-publish"]
    positions = [code.find(step) for step in steps]
    assert all(position >= 0 for position in positions) and positions == sorted(positions), positions


# --------------------------------------------------------------------------
# scripts/check-publish

needs_git = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None, reason="the publish check needs git and bash"
)


def _git(repo: Path, *args: str) -> None:
    command = ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false"]
    subprocess.run([*command, "-c", "core.hooksPath=/dev/null", *args], cwd=repo, check=True, capture_output=True, timeout=60)


def _commit(repo: Path, file_text: str, message: str) -> None:
    (repo / "notes.md").write_text(file_text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _check(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(CHECK_PUBLISH), "HEAD"], cwd=repo, capture_output=True, text=True, timeout=60)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", ".")
    return path


def _session_link() -> str:
    # Built here, so that this file never contains what the check looks for.
    return "https://claude.ai/code/" + "session" + "_01" + "ABCDEFGHJKMNPQRSTVWXYZ12"


@needs_git
def test_the_publish_check_passes_a_clean_commit(repo: Path) -> None:
    _commit(repo, "A session of work, session_notes and a short session_id=7 are all fine.\n", "Add notes")
    done = _check(repo)
    assert done.returncode == 0, done.stdout + done.stderr


@needs_git
def test_the_publish_check_refuses_a_session_link_in_a_file(repo: Path) -> None:
    _commit(repo, f"See {_session_link()} for how this was made.\n", "Add notes")
    done = _check(repo)
    assert done.returncode == 1
    assert "agent session id" in done.stdout and "notes.md" in done.stdout


@needs_git
def test_the_publish_check_refuses_a_session_link_in_the_commit_message(repo: Path) -> None:
    _commit(repo, "Nothing private here.\n", f"Add notes\n\nClaude-Session: {_session_link()}")
    done = _check(repo)
    assert done.returncode == 1
    assert "commit message" in done.stdout



# --------------------------------------------------------------------------
# The linter and scripts/check (R-QUAL-8)


def test_the_linter_is_pinned_and_selects_error_class_rules_only() -> None:
    pyproject = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    pins = [entry for entry in pyproject["dependency-groups"]["dev"] if entry.startswith("ruff")]
    assert len(pins) == 1 and re.fullmatch(r"ruff==\d+\.\d+\.\d+", pins[0]), pins
    # The whole configuration: pyflakes rules (undefined and unused names,
    # unused imports) and nothing else. A style rule, an ignore list or a
    # formatter setting is a decision for WO-12's debate, not an edit.
    assert pyproject["tool"]["ruff"] == {"lint": {"select": ["F"]}}
    # The linter is a development tool; it never becomes a runtime dependency (R-INV-14).
    assert not [entry for entry in pyproject["project"]["dependencies"] if entry.startswith("ruff")]


def test_the_check_script_lints_every_bash_file() -> None:
    listed = re.search(r"^SHELL_FILES=\((.*)\)$", CHECK.read_text(encoding="utf-8"), flags=re.MULTILINE)
    assert listed, "scripts/check no longer has a SHELL_FILES line"
    bash_files = sorted(
        path.relative_to(REPO).as_posix()
        for directory in (REPO / "scripts", REPO / ".githooks")
        for path in directory.iterdir()
        if path.is_file() and path.read_bytes().startswith(b"#!/usr/bin/env bash")
    )
    assert sorted(listed.group(1).split()) == bash_files


# What scripts/check and scripts/check-publish need besides uv and shellcheck.
CHECK_NEEDS = ("bash", "git", "mktemp", "rm", "basename", "grep")
needs_check_tools = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in CHECK_NEEDS), reason="scripts/check needs " + ", ".join(CHECK_NEEDS)
)


def _run_check(repo: Path, tmp_path: Path, *, shellcheck: bool, fail: str = "nothing") -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run scripts/check in a copy of the two scripts, with stand-ins on the path.

    The stand-ins log their arguments and whether GROVE_HOME is a directory;
    one whose arguments contain the word `fail` exits 1.
    """
    scripts = repo / "scripts"
    scripts.mkdir()
    for script in (CHECK, CHECK_PUBLISH):
        shutil.copy(script, scripts / script.name)
        (scripts / script.name).chmod(0o755)
    _commit(repo, "Nothing private here.\n", "Add the scripts")

    tools = tmp_path / "tools"
    tools.mkdir()
    for tool in CHECK_NEEDS:
        (tools / tool).symlink_to(shutil.which(tool))
    log = tmp_path / "calls.log"
    for stub in ("uv", "shellcheck") if shellcheck else ("uv",):
        (tools / stub).write_text(
            f"#!{shutil.which('bash')}\n"
            f"is_dir=no; [[ -d \"${{GROVE_HOME:-}}\" ]] && is_dir=yes\n"
            f"echo \"{stub} $* | ${{GROVE_HOME:-}} | $is_dir\" >> \"$STUB_LOG\"\n"
            f'case " $* " in *" $STUB_FAIL "*) exit 1 ;; esac\n',
            encoding="utf-8",
        )
        (tools / stub).chmod(0o755)
    env = {"PATH": str(tools), "HOME": str(tmp_path), "GROVE_HOME": os.environ["GROVE_HOME"], "STUB_LOG": str(log), "STUB_FAIL": fail}
    done = subprocess.run(["bash", "scripts/check"], cwd=repo, env=env, capture_output=True, text=True, timeout=60)
    return done, log.read_text(encoding="utf-8").splitlines()


@needs_check_tools
def test_the_check_script_runs_the_four_checks_in_order(repo: Path, tmp_path: Path) -> None:
    done, calls = _run_check(repo, tmp_path, shellcheck=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert [call.split(" | ")[0] for call in calls] == [
        "uv run ruff check",
        "shellcheck scripts/check scripts/check-publish .githooks/pre-push",
        "uv run pytest -q",
    ]
    assert "check-publish: HEAD is clean." in done.stdout
    summary = done.stdout.split("== summary\n", 1)[1].splitlines()
    assert summary == ["passed   linter", "passed   shell linter", "passed   tests", "passed   publish check", "check: all checks passed."]
    # The tests ran with a data directory of their own, which is gone afterwards.
    _, home, was_a_directory = calls[2].split(" | ")
    assert was_a_directory == "yes" and home != os.environ["GROVE_HOME"]
    assert not Path(home).exists()


@needs_check_tools
def test_the_check_script_says_when_the_shell_linter_is_skipped(repo: Path, tmp_path: Path) -> None:
    done, calls = _run_check(repo, tmp_path, shellcheck=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert [call.split(" | ")[0] for call in calls] == ["uv run ruff check", "uv run pytest -q"]
    assert "skipped  shell linter (shellcheck is not installed)" in done.stdout.splitlines()


@needs_check_tools
@pytest.mark.parametrize("fail,step", [("ruff", "linter"), ("scripts/check", "shell linter"), ("pytest", "tests")])
def test_the_check_script_fails_when_one_check_fails_and_still_runs_the_rest(repo: Path, tmp_path: Path, fail: str, step: str) -> None:
    done, calls = _run_check(repo, tmp_path, shellcheck=True, fail=fail)
    assert done.returncode == 1
    assert len(calls) == 3 and "check-publish: HEAD is clean." in done.stdout
    summary = done.stdout.split("== summary\n", 1)[1].splitlines()
    assert [line for line in summary if not line.startswith("passed")] == [f"FAILED   {step}"]
    assert "check: failed." in done.stderr


@needs_check_tools
def test_the_check_script_fails_when_the_publish_check_fails(repo: Path, tmp_path: Path) -> None:
    (repo / "leak.md").write_text(f"See {_session_link()}.\n", encoding="utf-8")
    done, _ = _run_check(repo, tmp_path, shellcheck=True)
    assert done.returncode == 1
    assert "FAILED   publish check" in done.stdout.splitlines()
