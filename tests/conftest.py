"""Shared fixtures. Every test gets its own Grove home under pytest's tmp_path."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from sf_grove.service import Grove

REPO = Path(__file__).resolve().parent.parent
TINY = REPO / "fixtures" / "tiny"
MAP_SAMPLE = REPO / "fixtures" / "map_sample.md"


@pytest.fixture(autouse=True)
def _no_ambient_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A test that forgets to pass a home must not touch the developer's real one.
    monkeypatch.setenv("GROVE_HOME", str(tmp_path / "ambient-home"))
    # Nor may a developer's own author name leak into what tests write.
    monkeypatch.delenv("GROVE_AUTHOR", raising=False)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path / "grove-home"


@pytest.fixture
def grove(home: Path):
    with Grove(home) as instance:
        yield instance


@pytest.fixture
def tiny(grove: Grove) -> Grove:
    grove.project_create("tiny", str(TINY))
    return grove


def tree_snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    """Every file and directory under root: (mtime_ns, size, sha256 of content)."""
    snapshot: dict[str, tuple[int, int, str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames + ["."]:
            path = Path(dirpath) / name
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
            snapshot[str(path.resolve().relative_to(root.resolve()))] = (stat.st_mtime_ns, stat.st_size, digest)
    return snapshot
