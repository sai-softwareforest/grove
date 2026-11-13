"""Requirement 4: MAP ingest on fixtures/map_sample.md."""

from __future__ import annotations

import pytest

from conftest import MAP_SAMPLE
from sf_grove.errors import GroveError
from sf_grove.mapdoc import parse_map
from sf_grove.service import Grove


def test_ingest_stores_knowledge_and_seeds_items_and_findings(tiny: Grove) -> None:
    before = MAP_SAMPLE.read_bytes()
    result = tiny.ingest_map("tiny", str(MAP_SAMPLE))

    assert result["knowledge"]["key"] == "map_sample"
    assert result["knowledge"]["revision"] == 1
    document = tiny.knowledge_get("map_sample", project="tiny")
    assert document["body"] == before.decode("utf-8")
    assert document["title"].startswith("Tiny")
    assert tiny.knowledge_search("greeting string")["items"][0]["key"] == "map_sample"

    assert result["seeded"]["declared"] >= 1
    assert result["seeded"]["actual"] >= 1
    assert result["seeded"]["map_untested"] >= 1

    declared = [item for item in tiny.blueprint_get("tiny", layer="declared")["items"] if item["origin"] == "map"]
    actual = [item for item in tiny.blueprint_get("tiny", layer="actual")["items"] if item["origin"] == "map"]
    assert declared and actual
    assert all(item["source_path"] == str(MAP_SAMPLE) and item["source_line"] > 0 for item in declared + actual)
    assert any("Purpose" in item["extra"]["heading"] for item in declared)
    assert any("greet.py" in item["title"] for item in actual)  # table row under a labelled header

    untested = tiny.gaps("tiny", kind="map_untested")
    assert untested["total"] == result["seeded"]["map_untested"]
    for finding in untested["items"]:
        assert finding["confidence"] == "heuristic"
        assert finding["evidence"]["source_path"] == str(MAP_SAMPLE)
        assert "Risks" in finding["evidence"]["heading"]

    assert MAP_SAMPLE.read_bytes() == before, "ingest must not write to the map file"


def test_legend_and_code_fences_are_not_seeded() -> None:
    blocks = parse_map(MAP_SAMPLE.read_text(encoding="utf-8"))
    texts = [block.text for block in blocks]
    assert not [text for text in texts if "code fence" in text]
    assert not [text for text in texts if text.startswith(("documented —", "observed-in-code —", "untested —"))]
    both = next(block for block in blocks if "no test file" in block.text)
    assert both.labels == ["observed-in-code", "untested"]


def test_reingest_adds_a_revision_without_duplicating(tiny: Grove) -> None:
    first = tiny.ingest_map("tiny", str(MAP_SAMPLE))
    second = tiny.ingest_map("tiny", str(MAP_SAMPLE))
    assert second["knowledge"]["revision"] == 2
    assert second["seeded"] == first["seeded"]
    assert tiny.gaps("tiny", kind="map_untested")["total"] == first["seeded"]["map_untested"]
    map_items = [item for item in tiny.blueprint_get("tiny", limit=200)["items"] if item["origin"] == "map"]
    assert len(map_items) == first["seeded"]["declared"] + first["seeded"]["actual"]


def test_rescan_keeps_map_items_and_map_findings(tiny: Grove) -> None:
    tiny.scan("tiny")
    ingested = tiny.ingest_map("tiny", str(MAP_SAMPLE))
    rescanned = tiny.scan("tiny")
    assert rescanned["findings"]["map_untested"] == ingested["seeded"]["map_untested"]
    origins = {item["origin"] for item in tiny.blueprint_get("tiny", limit=200)["items"]}
    assert origins == {"scan", "map"}
    assert tiny.recommend_next("tiny")["finding"]["kind"] == "map_untested"


def test_ingest_before_any_scan_skips_token_gaps(tiny: Grove) -> None:
    result = tiny.ingest_map("tiny", str(MAP_SAMPLE))
    assert "skipped" in result["gap_notes"]
    assert result["findings"]["declared_untested"] == 0
    assert result["findings"]["map_untested"] >= 1


def test_ingest_errors(tiny: Grove, tmp_path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("")
    for path, code in ((tmp_path / "missing.md", "not_found"), (tmp_path, "invalid"), (empty, "invalid")):
        with pytest.raises(GroveError) as raised:
            tiny.ingest_map("tiny", str(path))
        assert raised.value.code == code


# -- only map-like files are read (R-SEC-5) -----------------------------------

A_MAP = "# Map\n\nThe widget frobs on demand (documented).\n"


def test_the_accepted_extensions_are_the_ones_in_the_requirement() -> None:
    # The list is the scanner's. Widening it there widens ingest-map: change R-SEC-5 first.
    from sf_grove.scan import DOC_EXTENSIONS

    assert sorted(DOC_EXTENSIONS) == ["", ".markdown", ".md", ".mdx", ".rst", ".txt"]


@pytest.mark.parametrize(
    "name",
    ["MAP.md", "map.markdown", "map.mdx", "map.rst", "map.txt", "MAP", "MAP.MD", "Map.Markdown", "map.v2.md", ".map.md"],
)
def test_a_map_like_file_name_is_accepted(tiny: Grove, tmp_path, name: str) -> None:
    path = tmp_path / name
    path.write_text(A_MAP, encoding="utf-8")
    assert tiny.ingest_map("tiny", str(path))["seeded"] == {"declared": 1, "actual": 0, "map_untested": 0}


@pytest.mark.parametrize(
    "name",
    ["map.py", "map.json", "map.html", "map.pdf", "map.md.bak", "map.md~", "map.mdown", "MAP.", ".env", ".netrc", "prod.ENV"],
)
def test_any_other_file_name_is_refused_and_nothing_is_stored(tiny: Grove, tmp_path, name: str) -> None:
    path = tmp_path / name
    path.write_text(A_MAP, encoding="utf-8")
    with pytest.raises(GroveError) as raised:
        tiny.ingest_map("tiny", str(path))
    assert raised.value.code == "invalid"
    # The message is where a client learns the rule: it names what was refused and what is accepted.
    message = raised.value.message
    assert str(path) in message and "extension" in message
    for accepted in (".md", ".markdown", ".mdx", ".rst", ".txt", "without an extension"):
        assert accepted in message, accepted
    assert tiny.knowledge_search(None, project="tiny")["total"] == 0
    assert tiny.blueprint_get("tiny")["total"] == 0
    assert tiny.gaps("tiny")["total"] == 0


def test_the_name_is_judged_before_the_file_is_touched(tiny: Grove, tmp_path) -> None:
    # A file Grove would not read is not looked for: the answer is the same whether it exists or not.
    for path, code in ((tmp_path / "missing.py", "invalid"), (tmp_path / "missing.md", "not_found")):
        with pytest.raises(GroveError) as raised:
            tiny.ingest_map("tiny", str(path))
        assert raised.value.code == code


def test_the_name_that_counts_is_the_file_a_link_leads_to(tiny: Grove, tmp_path) -> None:
    secret = tmp_path / "settings.json"
    secret.write_text(A_MAP, encoding="utf-8")
    real = tmp_path / "MAP.md"
    real.write_text(A_MAP, encoding="utf-8")
    (tmp_path / "looks-like-a-map.md").symlink_to(secret)
    (tmp_path / "current.json").symlink_to(real)

    with pytest.raises(GroveError) as raised:
        tiny.ingest_map("tiny", str(tmp_path / "looks-like-a-map.md"))
    assert raised.value.code == "invalid" and str(secret) in raised.value.message
    # The other way round is the map itself: the key and the path are the real file's, as they always were.
    result = tiny.ingest_map("tiny", str(tmp_path / "current.json"))
    assert result["path"] == str(real.resolve()) and result["knowledge"]["key"] == "map"


# -- legends are not findings ------------------------------------------------

# Shapes seen in real maps during the team trial.
OBSERVED_LEGEND_PARAGRAPH = """\
# rust-sdk map

**Evidence labels.** Each statement below carries one or more labels: documented (the project's
docs say so), observed-in-code (read in the source), untested (no test was found).

## Transport

The stdio transport frames each message with a newline (`observed-in-code`, `untested`).
"""

OBSERVED_LEAD_IN = """\
# mcp-memory map

## Storage

**Missing — untested:**

- Reconnect after the database file is replaced underneath the server.
- Concurrent writers from two processes.

A later paragraph ends that list (`documented`).

- Missing — untested:
  - nested retry claim under a list-item lead-in
- a sibling item that must not inherit the label
"""


def test_observed_legend_paragraph_is_not_seeded() -> None:
    blocks = parse_map(OBSERVED_LEGEND_PARAGRAPH)
    assert [block.text for block in blocks] == [
        "The stdio transport frames each message with a newline (observed-in-code, untested)."
    ]


def test_observed_lead_in_is_not_a_finding_but_labels_its_list() -> None:
    blocks = parse_map(OBSERVED_LEAD_IN)
    texts = [block.text for block in blocks]
    assert not [text for text in texts if text.startswith("Missing")]
    by_text = {block.text: block.labels for block in blocks}
    assert by_text["Reconnect after the database file is replaced underneath the server."] == ["untested"]
    assert by_text["Concurrent writers from two processes."] == ["untested"]
    assert by_text["A later paragraph ends that list (documented)."] == ["documented"]
    assert by_text["nested retry claim under a list-item lead-in"] == ["untested"]
    assert "a sibling item that must not inherit the label" not in by_text


@pytest.mark.parametrize(
    "legend",
    [
        "Legend: documented / observed-in-code / untested.",
        "This map marks claims `documented`: stated in docs; `observed-in-code`: read in source; `untested`: no test.",
        "Claims are tagged documented (stated in the README) or untested (no test found).",
        "We use the label `untested` for anything no test exercises.",
        "untested — no test was found for it.",  # begins with a label (old rule, kept)
        "Untested: retries on timeout.",  # a real finding written label-first is skipped too (documented limit)
    ],
)
def test_legend_shapes_are_skipped(legend: str) -> None:
    assert parse_map(f"# Map\n\n## Notes\n\n{legend}\n") == []


def test_legend_section_and_legend_heading_pass_nothing_down() -> None:
    text = (
        "# Map\n\n## Evidence labels\n\nAnything here is legend, even untested prose about labels.\n\n"
        "| Label | Meaning |\n|---|---|\n| untested | no test found |\n\n"
        "## Labels: documented, observed-in-code, untested\n\nPlain sentence with no label of its own.\n\n"
        "## Parser (untested)\n\nThe parser accepts tabs as indentation.\n"
    )
    blocks = parse_map(text)
    assert [(block.text, block.labels) for block in blocks] == [
        ("The parser accepts tabs as indentation.", ["untested"])
    ]


def test_ingested_legend_never_becomes_the_recommendation(tiny: Grove, tmp_path) -> None:
    path = tmp_path / "MAP.md"
    path.write_text(OBSERVED_LEGEND_PARAGRAPH + "\n" + OBSERVED_LEAD_IN.split("\n", 1)[1], encoding="utf-8")
    tiny.scan("tiny")
    result = tiny.ingest_map("tiny", str(path))
    summaries = [finding["summary"] for finding in tiny.gaps("tiny", kind="map_untested")["items"]]
    assert result["seeded"]["map_untested"] == len(summaries) == 4
    assert not [summary for summary in summaries if "label" in summary.lower() or "Missing" in summary]
    recommended = tiny.recommend_next("tiny")["finding"]["summary"]
    assert "stdio transport" in recommended
