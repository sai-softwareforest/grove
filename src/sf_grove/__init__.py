"""Grove: a local workshop for mapping a codebase and tracking work toward a reviewed change."""

from __future__ import annotations

import os
import re
from pathlib import Path

__version__ = "0.1.0"

# The build id that `status` reports (R-GROK-9): the version, and the commit
# of the source when Grove runs from a git checkout. The commit is read from
# git's own files, because Grove starts no process (R-SEC-1), and it is cut
# to COMMIT_CHARS hexadecimal digits: `git rev-parse --short=12 HEAD`.
COMMIT_CHARS = 12
_OBJECT_NAME = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")  # SHA-1, or SHA-256
_GIT_FILE_BYTES = 8192  # HEAD, a ref, `commondir` and a `gitdir:` pointer are each one short line
_SYMBOLIC_REF_HOPS = 5


def _first_line(path: Path) -> str:
    """The first line of one of git's small text files; empty when it cannot be read."""
    try:
        with path.open("rb") as handle:
            data = handle.read(_GIT_FILE_BYTES)
    except OSError:
        return ""
    return os.fsdecode(data.split(b"\n", 1)[0]).strip()


def _packed_ref(common: Path, name: str) -> str:
    """The object a ref points to according to ``packed-refs``; empty when it is not listed."""
    try:
        with (common / "packed-refs").open("rb") as handle:
            for raw in handle:
                value, _, ref = os.fsdecode(raw).strip().partition(" ")
                if ref == name:
                    return value
    except OSError:
        pass
    return ""


def _read_commit(root: Path) -> str | None:
    git_dir = root / ".git"
    if git_dir.is_file():  # a linked worktree or a submodule: the file names the real directory
        pointer = _first_line(git_dir)
        if not pointer.startswith("gitdir: "):
            return None
        git_dir = root / pointer[len("gitdir: ") :]
    # A linked worktree keeps HEAD for itself and shares the branches with the main checkout.
    shared = _first_line(git_dir / "commondir")
    common = git_dir / shared if shared else git_dir
    value = _first_line(git_dir / "HEAD")
    for _ in range(_SYMBOLIC_REF_HOPS):
        if not value.startswith("ref: "):
            break
        name = value[len("ref: ") :].strip()
        if not name.startswith("refs/") or ".." in name:
            return None
        value = _first_line(git_dir / name) or _first_line(common / name) or _packed_ref(common, name)
    return value[:COMMIT_CHARS] if _OBJECT_NAME.fullmatch(value) else None


def read_commit(root: str | os.PathLike[str]) -> str | None:
    """The commit checked out in the git checkout at ``root``, abbreviated, or None.

    None when ``root`` is not a git checkout, has no commit yet, or keeps its
    refs in a format this does not read (reftable). Nothing is raised and no
    process is started. The result is hexadecimal digits only, never a path.
    Whether the tree has uncommitted changes is not looked at: that takes
    git itself.
    """
    try:
        return _read_commit(Path(root))
    except Exception:  # the build id is a convenience; it must never stop Grove from starting
        return None


def _source_root() -> Path | None:
    """The checkout this package is running from: ``ROOT/src/sf_grove``. None for an installed copy."""
    package = Path(__file__).resolve().parent
    # Only this exact layout counts. Walking further up would find some other
    # repository around an installed copy (a virtualenv inside a checkout).
    return package.parent.parent if package.parent.name == "src" else None


def _build() -> dict[str, str]:
    build = {"version": __version__}
    try:
        root = _source_root()
    except Exception:  # as in read_commit
        root = None
    commit = read_commit(root) if root is not None else None
    if commit:
        build["commit"] = commit
    return build


# Read once, when the process starts and loads this code, and never again. A
# server that is still running after its checkout moved on keeps reporting the
# commit it started from, which is how an operator sees that it needs a restart.
BUILD: dict[str, str] = _build()
