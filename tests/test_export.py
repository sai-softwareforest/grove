"""`grove export` (WO-39, R-VIEW-1, R-VIEW-3, R-VIEW-4): a read-only copy of a project as Markdown pages.

The same bytes for the same data; written only where the caller may write;
nothing of this machine in a page; nothing deleted.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from conftest import MAP_SAMPLE, REPO, TINY, tree_snapshot
from sf_grove.cli import build_parser, main
from sf_grove.errors import GroveError
from sf_grove.export import MAX_SLUG_CHARS, assign_slugs, export_project, redact, shown_path, slug
from sf_grove.scan import EXPORT_MARKER, scan_tree, walk_files
from sf_grove.service import Grove
from sf_grove.tools import TOOLS
from test_gates import _fake_secrets, _session_link

needs_symlinks = pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symbolic links")


@pytest.fixture
def filled(tiny: Grove) -> Grove:
    """The fixture project, scanned, with a map, two notes and a work item that refers to them."""
    tiny.scan("tiny")
    tiny.ingest_map("tiny", str(MAP_SAMPLE))
    tiny.knowledge_write("tiny", "greet-plan", "Greet plan", "# Plan\n\nWrite the test first.\n")
    tiny.knowledge_write("tiny", "release", "Release steps", "Tag, then build.\n")
    tiny.knowledge_write(None, "workspace-note", "A workspace note", "Belongs to no project.\n")
    key = tiny.gaps("tiny", kind="declared_untested")["items"][0]["key"]
    item = tiny.work_create(
        "tiny", "Add a test for greet", plan=f"Covers finding:{key}; see knowledge:greet-plan and https://example.org/pr/1."
    )
    tiny.work_update(item["id"], status="in_progress", note="started", author="tester")
    return tiny


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()
    }


def _refused(grove: Grove, out: Path, project: str = "tiny") -> str:
    with pytest.raises(GroveError) as caught:
        export_project(grove, project, str(out))
    assert caught.value.code == "invalid"
    assert caught.value.message.endswith("Nothing was written.")
    return caught.value.message


# -- pages ---------------------------------------------------------------------


def test_the_pages_of_a_project(filled: Grove, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = export_project(filled, "tiny", str(out))
    pages = _files(out)
    assert result["project"] == "tiny" and result["out"] == str(out)
    assert result["pages"] == len(pages) - 1 == result["written"]["total"]  # every file but the marker
    assert result["unchanged"] == 0 and result["stale"] == {"total": 0, "items": [], "omitted": 0}
    assert {"index.md", "requirements.md", "findings.md", "work/index.md", "work/1.md", EXPORT_MARKER} <= set(pages)
    assert {"knowledge/greet-plan.md", "knowledge/release.md", "blueprint/readme-md.md"} <= set(pages)
    assert not any("workspace-note" in name for name in pages), "a workspace note belongs to no project"

    index = pages["index.md"].decode()
    assert index.startswith("# tiny\n") and "[Requirements](requirements.md)" in index
    assert "[Greet plan](knowledge/greet-plan.md) (`greet-plan`)" in index
    assert "[#1 Add a test for greet](work/1.md)" in index
    assert "declared items, grouped" not in index and "- line 5: Adds two integers. (behaviour)" in pages["requirements.md"].decode()

    readme = pages["blueprint/readme-md.md"].decode()
    assert "## Declared (4)" in readme and "## Actual (0)" in readme and "## Tests (0)" in readme
    calc = pages["blueprint/src-tiny-calc-py.md"].decode()
    assert "## Actual (2)" in calc and "`src/tiny/calc.py` (python)" in calc

    note = pages["knowledge/greet-plan.md"].decode()
    assert "- Key: `greet-plan`" in note and "- Revision: 1 of 1" in note and note.endswith("Write the test first.\n")


def test_findings_have_anchors_and_cross_links(filled: Grove, tmp_path: Path) -> None:
    out = tmp_path / "out"
    export_project(filled, "tiny", str(out))
    findings = (out / "findings.md").read_text(encoding="utf-8")
    stored = filled.gaps("tiny")["items"]
    assert stored
    for finding in stored:
        assert f'<a id="{finding["key"]}"></a>`{finding["key"]}`' in findings
    for kind in {finding["kind"] for finding in stored}:
        assert f"## {kind} (" in findings
    # A finding links to the page of its source file, and that page links back to the anchor.
    untested = next(finding for finding in stored if finding["kind"] == "declared_untested")
    assert "[README.md](blueprint/readme-md.md)" in findings
    assert f"[{untested['key']}](../findings.md#{untested['key']})" in (out / "blueprint" / "readme-md.md").read_text()
    # A work item links what its text refers to.
    work = (out / "work" / "1.md").read_text(encoding="utf-8")
    assert f"[finding:{untested['key']}](../findings.md#{untested['key']})" in work
    assert "[knowledge:greet-plan](../knowledge/greet-plan.md)" in work
    assert "[https://example.org/pr/1](https://example.org/pr/1)" in work
    assert "## Plan" in work and "## History (1)" in work and "tester, ready → in_progress: started" in work
    assert "(../" not in (out / "index.md").read_text() and "](/" not in work, "every link is relative"


def test_a_requirement_id_links_to_the_statement_that_declares_it(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_text("# Proj\n\nR-DEMO-1: the parser accepts empty input.\n")
    grove.project_create("proj", str(root))
    grove.scan("proj")
    grove.work_create("proj", "Cover R-DEMO-1 and R-DEMO-9")
    out = tmp_path / "out"
    export_project(grove, "proj", str(out))
    assert '- <a id="R-DEMO-1"></a>line 3: R-DEMO-1: the parser accepts empty input.' in (out / "requirements.md").read_text()
    work = (out / "work" / "1.md").read_text()
    assert "[R-DEMO-1](../requirements.md#R-DEMO-1)" in work
    assert "- `R-DEMO-9`\n" in work, "an id no document declares stays text"


# -- determinism ------------------------------------------------------------------


def test_two_exports_are_byte_identical(filled: Grove, tmp_path: Path) -> None:
    first = export_project(filled, "tiny", str(tmp_path / "one"))
    again = export_project(filled, "tiny", str(tmp_path / "one"))
    export_project(filled, "tiny", str(tmp_path / "two"))
    assert _files(tmp_path / "one") == _files(tmp_path / "two")
    assert again["written"]["total"] == 0 and again["unchanged"] == first["pages"] == again["pages"]
    for name, data in _files(tmp_path / "one").items():
        assert data.endswith(b"\n") and not data.endswith(b"\n\n") and b"\r" not in data, name
        data.decode("utf-8")


def test_an_unchanged_page_is_not_rewritten(filled: Grove, tmp_path: Path) -> None:
    out = tmp_path / "out"
    export_project(filled, "tiny", str(out))
    before = tree_snapshot(out)
    export_project(filled, "tiny", str(out))
    assert tree_snapshot(out) == before


def test_editing_one_note_changes_exactly_one_page(filled: Grove, tmp_path: Path) -> None:
    out = tmp_path / "out"
    export_project(filled, "tiny", str(out))
    before = _files(out)
    filled.knowledge_write("tiny", "greet-plan", "Greet plan", "# Plan\n\nWrite the test first, then the code.\n")
    result = export_project(filled, "tiny", str(out))
    after = _files(out)
    assert result["written"] == {"total": 1, "items": ["knowledge/greet-plan.md"], "omitted": 0}
    assert [name for name in after if after[name] != before.get(name)] == ["knowledge/greet-plan.md"]
    assert b"- Revision: 2 of 2" in after["knowledge/greet-plan.md"]


def test_a_rescan_without_a_change_keeps_every_page_but_the_index(filled: Grove, tmp_path: Path) -> None:
    out = tmp_path / "out"
    export_project(filled, "tiny", str(out))
    filled.scan("tiny")  # new row ids and a new scan time; the same blueprint
    result = export_project(filled, "tiny", str(out))
    assert set(result["written"]["items"]) <= {"index.md"}, "only the scan time on the index may differ"


# -- names ------------------------------------------------------------------------


def test_slugs_are_plain_bounded_and_unique() -> None:
    assert slug("src/tiny/__init__.py") == "src-tiny-init-py"
    assert slug("Ünïcode & Spaces!") == "n-code-spaces"
    assert slug("///") == "page" and slug("") == "page"
    long = slug("a/" * 200 + "end")
    assert len(long) <= MAX_SLUG_CHARS and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", long)

    slugs = assign_slugs([(name, name) for name in ("a.b", "a-b", "a/b", "A_B", "x" * 200, "x" * 199 + "y")])
    assert len(set(slugs.values())) == 6
    assert slugs["A_B"] == "a-b", "the first in order keeps the plain slug"
    for name, value in slugs.items():
        assert len(value) <= MAX_SLUG_CHARS and re.fullmatch(r"[a-z0-9-]+", value), name
    assert re.fullmatch(r"a-b-[0-9a-f]{8}", slugs["a.b"])
    assert assign_slugs([(name, name) for name in ("a/b", "a.b", "A_B", "a-b")])["a.b"] == slugs["a.b"], "no order of arrival"


def test_colliding_keys_and_paths_get_pages_of_their_own(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "a").mkdir(parents=True)
    (root / "a" / "b.py").write_text("def one():\n    return 1\n")
    (root / "a-b.py").write_text("def two():\n    return 2\n")
    grove.project_create("proj", str(root))
    grove.scan("proj")
    grove.knowledge_write("proj", "a.b", "Dotted", "one\n")
    grove.knowledge_write("proj", "a-b", "Dashed", "two\n")
    out = tmp_path / "out"
    export_project(grove, "proj", str(out))
    notes = sorted(path.name for path in (out / "knowledge").iterdir())
    assert len(notes) == 2 and notes[1] == "a-b.md" and re.fullmatch(r"a-b-[0-9a-f]{8}\.md", notes[0])
    assert "Dashed" in (out / "knowledge" / "a-b.md").read_text()
    files = sorted(path.name for path in (out / "blueprint").iterdir())
    assert len(files) == 2 and files[1] == "a-b-py.md" and re.fullmatch(r"a-b-py-[0-9a-f]{8}\.md", files[0])
    index = (out / "index.md").read_text()
    assert all(f"(knowledge/{name})" in index for name in notes) and all(f"(blueprint/{name})" in index for name in files)


# -- privacy ------------------------------------------------------------------------


def test_shown_paths_are_relative_to_the_root_or_a_bare_name() -> None:
    assert shown_path("src/a.py", "/work/proj") == "src/a.py"
    assert shown_path("/work/proj/docs/MAP.md", "/work/proj") == "docs/MAP.md"
    assert shown_path("/elsewhere/deep/MAP.md", "/work/proj") == "MAP.md"
    assert shown_path("/work/project-two/MAP.md", "/work/proj") == "MAP.md", "a sibling with the same prefix is outside"
    assert shown_path("C:\\Users\\someone\\maps\\MAP.md", "C:\\work\\proj") == "MAP.md"
    assert shown_path(None, "/work/proj") == "(no source)"


def test_pages_hold_no_path_of_this_machine(filled: Grove, home: Path, tmp_path: Path) -> None:
    # The map was ingested from outside the project root: its items are stored under its full path.
    assert filled.blueprint_get("tiny", source_path=str(MAP_SAMPLE))["total"] > 0
    filled.knowledge_write(
        "tiny",
        "machine-notes",
        "Machine notes",
        f"The data is in {home} and the code in {TINY}.\nAlso {tmp_path}/scratch and " + "/home/" + "someone/notes.txt\n",
    )
    out = tmp_path / "out"
    result = export_project(filled, "tiny", str(out))
    text = "\n".join(data.decode() for data in _files(out).values())
    for private in (str(home), str(TINY), str(REPO), str(MAP_SAMPLE.parent), "/home/" + "someone", "grove.db"):
        assert private not in text, private
    assert "[map_sample.md](blueprint/map-sample-md.md)" in text, "a map from outside the root is shown by name only"
    assert result["redactions"] >= 3
    note = (out / "knowledge" / "machine-notes.md").read_text()
    assert "The data is in [redacted] and the code in [redacted]." in note and "[redacted]/notes.txt" in note


def test_every_kind_of_secret_the_publish_check_names_is_redacted(filled: Grove, tmp_path: Path) -> None:
    secrets = _fake_secrets()
    body = "\n".join(f"- {name}: {value}" for name, value in secrets.items()) + f"\n\nSession: {_session_link()}\n"
    filled.knowledge_write("tiny", "leaky", "Leaky note", body)
    filled.work_create("tiny", "Rotate " + secrets["github-classic.txt"], plan="Paths: C:\\Users\\" + "someone\\x and /Users/" + "someone/y")
    out = tmp_path / "out"
    result = export_project(filled, "tiny", str(out))
    text = "\n".join(data.decode() for data in _files(out).values())
    leaked = [name for name, value in secrets.items() if value in text]
    assert not leaked, leaked
    assert not re.search(r"session_[0-9A-Za-z]{20,}", text) and "someone" not in text
    assert result["redactions"] >= len(secrets) + 3
    assert text.count("[redacted]") == result["redactions"]


def test_redaction_leaves_ordinary_text_alone() -> None:
    plain = (
        "See https://example.org/home/page and src/home/views.py, a postgres://db.example.invalid/grove URL "
        "without a password, session_short, and the /home directory."
    )
    assert redact(plain) == (plain, 0)
    assert redact("in /srv/data/grove here", ["/srv/data/grove", "/"]) == ("in [redacted] here", 1)
    text, count = redact("file:///home/" + "someone/x and /Users/" + "other")
    assert text == "file://[redacted]/x and [redacted]" and count == 2


def test_redaction_and_the_markdown_subset_take_linear_time() -> None:
    import time

    from sf_grove.view import render_markdown

    size = 400_000
    worst = {
        "database prefixes": "postgres://" * (size // 11),
        "database colons": "mysql://" + "a:" * (size // 2),
        "home prefixes": "/home/" * (size // 6),
        "session prefixes": "session_" * (size // 8),
        "key headers": "-----BEGIN " * (size // 11),
        "one long word": "A" * size,
    }
    for name, text in worst.items():
        started = time.perf_counter()
        redact(text, ["/srv/grove-home"])
        assert time.perf_counter() - started < 5, f"redact is not linear on {name}"
    for name, text in {"brackets": "[" * size, "stars": "*a " * (size // 3), "ticks": "`a" * (size // 2), "links": "[x](" * (size // 4)}.items():
        started = time.perf_counter()
        render_markdown(text)
        assert time.perf_counter() - started < 5, f"the Markdown subset is not linear on {name}"


# -- where an export may write ----------------------------------------------------------


def test_the_default_directory_is_inside_the_data_directory_and_outside_the_project(filled: Grove, home: Path) -> None:
    before = tree_snapshot(TINY)
    result = export_project(filled, "tiny")
    out = home / "exports" / "tiny"
    assert result["out"] == str(out.resolve()) and (out / "index.md").is_file() and (out / EXPORT_MARKER).is_file()
    filled.scan("tiny")
    export_project(filled, "tiny")
    assert tree_snapshot(TINY) == before, "R-INV-4: nothing under the project root was created or changed"


def test_projects_whose_names_differ_only_in_case_get_directories_of_their_own(filled: Grove, home: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    filled.project_create("Tiny", str(other))
    first = Path(export_project(filled, "Tiny")["out"])
    second = Path(export_project(filled, "tiny")["out"])
    assert first != second and first.parent == second.parent == (home / "exports").resolve()
    assert export_project(filled, "tiny")["stale"]["total"] == 0


@pytest.mark.parametrize("inside", ["", "docs/export", "new/deep/dir"])
def test_a_directory_inside_a_project_root_is_refused(grove: Grove, tmp_path: Path, inside: str) -> None:
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# Proj\n\nParses a file.\n")
    other = tmp_path / "other"
    other.mkdir()
    grove.project_create("proj", str(root))
    grove.project_create("other", str(other))
    grove.scan("other")
    before = tree_snapshot(root)
    # Any registered root counts, not only the root of the project that is exported.
    for project in ("proj", "other"):
        message = _refused(grove, root / inside, project)
        assert "inside the root of project 'proj'" in message and "R-INV-4" in message
    assert tree_snapshot(root) == before


@needs_symlinks
def test_a_path_that_resolves_into_a_project_root_is_refused(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    grove.project_create("proj", str(root))
    (tmp_path / "alias").symlink_to(root / "docs", target_is_directory=True)
    before = tree_snapshot(root)
    assert "inside the root of project 'proj'" in _refused(grove, tmp_path / "alias" / "export", "proj")
    assert tree_snapshot(root) == before


def test_the_data_directory_and_any_directory_with_a_database_are_refused(filled: Grove, home: Path, tmp_path: Path) -> None:
    before = sorted(path.name for path in home.iterdir())
    assert "is the Grove data directory itself" in _refused(filled, home)
    assert sorted(path.name for path in home.iterdir()) == before
    other = tmp_path / "other-home"
    with Grove(other) as second:
        second.status()
    assert "it is a Grove data directory" in _refused(filled, other)
    assert not (other / "index.md").exists()


def test_groves_own_source_tree_is_refused_for_another_project(filled: Grove) -> None:
    target = REPO / "tests" / "no-such-export-directory"
    assert "inside Grove's own source tree" in _refused(filled, target)
    assert not target.exists()


def test_a_directory_with_unknown_files_is_refused(filled: Grove, tmp_path: Path) -> None:
    out = tmp_path / "notes"
    out.mkdir()
    (out / "index.md").write_text("mine\n")
    before = tree_snapshot(out)
    assert f"holds no {EXPORT_MARKER} file" in _refused(filled, out)
    assert tree_snapshot(out) == before
    (out / "index.md").unlink()
    assert export_project(filled, "tiny", str(out))["pages"] > 0, "an empty directory is fine"
    (tmp_path / "a-file").write_text("x")
    assert "is not a directory" in _refused(filled, tmp_path / "a-file")


def test_the_export_of_another_project_is_not_overwritten(filled: Grove, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    filled.project_create("other", str(other))
    out = tmp_path / "out"
    export_project(filled, "tiny", str(out))
    before = tree_snapshot(out)
    assert "holds the export of project 'tiny', not of 'other'" in _refused(filled, out, "other")
    assert tree_snapshot(out) == before


@needs_symlinks
def test_no_symbolic_link_is_followed(filled: Grove, tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    assert "is a symbolic link" in _refused(filled, tmp_path / "link")
    assert list(real.iterdir()) == []

    out = tmp_path / "out"
    export_project(filled, "tiny", str(out))
    victim = tmp_path / "victim.txt"
    victim.write_text("untouched\n")
    (out / "index.md").unlink()
    (out / "index.md").symlink_to(victim)
    filled.knowledge_write("tiny", "release", "Release steps", "Changed.\n")  # a page that would be rewritten
    before = _files(out / "knowledge")
    assert "is not a regular file" in _refused(filled, out)
    assert victim.read_text() == "untouched\n" and _files(out / "knowledge") == before, "refused before any page was written"

    (out / "index.md").unlink()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for name in ("work", EXPORT_MARKER):
        fresh = tmp_path / f"fresh-{name.strip('.')}"
        export_project(filled, "tiny", str(fresh))
        if name == "work":
            for page in (fresh / "work").iterdir():
                page.unlink()
            (fresh / "work").rmdir()
            (fresh / "work").symlink_to(elsewhere, target_is_directory=True)
        else:
            (fresh / name).unlink()
            (fresh / name).symlink_to(victim)
        _refused(filled, fresh)
    assert list(elsewhere.iterdir()) == [] and victim.read_text() == "untouched\n"


# -- nothing is deleted ----------------------------------------------------------------


def test_a_page_that_is_no_longer_produced_is_reported_and_kept(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_text("# Proj\n\nParses a file.\n")
    (root / "old.py").write_text("def old():\n    return 1\n")
    grove.project_create("proj", str(root))
    grove.scan("proj")
    out = tmp_path / "out"
    export_project(grove, "proj", str(out))
    (out / "mine.txt").write_text("not a page\n")
    kept = (out / "blueprint" / "old-py.md").read_bytes()
    (root / "old.py").unlink()
    grove.scan("proj")
    result = export_project(grove, "proj", str(out))
    assert result["stale"] == {"total": 1, "items": ["blueprint/old-py.md"], "omitted": 0}
    assert "Grove deletes nothing" in result["note"]
    assert (out / "blueprint" / "old-py.md").read_bytes() == kept and (out / "mine.txt").exists()
    assert "old.py" not in (out / "index.md").read_text()


# -- the scanner and an export ------------------------------------------------------------


def test_a_scan_records_nothing_from_a_directory_that_holds_the_marker(filled: Grove, grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# Proj\n\nParses a file.\n")
    (root / "docs" / "guide.md").write_text("# Guide\n\nThe guide explains the parser.\n")
    # An export that came to lie inside a project: written elsewhere, moved in by hand.
    export_project(filled, "tiny", str(tmp_path / "made"))
    (tmp_path / "made").rename(root / "docs" / "export")
    (root / "docs" / "export" / "README.md").write_text("# Planted\n\nPlanted statement about zebras.\n")
    (root / "docs" / "export" / "deeper").mkdir()
    (root / "docs" / "export" / "deeper" / "module.py").write_text("def planted_zebra():\n    return 1\n")

    walked = list(walk_files(str(root)))
    assert walked == ["README.md", "docs/guide.md"]
    assert scan_tree(root).files_seen == 2
    grove.project_create("proj", str(root))
    before = tree_snapshot(root)
    summary = grove.scan("proj")
    assert summary["files_seen"] == 2
    paths = {row["source_path"] for row in grove.blueprint_get("proj", summary=True, limit=200)["items"]}
    assert paths == {"README.md", "docs/guide.md"}
    assert grove.blueprint_get("proj", query="zebra")["total"] == 0 and grove.gaps("proj", query="export")["total"] == 0
    assert tree_snapshot(root) == before


def test_a_root_that_is_itself_an_export_yields_nothing(filled: Grove, tmp_path: Path) -> None:
    out = tmp_path / "out"
    export_project(filled, "tiny", str(out))
    assert list(walk_files(str(out))) == []


# -- the command line, and what did not change ----------------------------------------------


def test_the_command_prints_one_envelope(filled: Grove, home: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    filled.close()
    out = tmp_path / "out"
    assert main(["--home", str(home), "export", "tiny", "--out", str(out)]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert data["pages"] == data["written"]["total"] > 0 and (out / "index.md").is_file()
    assert main(["--home", str(home), "export", "tiny"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["out"] == str((home / "exports" / "tiny").resolve())
    assert main(["--home", str(home), "export", "tiny", "--out", str(TINY / "export")]) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "invalid" and not (TINY / "export").exists()
    assert main(["--home", str(home), "export", "nobody"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "not_found"


def test_export_and_view_are_commands_without_a_tool() -> None:
    commands = set(build_parser()._subparsers._group_actions[0].choices)  # noqa: SLF001 - top-level command names
    assert {"export", "view"} <= commands
    assert len(TOOLS) == 16 and not any("export" in tool.name or "view" in tool.name for tool in TOOLS)
