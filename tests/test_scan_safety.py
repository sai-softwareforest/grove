"""Requirements 6 and 7: scans are read-only, and caps are honoured and reported."""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import TINY, tree_snapshot
from sf_grove.errors import GroveError
from sf_grove.scan import scan_tree, walk_files
from sf_grove.service import Grove


def test_scan_does_not_write_inside_the_fixture_tree(tiny: Grove, home: Path) -> None:
    before = tree_snapshot(TINY)
    tiny.scan("tiny")
    tiny.scan("tiny")
    tiny.gaps("tiny")
    tiny.recommend_next("tiny")
    after = tree_snapshot(TINY)
    assert after == before, "scan changed, added or removed something under fixtures/tiny"
    assert TINY.resolve() not in home.resolve().parents  # the data dir is elsewhere
    assert (home / "grove.db").exists()


def test_scan_does_not_write_inside_a_scratch_tree(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "scratch"
    (root / "pkg").mkdir(parents=True)
    (root / "README.md").write_text("# Scratch\n\nParses a config file.\n")
    (root / "pkg" / "config.py").write_text("def parse_config(path):\n    return {}\n")
    (root / ".gitignore").write_text("ignored/\n")
    before = tree_snapshot(root)
    grove.project_create("scratch", str(root))
    grove.scan("scratch")
    assert tree_snapshot(root) == before
    assert sorted(path.name for path in root.iterdir()) == [".gitignore", "README.md", "pkg"]


def test_file_cap_is_reported_and_recorded(tiny: Grove) -> None:
    summary = tiny.scan("tiny", max_files=1)
    assert summary["caps"]["max_files"] == 1
    assert summary["caps"]["hit"] == ["max_files"]
    assert summary["files_seen"] == 1
    assert any("max_files" in warning for warning in summary["warnings"])

    project = tiny.project_get("tiny")
    assert project["last_scanned_at"] is not None
    assert project["caps_hit"] == ["max_files"]
    assert any("max_files" in warning for warning in project["cap_warnings"])
    assert project["last_scan"]["caps"]["max_files"] == 1

    # A later uncapped scan clears the warning and sees the whole tree.
    full = tiny.scan("tiny")
    assert full["caps"]["hit"] == [] and full["files_seen"] > 1
    assert tiny.project_get("tiny")["caps_hit"] == []


def test_time_cap_is_reported(tiny: Grove) -> None:
    summary = tiny.scan("tiny", max_seconds=1e-9)
    assert summary["caps"]["hit"] == ["max_seconds"]
    assert summary["files_seen"] == 0
    assert tiny.project_get("tiny")["caps_hit"] == ["max_seconds"]


def test_cap_arguments_are_validated(tiny: Grove) -> None:
    for kwargs in ({"max_files": 0}, {"max_seconds": 0}, {"max_seconds": -1}, {"max_files": "many"}):
        with pytest.raises(GroveError) as raised:
            tiny.scan("tiny", **kwargs)
        assert raised.value.code == "invalid"


def test_gitignore_and_always_skipped_directories(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    for directory in ("src", "node_modules/dep", ".venv/lib", "target/debug", "generated", "src/sub", ".git"):
        (root / directory).mkdir(parents=True)
    (root / ".gitignore").write_text("generated/\n*.log\n")
    (root / "src" / "sub" / ".gitignore").write_text("local_only.py\n")
    for name in (
        "src/app.py",
        "src/sub/kept.py",
        "src/sub/local_only.py",
        "node_modules/dep/index.js",
        ".venv/lib/site.py",
        "target/debug/build.rs",
        "generated/out.py",
        "debug.log",
        ".git/config",
    ):
        (root / name).write_text("def f():\n    pass\n")
    assert list(walk_files(str(root))) == [".gitignore", "src/app.py", "src/sub/.gitignore", "src/sub/kept.py"]

    result = scan_tree(root)
    modules = sorted(item.title for item in result.items if item.extra.get("kind") == "module")
    assert modules == ["src/app.py", "src/sub/kept.py"]
