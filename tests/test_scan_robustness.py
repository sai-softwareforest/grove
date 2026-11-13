"""R-SCAN-7, R-SCAN-8: scan time is bounded by input size, and what is skipped is reported."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from sf_grove import mapdoc, scan
from sf_grove.scan import MAX_LINE_CHARS, Clock, extract_declared, extract_symbols, extract_test_names, scan_tree
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


def test_a_worst_case_line_under_the_cap_stays_cheap() -> None:
    # The patterns are still quadratic below the cap; the cap is what keeps that small.
    assert timed(lambda: extract_declared("README.md", "a " + "[" * (MAX_LINE_CHARS - 2) + "\n")) < 2.0


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


def test_the_time_cap_is_honoured_inside_one_large_file(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    # One file whose analysis takes far longer than the cap: many worst-case lines just under the line cap.
    line = "a " + "[" * (MAX_LINE_CHARS - 2)
    (root / "README.md").write_text("# Proj\n\n" + "\n\n".join([line] * 90) + "\n")
    started = time.perf_counter()
    result = scan_tree(root, max_seconds=0.2)
    elapsed = time.perf_counter() - started
    assert result.caps_hit == ["max_seconds"]
    assert any("max_seconds cap" in warning for warning in result.warnings)
    assert elapsed < 3.0, elapsed  # without the in-file check this file alone takes several seconds
    assert [item.title for item in result.items][:1] == ["Proj"]  # what was read before the cap is kept


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
