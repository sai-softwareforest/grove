"""Requirement 1: scan + gaps on fixtures/tiny."""

from __future__ import annotations

from sf_grove.service import Grove


def all_items(grove: Grove, layer: str) -> list[dict]:
    return grove.blueprint_get("tiny", layer=layer, limit=200)["items"]


def test_scan_reports_three_layers(tiny: Grove) -> None:
    summary = tiny.scan("tiny")
    assert summary["items"]["declared"] > 0
    assert summary["items"]["actual"] > 0
    assert summary["items"]["tests"] > 0
    assert summary["caps"]["hit"] == []
    assert set(summary["findings"]) >= {"declared_untested", "declared_unseen", "actual_undocumented", "map_untested"}
    assert summary["sample_findings"], "the scan result should carry a sample of findings"


def test_actual_layer_sees_both_functions(tiny: Grove) -> None:
    tiny.scan("tiny")
    actual = all_items(tiny, "actual")
    symbols = {(item["title"], item["source_path"]) for item in actual if item["extra"]["kind"] == "function"}
    assert ("add", "src/tiny/calc.py") in symbols
    assert ("greet", "src/tiny/greet.py") in symbols
    modules = {item["title"] for item in actual if item["extra"]["kind"] == "module"}
    assert {"src/tiny/calc.py", "src/tiny/greet.py"} <= modules
    assert all(item["source_line"] >= 1 for item in actual)


def test_tests_layer_finds_only_the_calc_test(tiny: Grove) -> None:
    tiny.scan("tiny")
    tests = all_items(tiny, "tests")
    names = {item["title"] for item in tests if item["extra"]["kind"] == "test"}
    assert names == {"test_add_two_integers"}
    assert {item["source_path"] for item in tests} == {"tests/test_calc.py"}
    # Test files are not double-counted as modules.
    assert not [item for item in all_items(tiny, "actual") if item["source_path"].startswith("tests/")]


def test_greet_is_declared_untested_and_add_is_not(tiny: Grove) -> None:
    tiny.scan("tiny")
    untested = tiny.gaps("tiny", kind="declared_untested")
    assert untested["total"] >= 1
    assert untested["counts"]["declared_untested"] == untested["total"]
    summaries = " ".join(finding["summary"].lower() for finding in untested["items"])
    assert "greet" in summaries
    assert "adds two integers" not in summaries
    for finding in untested["items"]:
        assert finding["kind"] == "declared_untested"
        assert finding["confidence"] == "heuristic"
        assert finding["evidence"]["item_ids"]
        assert finding["evidence"]["source_path"] == "README.md"
    greet = next(finding for finding in untested["items"] if "greet" in finding["summary"].lower())
    # The greet claim is seen in code (greet.py / def greet), so it is not declared_unseen.
    assert greet["evidence"]["seen_in_actual"] is True
    unseen = tiny.gaps("tiny", kind="declared_unseen")["items"]
    assert not [finding for finding in unseen if "greet" in finding["summary"].lower()]


def test_every_finding_is_labelled_heuristic(tiny: Grove) -> None:
    tiny.scan("tiny")
    findings = tiny.gaps("tiny", limit=200)["items"]
    assert findings
    assert {finding["confidence"] for finding in findings} == {"heuristic"}


def test_gaps_are_paged(tiny: Grove) -> None:
    tiny.scan("tiny")
    everything = tiny.gaps("tiny", limit=200)
    assert everything["total"] >= 2
    first = tiny.gaps("tiny", limit=1)
    second = tiny.gaps("tiny", limit=1, offset=1)
    assert first["limit"] == 1 and first["offset"] == 0 and len(first["items"]) == 1
    assert second["offset"] == 1 and len(second["items"]) == 1
    assert first["total"] == second["total"] == everything["total"]
    assert first["items"][0]["id"] != second["items"][0]["id"]


def test_rescan_replaces_scan_items_but_keeps_everything_else(tiny: Grove) -> None:
    first = tiny.scan("tiny")
    tiny.knowledge_write("tiny", "note", "A note", "Keep me across rescans.")
    work = tiny.work_create("tiny", "Write a greet test")
    second = tiny.scan("tiny")
    assert second["items"] == first["items"]
    assert second["findings"] == first["findings"]
    assert tiny.knowledge_get("note")["body"] == "Keep me across rescans."
    assert tiny.work_get(work["id"])["status"] == "ready"


def test_blueprint_query_and_layer_filter(tiny: Grove) -> None:
    tiny.scan("tiny")
    hits = tiny.blueprint_get("tiny", query="greet")
    assert hits["total"] >= 2
    assert {item["layer"] for item in hits["items"]} >= {"declared", "actual"}
    declared = tiny.blueprint_get("tiny", layer="declared", query="GREET")
    assert declared["total"] == 1
    assert declared["items"][0]["source_path"] == "README.md"
    assert declared["items"][0]["source_line"] == 6


def test_recommend_prefers_the_untested_claim_seen_in_code(tiny: Grove) -> None:
    assert tiny.recommend_next("tiny")["action"] == "scan"
    tiny.scan("tiny")
    recommendation = tiny.recommend_next("tiny")
    assert recommendation["finding"]["kind"] == "declared_untested"
    assert "greet" in recommendation["finding"]["summary"].lower()
    assert recommendation["finding_ids"] == [recommendation["finding"]["id"]]
    assert recommendation["rationale"]
