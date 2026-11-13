"""The repository's two gates: the CI workflow and the publish check.

The workflow's rules are the acceptance criteria of WO-08 (R-QUAL-9). They
are checked as text, with the standard library, so that a later edit which
adds a secret, a floating action version or a pull-request value in a script
fails the suite before it reaches a public repository.

The publish check (R-SEC-6, R-INV-15) is run for real in a temporary
repository. Only the session-id rule is covered here; tokens, file names and
private paths are WO-26.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import REPO

WORKFLOWS = REPO / ".github" / "workflows"
CHECK_PUBLISH = REPO / "scripts" / "check-publish"
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


def test_the_workflow_runs_the_locked_install_the_tests_and_the_publish_check() -> None:
    code = "\n".join(_code_lines((WORKFLOWS / "ci.yml").read_text(encoding="utf-8")))
    steps = ["uv sync --locked", "uv run pytest -q", "scripts/check-publish"]
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

