"""Declared sentences are classified so install notes and prose stay off the gap list.

Test names here avoid the words of this repository's own README promises, so a
self-scan of Grove still reports those promises as untested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sf_grove.claims import classify
from sf_grove.service import Grove

README = """# Widget

Widget is the friendly toolkit for config files. It runs locally and does three things:

- Parses config files.
- Not a framework.

## What it is not

It does not talk to GitHub or to any other network service.
Not an AI. v1 calls no model and no embeddings API.
There is no HTTP endpoint to connect to.
It never edits your code, and it does not implement changes.

## Installation

This creates .venv/ with the widget command at .venv/bin/widget. Requires Python 3.13 and uv.
Dependencies are pinned in pyproject.toml and uv.lock.

Run the tests with uv run pytest -q.

## Known limits

Nested parsing blocks can be missed by the parser.
"""

CODE = "def parse_config(path):\n    return path\n\n\ndef parse_blocks(text):\n    return text\n"
TESTS = "def test_parse_config():\n    assert True\n"


@pytest.mark.parametrize(
    ("sentence", "heading"),
    [
        ("This creates .venv/ with the grove command at .venv/bin/grove.", "Install"),
        ("Requires Python 3.13 and uv.", "Install"),
        ("Dependencies are pinned in pyproject.toml and uv.lock.", "Install"),
        ("Run the tests with uv run pytest -q.", "Install"),
        ("Requires Python 3.13 and uv.", "Overview"),
        ("Dependencies are pinned in pyproject.toml and uv.lock.", "Overview"),
        ("Run the tests with uv run pytest -q.", ""),
    ],
)
def test_install_notes_classify_as_setup(sentence: str, heading: str) -> None:
    assert classify(sentence, heading)[0] == "setup"


@pytest.mark.parametrize(
    "sentence",
    [
        "It runs on your own machine and does four things:",
        "If you would rather not point at the virtualenv directly, this is equivalent:",
        "Not an autonomous coder.",
        "Grove is Software Forest's open-source workshop for coding agents.",
    ],
)
def test_lead_ins_and_taglines_classify_as_prose(sentence: str) -> None:
    assert classify(sentence, "What it is not")[0] == "prose"


@pytest.mark.parametrize(
    ("sentence", "heading"),
    [
        ("It does not talk to GitHub or to any other network service.", "What Grove is not"),
        ("Not an AI. v0 calls no model and no embeddings API.", "What Grove is not"),
        ("There is no HTTP endpoint to connect to.", "Install"),
        ("It never edits your code, and it does not implement changes.", ""),
        ("It does not open pull requests.", ""),
        ("Greets a user by name.", "Behaviours"),
    ],
)
def test_promises_classify_as_behaviour(sentence: str, heading: str) -> None:
    assert classify(sentence, heading)[0] == "behaviour"


def test_limit_statements_classify_as_limit() -> None:
    assert classify("The scanner is not a parser.", "Honest limits")[0] == "limit"
    assert classify("Definitions split across lines can be missed.", "Notes")[0] == "limit"


@pytest.fixture
def widget(grove: Grove, tmp_path: Path) -> Grove:
    root = tmp_path / "widget"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "README.md").write_text(README)
    (root / "src" / "parse.py").write_text(CODE)
    (root / "tests" / "test_parse.py").write_text(TESTS)
    grove.project_create("widget", str(root))
    grove.scan("widget")
    return grove


def _summaries(grove: Grove) -> str:
    return "\n".join(finding["summary"] for finding in grove.gaps("widget", limit=200)["items"])


def test_setup_and_prose_sentences_raise_no_gap(widget: Grove) -> None:
    summaries = _summaries(widget)
    for noise in ("does three things", "Not a framework", "creates .venv", "Requires Python", "pinned in", "Run the tests"):
        assert noise not in summaries
    declared = widget.blueprint_get("widget", layer="declared", limit=200)["items"]
    by_title = {item["title"]: item["extra"] for item in declared if item["extra"]["kind"] == "sentence"}
    assert by_title["Requires Python 3.13 and uv."]["class"] == "setup"
    assert by_title["Requires Python 3.13 and uv."]["class_reason"]
    notes = widget.scan("widget")["gap_notes"]
    assert notes["declared_skipped"]["setup"] >= 4 and notes["declared_skipped"]["prose"] >= 2


def test_negative_promises_still_raise_gaps(widget: Grove) -> None:
    summaries = _summaries(widget)
    for promise in (
        "It does not talk to GitHub or to any other network service.",
        "v1 calls no model and no embeddings API.",
        "There is no HTTP endpoint to connect to.",
        "It never edits your code, and it does not implement changes.",
    ):
        assert promise in summaries
    for finding in widget.gaps("widget", kind="declared_untested", limit=200)["items"]:
        assert finding["evidence"]["class"] in ("behaviour", "limit")
        assert finding["evidence"]["class_reason"]


def test_recommend_prefers_a_promise_over_a_limit(widget: Grove) -> None:
    findings = widget.gaps("widget", kind="declared_untested", limit=200)["items"]
    limit = [finding for finding in findings if finding["evidence"]["class"] == "limit"]
    # The limit shares a name with the code (parse_blocks) yet must not win.
    assert limit and limit[0]["evidence"]["seen_in_actual"] is True
    assert max(f["id"] for f in findings if f["evidence"]["class"] == "behaviour") < limit[0]["id"]
    recommendation = widget.recommend_next("widget")
    assert recommendation["finding"]["evidence"]["class"] == "behaviour"
    assert "[limit]" not in recommendation["finding"]["summary"]


def test_recommend_falls_back_to_a_limit_last(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "limits"
    root.mkdir()
    (root / "README.md").write_text("# Thing\n\n## Caveats\n\nNested parsing blocks can be missed.\n")
    grove.project_create("limits", str(root))
    grove.scan("limits")
    recommendation = grove.recommend_next("limits")
    assert recommendation["action"] == "check_documented_limit"
    assert recommendation["finding"]["evidence"]["class"] == "limit"
