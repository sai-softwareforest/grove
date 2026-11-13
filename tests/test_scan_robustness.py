"""R-SCAN-7, R-SCAN-8: scan time is bounded by input size, and what is skipped is reported."""

from __future__ import annotations

import itertools
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from sf_grove import claims, mapdoc, scan, service
from sf_grove.scan import MAX_LINE_CHARS, Clock, clean_inline, extract_declared, extract_symbols, extract_test_names, scan_tree
from sf_grove.service import Grove

# Each of these lines took from seconds to many minutes to analyse before the
# line cap and the table-separator fix (quadratic backtracking). 200 000
# characters is well under the 512 KB file cap.
N = 200_000
HOSTILE_DOC_LINES = {
    "spaces": " " * N + "x",
    "brackets": "a " + "[" * N,
    "images": "a " + "![" * (N // 2),
    "angles": "a " + "<" * N,
}
BUDGET_SECONDS = 5.0  # generous: the fixed code needs milliseconds, the old code minutes


def timed(call) -> float:
    started = time.perf_counter()
    call()
    return time.perf_counter() - started


@pytest.mark.parametrize("name", sorted(HOSTILE_DOC_LINES))
def test_a_hostile_long_line_in_a_document_costs_nothing(name: str) -> None:
    text = "# Title\n\nIt always frobs the widget.\n\n" + HOSTILE_DOC_LINES[name] + "\n\nIt never drops a frame.\n"
    items: list = []
    assert timed(lambda: items.extend(extract_declared("README.md", text))) < BUDGET_SECONDS
    # The long line is skipped; the lines around it are still read.
    assert [item.title for item in items] == ["Title", "It always frobs the widget.", "It never drops a frame."]
    assert timed(lambda: mapdoc.parse_map("Claim one is documented here.\n\n" + HOSTILE_DOC_LINES[name] + "\n")) < BUDGET_SECONDS


def test_hostile_long_lines_in_source_and_test_files_cost_nothing() -> None:
    js_tests = "it('adds numbers', () => {})\n" + " it(" * (N // 4) + "\n"
    found: list = []
    assert timed(lambda: found.extend(extract_test_names("javascript", js_tests))) < BUDGET_SECONDS
    assert [test.name for test in found] == ["adds numbers"]
    minified = "function first() {}\n" + "const a = " + "(" * N + "\nfunction last() {}\n"
    symbols: list = []
    assert timed(lambda: symbols.extend(extract_symbols("javascript", minified))) < BUDGET_SECONDS
    assert [symbol.name for symbol in symbols] == ["first", "last"]


def test_table_separator_pattern_is_linear_and_unchanged_in_meaning() -> None:
    for pattern in (scan._TABLE_SEP, mapdoc._TABLE_SEP):
        for line in ("|---|---|", "---|---", "  | :--- | ---: |  ", "--", ":-- | --:", "|--|"):
            assert pattern.match(line), line
        for line in ("| a | b |", "-", "| - |", "text", "", "   ", "|", "a --- b"):
            assert not pattern.match(line), line
        assert timed(lambda: pattern.match(" " * N + "x")) < 1.0
        assert timed(lambda: pattern.match("|" + " " * N + "x")) < 1.0


def test_a_line_at_the_cap_is_analysed_and_one_over_is_not() -> None:
    at_cap = "def at_cap():" + " " * (MAX_LINE_CHARS - len("def at_cap():"))
    over = "def over_cap():" + " " * (MAX_LINE_CHARS + 1 - len("def over_cap():"))
    assert len(at_cap) == MAX_LINE_CHARS and len(over) == MAX_LINE_CHARS + 1
    assert [symbol.name for symbol in extract_symbols("python", at_cap + "\n" + over + "\n")] == ["at_cap"]
    assert scan.long_line_count(at_cap + "\n" + over + "\n") == 1


# One line of the cap's length each. Before WO-24 the first three took from
# 0.1 to 0.4 seconds a line in a document or a map, the fourth 0.02.
WORST_LINES_AT_THE_CAP = {
    "brackets": "a " + "[" * (MAX_LINE_CHARS - 2),
    "images": "a " + "![" * (MAX_LINE_CHARS // 2 - 1),
    "heading of hashes": "# " + "#" * (MAX_LINE_CHARS - 3) + "x",
    "hyphenated word": ("A is " + "observed-in-code-" * MAX_LINE_CHARS)[: MAX_LINE_CHARS - 1] + ")",
}


@pytest.mark.parametrize("name", sorted(WORST_LINES_AT_THE_CAP))
def test_worst_case_lines_at_the_cap_stay_cheap(name: str) -> None:
    # Some patterns are still quadratic below the cap (the JavaScript test
    # name after a run of "it("); the cap is what keeps that small. Twenty
    # lines, so that a slow line shows over the noise of the machine.
    line = WORST_LINES_AT_THE_CAP[name]
    assert len(line) == MAX_LINE_CHARS
    text = (line + "\n\n") * 20
    assert timed(lambda: extract_declared("README.md", text)) < 1.0
    assert timed(lambda: (mapdoc.map_title(text, "fallback"), mapdoc.parse_map(text))) < 1.0
    assert timed(lambda: service._outline(text)) < 1.0
    assert timed(lambda: [extract_test_names("javascript", text), extract_symbols("typescript", text)]) < 1.0


def test_inline_patterns_are_linear_and_read_well_formed_markdown_as_before() -> None:
    for text, cleaned in (
        ("See [the guide](docs/guide.md) and [the notes][n].", "See the guide and the notes."),
        ("[![build](https://example.invalid/b.svg)](https://example.invalid) Widget", "Widget"),
        ("![logo](logo.png) ![alt][ref] text", "text"),
        ("a <b>bold</b><br/> word", "a bold word"),
        ("**strong** _em_ `code` snake_case", "strong em code snake_case"),
        ("mail <<someone@example.invalid>> now", "mail > now"),
        # A link target may hold a pair of parentheses; it used to end at the first ")".
        ("[Foo](https://example.invalid/wiki/Foo_(bar)) is here", "Foo is here"),
        # Nothing reads past the next opener, so an opener that never closes stays as text.
        ("[a [b](c)", "[a b"),
        ("<a <b> c", "<a c"),
    ):
        assert clean_inline(text) == cleaned, text
    for opener in ("[", "![", "<", "(", "[a](", "![a](", "[a][", "[a](b (c) "):
        hostile = opener * (N // len(opener))
        assert timed(lambda: clean_inline(hostile)) < 1.0, opener


def test_heading_pattern_is_linear_and_unchanged_in_meaning() -> None:
    for line, heading in (
        ("# Title", (1, "Title")),
        ("### Title ###", (3, "Title")),
        ("   ## a # b ##  ", (2, "a # b")),
        ("# C#", (1, "C")),  # as before: the closing "#" needs no space in front of it
        ("#\t#", (1, "")),
        ("# ", (1, "")),
        ("#Title", None),
        ("####### seven", None),
        ("    # four spaces", None),
        ("text # not a heading", None),
    ):
        assert scan.atx_heading(line) == heading, line
    hostile = "# " + "#" * N + "x"
    assert timed(lambda: scan.atx_heading(hostile)) < 1.0
    # A knowledge document has no line cap: its outline reads the whole line.
    outline: list = []
    assert timed(lambda: outline.extend(service._outline(hostile + "\n# Real\n"))) < 1.0
    assert outline[1] == 2 and outline[0][1] == {"level": 1, "title": "Real", "line": 2}


def test_file_name_pattern_is_linear_and_unchanged_in_meaning() -> None:
    for sentence, named in (
        ("Settings live in my-app.toml today.", "my-app.toml"),
        ("The loader passes --config.json along to the worker.", "config.json"),  # named from its first word character, as before
        ("It reads src/app/main.py first.", "src/app/main.py"),
    ):
        assert claims.classify(sentence) == (claims.SETUP, f"names a path or file name ({named!r})"), sentence
    assert claims.classify("It reads ---.toml as text.")[0] == claims.BEHAVIOUR  # hyphens alone are no file name
    hostile = "A is " + "observed-in-code-" * (N // 17)
    assert timed(lambda: claims._PATH.search(hostile)) < 1.0
    assert timed(lambda: claims._PATH.search(hostile + ".toml")) < 1.0


@pytest.mark.parametrize("opener", ["[", "![", "<", "[a]("])
def test_a_long_paragraph_in_a_map_is_read_in_linear_time(opener: str) -> None:
    # A paragraph of a map is joined before it is read and has no length cap.
    # 40 000 characters of "[" took 9 seconds before the inline patterns were
    # made linear; a map may be 2 MB.
    line = (opener * 60)[:60]
    text = "The widget is untested here.\n" + (line + "\n") * (N // 61)
    blocks: list = []
    assert timed(lambda: blocks.extend(mapdoc.parse_map(text))) < BUDGET_SECONDS
    assert [(block.line, block.labels) for block in blocks] == [(1, ["untested"])]
    assert timed(lambda: mapdoc.parse_map("- The widget is untested here.\n" + ("  " + line + "\n") * (N // 63))) < BUDGET_SECONDS


def test_scan_reports_long_lines_never_silently(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# Proj\n\nIt always frobs the widget.\n\n" + HOSTILE_DOC_LINES["brackets"] + "\n")
    (root / "docs" / "guide.md").write_text("# Guide\n\nShort and readable.\n")
    (root / "bundle.js").write_text("function ok() {}\n" + "x" * N + "\n" + "y" * N + "\n")
    grove.project_create("proj", str(root))
    started = time.perf_counter()
    result = grove.scan("proj")
    assert time.perf_counter() - started < BUDGET_SECONDS

    long_lines = result["long_lines"]
    assert long_lines["max_line_chars"] == MAX_LINE_CHARS
    assert long_lines["lines"] == 3
    assert long_lines["files"] == {
        "total": 2,
        "items": [{"path": "README.md", "lines": 1}, {"path": "bundle.js", "lines": 2}],
        "omitted": 0,
    }
    assert any("longer than 5000 characters" in warning and "bundle.js" in warning for warning in result["warnings"])
    # The same report is kept on the project.
    assert grove.project_get("proj")["last_scan"]["long_lines"]["lines"] == 3
    # Everything else in those files was still read.
    assert "ok" in {item["title"] for item in grove.blueprint_get("proj", layer="actual")["items"]}
    assert grove.gaps("proj", kind="declared_untested")["total"] == 1


def test_a_clean_scan_reports_no_long_lines(tiny: Grove) -> None:
    result = tiny.scan("tiny")
    assert result["long_lines"] == {
        "max_line_chars": MAX_LINE_CHARS,
        "lines": 0,
        "files": {"total": 0, "items": [], "omitted": 0},
    }
    assert not any("longer than" in warning for warning in result["warnings"])


def test_map_ingest_reports_long_lines(tiny: Grove, tmp_path: Path) -> None:
    path = tmp_path / "MAP.md"
    path.write_text("# Map\n\nThe widget frobs on demand (documented).\n\n" + "z" * (MAX_LINE_CHARS + 1) + " untested\n")
    result = tiny.ingest_map("tiny", str(path))
    assert result["long_lines"] == {"max_line_chars": MAX_LINE_CHARS, "lines": 1}
    assert result["seeded"] == {"declared": 1, "actual": 0, "map_untested": 0}
    # The stored knowledge document is the whole file, long line included.
    assert tiny.knowledge_get("map", full=True)["body"] == path.read_text()


def test_a_huge_paragraph_is_read_in_linear_time_with_correct_lines() -> None:
    count = 20_000  # took about eight seconds before the line lookup walked forward once
    text = "".join(f"Sentence number {index} is here.\n" for index in range(count))
    items: list = []
    assert timed(lambda: items.extend(extract_declared("docs/big.md", text))) < BUDGET_SECONDS
    assert len(items) == count
    assert [(item.title, item.source_line) for item in (items[0], items[7], items[-1])] == [
        ("Sentence number 0 is here.", 1),
        ("Sentence number 7 is here.", 8),
        (f"Sentence number {count - 1} is here.", count),
    ]


def test_sentences_split_inside_one_line_keep_that_line() -> None:
    items = extract_declared("README.md", "First claim holds. Second claim holds\ntoo. Third claim holds now.\n")
    assert [(item.title, item.source_line) for item in items] == [
        ("First claim holds.", 1),
        ("Second claim holds too.", 1),
        ("Third claim holds now.", 2),
    ]


def test_the_time_cap_is_honoured_inside_one_large_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    sentences = 2000
    (root / "README.md").write_text("# Proj\n\n" + "".join(f"Claim {index} always holds.\n\n" for index in range(sentences)))
    # A clock that moves one millisecond every time it is read: the cap of 0.2
    # seconds runs out after about 200 lines of the one file, on any machine.
    # (No file is slow enough to do that by itself since WO-24.)
    ticks = itertools.count()
    monkeypatch.setattr(scan, "time", SimpleNamespace(monotonic=lambda: next(ticks) / 1000))
    result = scan_tree(root, max_seconds=0.2)
    assert result.caps_hit == ["max_seconds"]
    assert any("max_seconds cap" in warning for warning in result.warnings)
    titles = [item.title for item in result.items]
    assert titles[:2] == ["Proj", "Claim 0 always holds."]  # what was read before the cap is kept
    assert 50 < len(titles) < 250, len(titles)  # it stopped inside the file, not after it


def test_clock_expires_once_and_stays_expired() -> None:
    clock = Clock(time.monotonic() + 60)
    assert clock.over() is False and clock.expired is False
    clock.deadline = time.monotonic() - 1
    assert clock.over() is True and clock.expired is True
    clock.deadline = time.monotonic() + 60
    assert clock.over() is True


def test_a_byte_order_mark_does_not_hide_the_first_line(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_bytes(b"\xef\xbb\xbf# Bom project\n\nIt always frobs the widget.\n")
    (root / "frob.py").write_bytes(b"\xef\xbb\xbfdef first():\n    pass\n\n\ndef second():\n    pass\n")
    grove.project_create("proj", str(root))
    grove.scan("proj")
    declared = grove.blueprint_get("proj", layer="declared")["items"]
    assert declared[0]["title"] == "Bom project" and declared[0]["extra"]["kind"] == "heading"
    names = {item["title"] for item in grove.blueprint_get("proj", layer="actual")["items"]}
    assert {"first", "second"} <= names

    marked = tmp_path / "MAP.md"
    marked.write_bytes("﻿# Marked map\n\nThe widget frobs on demand (documented).\n".encode("utf-8"))
    assert grove.ingest_map("proj", str(marked))["knowledge"]["title"] == "Marked map"
