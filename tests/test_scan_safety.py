"""Requirements 6 and 7: scans are read-only, and caps are honoured and reported."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import TINY, tree_snapshot
from sf_grove.cli import main
from sf_grove.db import now_iso
from sf_grove.errors import GroveError
from sf_grove.scan import scan_tree, walk_files
from sf_grove.service import Grove
from sf_grove.tools import call_tool


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


# -- the data directory stays outside every project root (R-HOME-4, R-INV-4) ------


def _project_tree(root: Path) -> Path:
    (root / "pkg").mkdir(parents=True)
    (root / "README.md").write_text("# Proj\n\nParses a config file.\n")
    (root / "pkg" / "config.py").write_text("def parse_config(path):\n    return {}\n")
    return root


@pytest.mark.parametrize("inside", ["", ".grove", "deep/down/data"])
def test_project_create_refuses_a_data_directory_inside_the_root(tmp_path: Path, inside: str) -> None:
    root = _project_tree(tmp_path / "proj")
    home = root / inside
    before = tree_snapshot(root)
    with Grove(home) as grove:
        with pytest.raises(GroveError) as raised:
            grove.project_create("proj", str(root))
    assert raised.value.code == "invalid"
    # The message names both paths and says what to do.
    assert str(home.resolve()) in raised.value.message and str(root.resolve()) in raised.value.message
    assert "--home" in raised.value.message and "GROVE_HOME" in raised.value.message
    # Refused before the database was opened: nothing was created inside the project.
    assert tree_snapshot(root) == before


def test_the_refusal_is_the_same_on_both_surfaces(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project_tree(tmp_path / "proj")
    home = root / ".grove"
    before = tree_snapshot(root)

    envelope = call_tool(home, "grove_project_create", {"name": "proj", "root_path": str(root)})
    assert envelope["ok"] is False and envelope["error"]["code"] == "invalid"
    assert "is inside the project root" in envelope["error"]["message"]

    assert main(["--home", str(home), "project", "create", "proj", "--root", str(root)]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid"
    assert tree_snapshot(root) == before


def test_paths_are_compared_after_resolving_symlinks(tmp_path: Path) -> None:
    root = _project_tree(tmp_path / "proj")
    (root / "data").mkdir()
    (tmp_path / "home-link").symlink_to(root / "data", target_is_directory=True)
    (tmp_path / "root-link").symlink_to(root, target_is_directory=True)
    before = tree_snapshot(root)

    # A home reached through a link that points into the project is inside it.
    with Grove(tmp_path / "home-link") as grove:
        with pytest.raises(GroveError) as raised:
            grove.project_create("proj", str(root))
    assert raised.value.code == "invalid" and str((root / "data").resolve()) in raised.value.message
    # So is a home inside a project that was named through a link.
    with Grove(root / "data") as grove:
        with pytest.raises(GroveError) as raised:
            grove.project_create("proj", str(tmp_path / "root-link"))
    assert raised.value.code == "invalid"
    assert tree_snapshot(root) == before

    # A link inside the project that leads out of it is fine: the database is written outside.
    outside = tmp_path / "outside-home"
    outside.mkdir()
    (root / "grove-data").symlink_to(outside, target_is_directory=True)
    with Grove(root / "grove-data") as grove:
        grove.project_create("proj", str(root))
        grove.scan("proj")
    assert (outside / "grove.db").exists()
    assert sorted(path.name for path in root.iterdir()) == ["README.md", "data", "grove-data", "pkg"]
    assert list((root / "data").iterdir()) == []


def test_a_sibling_directory_with_the_same_prefix_is_not_inside(tmp_path: Path) -> None:
    root = _project_tree(tmp_path / "proj")
    with Grove(tmp_path / "proj-data") as grove:  # shares a name prefix with the root, but is beside it
        grove.project_create("proj", str(root))
        assert grove.scan("proj")["items"]["actual"] > 0
    # A project inside the data directory is the reverse case and is not refused: nothing is written in it.
    inner = _project_tree(tmp_path / "proj-data" / "checkout")
    before = tree_snapshot(inner)
    with Grove(tmp_path / "proj-data") as grove:
        grove.project_create("inner", str(inner))
        grove.scan("inner")
    assert tree_snapshot(inner) == before


def test_scan_refuses_a_project_registered_with_the_home_inside_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # An earlier Grove accepted this registration. The data stays readable; only scanning is refused.
    root = _project_tree(tmp_path / "proj")
    home = root / ".grove"
    with Grove(home) as grove:
        with grove._write():  # noqa: SLF001 - stands in for a row written before the check existed
            grove.conn.execute(
                "INSERT INTO projects (name, root_path, created_at) VALUES ('proj', ?, ?)", (str(root.resolve()), now_iso())
            )
        grove.knowledge_write("proj", "note", "Note", "kept")
        work = grove.work_create("proj", "Move the data directory")

    with Grove(home) as grove:
        with pytest.raises(GroveError) as raised:
            grove.scan("proj")
        assert raised.value.code == "invalid"
        assert str(home.resolve()) in raised.value.message and str(root.resolve()) in raised.value.message
        assert "move the whole data directory" in raised.value.message
        # Nothing was scanned, and everything that was stored can still be read and updated.
        project = grove.project_get("proj")
        assert project["last_scanned_at"] is None and project["counts"]["items"]["actual"] == 0
        assert grove.knowledge_get("note")["body"] == "kept"
        assert grove.work_update(work["id"], status="in_progress")["status"] == "in_progress"
        assert grove.blueprint_get("proj")["total"] == 0 and grove.gaps("proj")["total"] == 0
        assert grove.recommend_next("proj")["action"] == "scan"

    assert call_tool(home, "grove_scan", {"project": "proj"})["error"]["code"] == "invalid"
    assert main(["--home", str(home), "scan", "proj"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid"

    # The remedy in the message works: move the data directory out, and the same project scans.
    moved = tmp_path / "moved-home"
    home.rename(moved)
    with Grove(moved) as grove:
        assert grove.scan("proj")["items"]["actual"] > 0
        assert grove.knowledge_get("note")["body"] == "kept"
    assert sorted(path.name for path in root.iterdir()) == ["README.md", "pkg"]


def test_scan_resolves_the_root_again(tmp_path: Path) -> None:
    # The root was outside the home when the project was created; a link later puts the home inside it.
    real = _project_tree(tmp_path / "real")
    home = tmp_path / "elsewhere" / "home"
    with Grove(home) as grove:
        grove.project_create("proj", str(real))
        grove.scan("proj")
        with grove._write():  # noqa: SLF001 - as if the registered path now led through a link
            grove.conn.execute("UPDATE projects SET root_path = ? WHERE name = 'proj'", (str(tmp_path / "link"),))
    (tmp_path / "link").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with Grove(home) as grove:
        with pytest.raises(GroveError) as raised:
            grove.scan("proj")
    assert raised.value.code == "invalid" and str((tmp_path / "elsewhere").resolve()) in raised.value.message
