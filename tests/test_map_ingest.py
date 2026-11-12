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
