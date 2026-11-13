"""The repository's gates: the CI workflow, the publish check and the one
check script with its linter.

The workflow's rules are the acceptance criteria of WO-08 (R-QUAL-9). They
are checked as text, with the standard library, so that a later edit which
adds a secret, a floating action version or a pull-request value in a script
fails the suite before it reaches a public repository.

The publish check (R-SEC-6, R-INV-15) is run for real in a temporary
repository: a made-up token, a forbidden file name, a private path from a
local pattern file and an agent session link are each refused, and a clean
commit passes. The pre-push hook is run by a real `git push` to a bare
repository next to it, to show which commits of a push it checks (WO-26).
Every value the check looks for is put together when the test runs, so this
file holds none of them.

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

HOOKS = REPO / ".githooks"

needs_git = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("bash") is None, reason="the publish check needs git and bash"
)

# The tests' git reads no configuration of the machine it runs on: a signing
# key, a push default or a rewritten URL there must not decide a result.
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
GIT = ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false"]


def _git(repo: Path, *args: str) -> str:
    """Run git with no hook, and return what it printed."""
    command = [*GIT, "-c", "core.hooksPath=/dev/null", *args]
    done = subprocess.run(command, cwd=repo, env=GIT_ENV, check=True, capture_output=True, text=True, timeout=60)
    return done.stdout.strip()


def _commit_files(repo: Path, files: dict[str, str], message: str = "Add files") -> str:
    """Write the files, commit everything, and return the commit's id."""
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _commit(repo: Path, file_text: str, message: str) -> str:
    return _commit_files(repo, {"notes.md": file_text}, message)


def _check(repo: Path, revision: str = "HEAD") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(CHECK_PUBLISH), revision], cwd=repo, env=GIT_ENV, capture_output=True, text=True, timeout=60
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q", ".")
    return path


def _session_link() -> str:
    # Built here, so that this file never contains what the check looks for.
    return "https://claude.ai/code/" + "session" + "_01" + "ABCDEFGHJKMNPQRSTVWXYZ12"


def _fake_secrets() -> dict[str, str]:
    """One made-up value for every kind of secret the script names, by file name.

    Each is joined here from a prefix and a filler, so that no line of this
    file is something the check refuses. None was ever a real credential.
    """
    filler = "0aB1" * 10
    return {
        "github-classic.txt": "ghp_" + filler,
        "github-fine-grained.txt": "github_pat_" + filler,
        "github-oauth.txt": "gho_" + filler,
        "github-user.txt": "ghu_" + filler,
        "github-server.txt": "ghs_" + filler,
        "stripe-secret-live.txt": "sk_live_" + filler,
        "stripe-secret-test.txt": "sk_test_" + filler,
        "stripe-restricted-live.txt": "rk_live_" + filler,
        "stripe-restricted-test.txt": "rk_test_" + filler,
        "stripe-webhook.txt": "whsec_" + filler,
        "slack.txt": "xoxb-" + "1234-" + filler,
        "aws-key-id.txt": "AKIA" + "ABCDEFGH12345678",
        "aws-temporary-key-id.txt": "ASIA" + "ABCDEFGH12345678",
        "google-api.txt": "AIza" + "0aB1_-x" * 5,
        "private-key.txt": "-----BEGIN " + "PRIVATE KEY-----",
        "private-key-rsa.txt": "-----BEGIN " + "RSA PRIVATE KEY-----",
        "xai.txt": "xai-" + filler,
        "anthropic.txt": "sk-ant-" + filler,
        "openai-project.txt": "sk-proj-" + filler,
        "postgres.txt": "postgres://" + "grove:made-up@db.example.invalid/grove",
        "mysql.txt": "mysql://" + "grove:made-up@db.example.invalid/grove",
        "mongodb.txt": "mongodb://" + "grove:made-up@db.example.invalid/grove",
        "mongodb-srv.txt": "mongodb+srv://" + "grove:made-up@db.example.invalid/grove",
    }


def _fake_token() -> str:
    return _fake_secrets()["github-classic.txt"]


@needs_git
def test_the_publish_check_passes_a_clean_commit(repo: Path) -> None:
    _commit(repo, "A session of work, session_notes and a short session_id=7 are all fine.\n", "Add notes")
    done = _check(repo)
    assert done.returncode == 0, done.stdout + done.stderr


@needs_git
def test_the_publish_check_passes_text_and_file_names_that_only_resemble_a_finding(repo: Path) -> None:
    files = {
        # Prose about secrets, and addresses without a password.
        "notes.md": "A GitHub token starts with ghp_ and an AWS key id with AKIA; sk-ant is a prefix too.\n"
        "The database is at postgres://db.example.invalid:5432/grove and needs no password here.\n"
        "BEGIN PRIVATE KEY is what a key file starts with.\n",
        # Names that contain a forbidden name without being one.
        "environment.md": "Variables.\n",
        "keys.md": "Which keys exist.\n",
        "docs/database.md": "The schema.\n",
        "claude/notes.md": "Not the settings directory.\n",
        "scripts/check-publish.local.example": "# /path/to/your-machine/\n",
    }
    _commit_files(repo, files, "Add documents about keys and databases")
    done = _check(repo)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout == "check-publish: HEAD is clean.\n"


@needs_git
def test_the_publish_check_refuses_every_kind_of_planted_token(repo: Path) -> None:
    secrets = _fake_secrets()
    _commit_files(repo, {name: f"value: {secret}\n" for name, secret in secrets.items()}, "Add settings")
    done = _check(repo)
    assert done.returncode == 1
    assert "secret-like content in HEAD:" in done.stdout
    missed = [name for name in secrets if f"HEAD:{name}:1:" not in done.stdout]
    assert not missed, f"not refused: {missed}"
    assert "is clean" not in done.stdout and "check-publish: failed." in done.stderr


@needs_git
def test_the_publish_check_refuses_a_token_in_the_commit_message(repo: Path) -> None:
    _commit(repo, "Nothing private here.\n", f"Add notes\n\nTried with {_fake_token()} first.")
    done = _check(repo)
    assert done.returncode == 1
    assert "commit message of HEAD" in done.stdout and "secret-like content in HEAD:" not in done.stdout


# Every name the script forbids, at the top and in a directory. One name is
# not ASCII: git quotes such a name in a plain listing, and the check once
# read the quoted form, which ends in a quote and not in ".pem".
FORBIDDEN_FILES = (
    ".env",
    ".env.production",
    "deploy/.env",
    "server.pem",
    "schlüssel.pem",
    "deploy/id.key",
    "credentials.json",
    "deploy/credentials.json",
    "grove.db",
    "grove.db-wal",
    "grove.db-shm",
    "cache.sqlite",
    "cache.sqlite3",
    "grove-data/grove.txt",
    ".claude/settings.json",
    "LOCAL.md",
    "scripts/check-publish.local",
)


@needs_git
def test_the_publish_check_refuses_every_forbidden_file_name(repo: Path) -> None:
    _commit_files(repo, {name: "Nothing private in the text itself.\n" for name in FORBIDDEN_FILES}, "Add files")
    done = _check(repo)
    assert done.returncode == 1
    lines = done.stdout.splitlines()
    missed = [name for name in FORBIDDEN_FILES if f"forbidden file in HEAD: {name}" not in lines]
    assert not missed, f"not refused: {missed}"


def _write_local_patterns(repo: Path, text: str) -> None:
    """Give the repository a pattern file that git does not track, as Grove's `.gitignore` does."""
    (repo / ".git" / "info" / "exclude").write_text("scripts/check-publish.local\n", encoding="utf-8")
    (repo / "scripts").mkdir(exist_ok=True)
    (repo / "scripts" / "check-publish.local").write_text(text, encoding="utf-8")


@needs_git
def test_the_publish_check_refuses_a_private_path_named_in_the_local_pattern_file(repo: Path) -> None:
    _commit(repo, "The data directory is /made-up/private-place/grove on that machine.\n", "Add notes")
    # Without the pattern file nothing says the path is private.
    done = _check(repo)
    assert done.returncode == 0, done.stdout + done.stderr
    _write_local_patterns(repo, "/made-up/private-place/\n")
    done = _check(repo)
    assert done.returncode == 1
    assert "private path pattern found in HEAD:" in done.stdout and "HEAD:notes.md:1:" in done.stdout


@needs_git
def test_the_local_pattern_file_holds_fixed_strings_comments_and_blank_lines(repo: Path) -> None:
    _write_local_patterns(
        repo,
        "# Private places on this machine.\n"
        "\n"
        "   /made-up/private-place/   # spaces around it, and a comment after it\n"
        "-dashed-place/\n"
        "v1.2+x\n",
    )
    lines = [
        "one: /made-up/private-place/grove",
        "two: -dashed-place/grove",
        "three: v1.2+x",
        # Matches "v1.2+x" read as an expression, and must not: a pattern is a fixed string.
        "four: v1a22x",
        "five: # Private places on this machine.",
    ]
    _commit(repo, "\n".join(lines) + "\n", "Add notes")
    done = _check(repo)
    assert done.returncode == 1
    found = sorted(set(re.findall(r"^HEAD:notes\.md:(\d):", done.stdout, flags=re.MULTILINE)))
    assert found == ["1", "2", "3"], done.stdout


@needs_git
def test_the_publish_check_fails_on_a_revision_that_does_not_exist(repo: Path) -> None:
    _commit(repo, "Nothing private here.\n", "Add notes")
    done = _check(repo, "no-such-revision")
    assert done.returncode == 1
    assert "is clean" not in done.stdout and "Nothing was checked" in done.stderr


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
# .githooks/pre-push: which commits of a push are checked (WO-26)


def _add_remote(repo: Path, tmp_path: Path, name: str = "origin") -> Path:
    """A bare repository next to the working one, registered as a remote."""
    path = tmp_path / f"{name}.git"
    path.mkdir()
    _git(path, "init", "-q", "--bare", ".")
    _git(repo, "remote", "add", name, str(path))
    return path


def _install_the_check(repo: Path) -> str:
    """The hook runs the repository's own copy of the script; commit one."""
    (repo / "scripts").mkdir(exist_ok=True)
    shutil.copy(CHECK_PUBLISH, repo / "scripts" / "check-publish")
    (repo / "scripts" / "check-publish").chmod(0o755)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "Add the publish check")
    return _git(repo, "rev-parse", "HEAD")


def _push(repo: Path, *refspecs: str, remote: str = "origin") -> subprocess.CompletedProcess[str]:
    """`git push` with Grove's hook directory, as a clone set up per the brief has it."""
    command = [*GIT, "-c", f"core.hooksPath={HOOKS}", "push", remote, *refspecs]
    return subprocess.run(command, cwd=repo, env=GIT_ENV, capture_output=True, text=True, timeout=60)


def _push_without_the_hook(repo: Path, *refspecs: str, remote: str = "origin") -> None:
    _git(repo, "push", "-q", remote, *refspecs)


def _checked(done: subprocess.CompletedProcess[str]) -> list[str]:
    """The commits the hook passed, in the order it checked them."""
    return re.findall(r"^check-publish: ([0-9a-f]{40,64}) is clean\.$", done.stdout + done.stderr, flags=re.MULTILINE)


def _remote_branch(remote: Path, branch: str) -> str:
    """The commit the remote has for the branch, or "" when it has none."""
    return _git(remote, "for-each-ref", "--format=%(objectname)", f"refs/heads/{branch}")


@needs_git
@pytest.mark.parametrize("branch_is_new", [False, True], ids=["update", "new-branch"])
def test_the_hook_refuses_a_push_whose_earlier_commit_holds_a_token(repo: Path, tmp_path: Path, branch_is_new: bool) -> None:
    remote = _add_remote(repo, tmp_path)
    _install_the_check(repo)
    if not branch_is_new:
        done = _push(repo, "HEAD:refs/heads/topic")
        assert done.returncode == 0, done.stdout + done.stderr
    before = _remote_branch(remote, "topic")
    _commit(repo, "A first step.\n", "First step")
    leak = _commit(repo, f"token: {_fake_token()}\n", "Second step")
    _commit(repo, "The token is gone again.\n", "Third step")
    # The tip alone is clean; it is all the hook looked at before WO-26.
    assert _check(repo).returncode == 0

    done = _push(repo, "HEAD:refs/heads/topic")
    assert done.returncode != 0
    output = done.stdout + done.stderr
    assert "secret-like content in" in output
    assert f"pre-push: blocked HEAD: commit {leak} would be published and does not pass." in output
    assert _remote_branch(remote, "topic") == before


@needs_git
def test_the_hook_checks_the_new_commits_only_each_once_oldest_first(repo: Path, tmp_path: Path) -> None:
    _add_remote(repo, tmp_path)
    _install_the_check(repo)
    # Published earlier, without the hook: a token and its removal. They are
    # on the remote; refusing a later push would take nothing back.
    _commit(repo, f"token: {_fake_token()}\n", "Leak")
    _commit(repo, "The token is gone again.\n", "Remove it")
    _push_without_the_hook(repo, "HEAD:refs/heads/main")

    new = [_commit(repo, f"Step {number}.\n", f"Step {number}") for number in (1, 2, 3)]
    done = _push(repo, "HEAD:refs/heads/main")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _checked(done) == new
    assert "pre-push: HEAD: new commits checked: 3." in done.stdout + done.stderr

    # A new branch: git gives a remote sha of zeros. What the remote has on
    # another branch is not checked again.
    extra = _commit(repo, "Step 4.\n", "Step 4")
    done = _push(repo, "HEAD:refs/heads/topic")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _checked(done) == [extra]

    # A second name for a commit the remote has: nothing new to check.
    done = _push(repo, "HEAD:refs/heads/same")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _checked(done) == [] and "new commits checked: 0." in done.stdout + done.stderr


@needs_git
def test_the_hook_skips_a_deletion_and_checks_every_other_ref_of_the_push(repo: Path, tmp_path: Path) -> None:
    remote = _add_remote(repo, tmp_path)
    _install_the_check(repo)
    _push_without_the_hook(repo, "HEAD:refs/heads/old", "HEAD:refs/heads/one")
    new = _commit(repo, "A step.\n", "A step")

    done = _push(repo, ":refs/heads/old", "HEAD:refs/heads/one", "HEAD:refs/heads/two")
    assert done.returncode == 0, done.stdout + done.stderr
    # Once for the updated branch and once for the new one; never for the deleted one.
    assert _checked(done) == [new, new]
    assert (done.stdout + done.stderr).count("new commits checked: 1.") == 2
    assert _remote_branch(remote, "old") == ""
    assert _remote_branch(remote, "one") == new and _remote_branch(remote, "two") == new


@needs_git
def test_the_hook_refuses_the_whole_push_when_one_of_its_refs_fails(repo: Path, tmp_path: Path) -> None:
    remote = _add_remote(repo, tmp_path)
    base = _install_the_check(repo)
    _push_without_the_hook(repo, "HEAD:refs/heads/main")
    leak = _commit(repo, f"token: {_fake_token()}\n", "Leak")
    _git(repo, "branch", "leak")
    _git(repo, "reset", "-q", "--hard", base)
    _commit(repo, "Nothing private here.\n", "A clean step")

    done = _push(repo, "HEAD:refs/heads/main", "leak:refs/heads/leak")
    assert done.returncode != 0
    assert f"pre-push: blocked refs/heads/leak: commit {leak}" in done.stdout + done.stderr
    assert _remote_branch(remote, "main") == base and _remote_branch(remote, "leak") == ""


@needs_git
def test_the_hook_treats_a_remote_sha_it_does_not_have_like_a_new_branch(repo: Path, tmp_path: Path) -> None:
    remote = _add_remote(repo, tmp_path)
    _install_the_check(repo)
    _push_without_the_hook(repo, "HEAD:refs/heads/topic")
    new = _commit(repo, "A step.\n", "A step")
    # What git sends when someone else has pushed to the branch since the last fetch.
    line = f"refs/heads/topic {new} refs/heads/topic {'1' * len(new)}\n"
    done = subprocess.run(
        ["bash", str(HOOKS / "pre-push"), "origin", str(remote)], input=line, cwd=repo, env=GIT_ENV, capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert _checked(done) == [new]


@needs_git
def test_the_hook_checks_a_commit_that_only_another_remote_has(repo: Path, tmp_path: Path) -> None:
    remote = _add_remote(repo, tmp_path)
    _add_remote(repo, tmp_path, "backup")
    _install_the_check(repo)
    _push_without_the_hook(repo, "HEAD:refs/heads/topic")
    leak = _commit(repo, f"token: {_fake_token()}\n", "Leak")
    _commit(repo, "The token is gone again.\n", "Remove it")
    # On a private remote already; that does not make it public on this one.
    _push_without_the_hook(repo, "HEAD:refs/heads/topic", remote="backup")
    before = _remote_branch(remote, "topic")

    done = _push(repo, "HEAD:refs/heads/topic")
    assert done.returncode != 0
    assert f"commit {leak} would be published" in done.stdout + done.stderr
    assert _remote_branch(remote, "topic") == before


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
CHECK_NEEDS = ("bash", "git", "mktemp", "rm", "grep")
needs_check_tools = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in CHECK_NEEDS), reason="scripts/check needs " + ", ".join(CHECK_NEEDS)
)


def _run_check(
    repo: Path, tmp_path: Path, *, shellcheck: bool, fail: str = "nothing", caller_has_a_home: bool = True
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
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
    if not caller_has_a_home:
        del env["GROVE_HOME"]
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
def test_the_check_script_gives_the_tests_a_home_when_the_caller_has_none(repo: Path, tmp_path: Path) -> None:
    done, calls = _run_check(repo, tmp_path, shellcheck=False, caller_has_a_home=False)
    assert done.returncode == 0, done.stdout + done.stderr
    _, home, was_a_directory = calls[1].split(" | ")
    assert was_a_directory == "yes" and not Path(home).exists()


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
