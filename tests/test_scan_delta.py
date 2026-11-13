"""WO-37, R-SCAN-10: every scan says which findings it added and which it resolved."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sf_grove.cli import main
from sf_grove.service import DELTA_LISTED, Grove
from sf_grove.tools import TOOLS_BY_NAME, call_tool

README = "# Proj\n\n## Behaviours\n\n- Parses a config file.\n- Renders an invoice as text.\n"
CLAIM = "- Exports a ledger as csv.\n"
UNCHANGED = {
    "first_scan": False,
    "added": 0,
    "resolved": 0,
    "added_keys": [],
    "resolved_items": [],
    "list_cap": DELTA_LISTED,
    "complete": True,
    "note": None,
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "README.md").write_text(README)
    # The code names every statement the tests add, so a new statement is one finding (untested), not two.
    (root / "src" / "proj.py").write_text("def parse_config():\n    pass\n\n\ndef export_ledger():\n    pass\n")
    return root


@pytest.fixture
def project(grove: Grove, root: Path) -> Grove:
    grove.project_create("proj", str(root))
    assert grove.scan("proj")["delta"] == {"first_scan": True}
    return grove


def stored(grove: Grove, kind: str | None = None) -> dict[str, dict]:
    page = grove.gaps("proj", kind=kind, limit=200)
    assert page["total"] == len(page["items"])
    return {finding["key"]: finding for finding in page["items"]}


def test_a_first_scan_says_so_and_lists_nothing(grove: Grove, root: Path) -> None:
    grove.project_create("proj", str(root))
    result = grove.scan("proj")
    assert stored(grove), "the project has findings; a first scan still calls none of them added"
    assert result["delta"] == {"first_scan": True}


def test_an_unchanged_rescan_adds_and_resolves_nothing(project: Grove) -> None:
    before = set(stored(project))
    assert before
    assert project.scan("proj")["delta"] == UNCHANGED
    assert set(stored(project)) == before


def test_a_new_test_resolves_exactly_the_finding_it_covers(project: Grove, root: Path) -> None:
    before = stored(project)
    (root / "tests" / "test_config.py").write_text("def test_parses_config():\n    pass\n")
    delta = project.scan("proj")["delta"]
    after = stored(project)
    (gone,) = set(before) - set(after)
    finding = before[gone]
    assert finding["kind"] == "declared_untested" and "Parses a config file." in finding["summary"]
    assert delta == {
        **UNCHANGED,
        "resolved": 1,
        "resolved_items": [{"key": gone, "kind": "declared_untested", "summary": finding["summary"]}],
    }
    assert project.scan("proj")["delta"] == UNCHANGED, "a resolved finding is reported once"


def test_a_new_untested_claim_adds_exactly_its_key(project: Grove, root: Path) -> None:
    before = stored(project)
    (root / "README.md").write_text(README + CLAIM)
    delta = project.scan("proj")["delta"]
    after = stored(project)
    (new,) = set(after) - set(before)
    assert after[new]["kind"] == "declared_untested" and "Exports a ledger as csv." in after[new]["summary"]
    assert delta == {**UNCHANGED, "added": 1, "added_keys": [new]}
    assert project.scan("proj")["delta"] == UNCHANGED, "an added finding is reported once"


def test_a_line_inserted_above_a_claim_is_no_change(project: Grove, root: Path) -> None:
    (root / "README.md").write_text(README.replace("## Behaviours\n", "## Behaviours\n\nA new line of setup.\n"))
    assert project.scan("proj")["delta"] == UNCHANGED


def test_map_findings_are_not_part_of_the_delta(project: Grove, root: Path) -> None:
    map_file = root.parent / "map.md"
    map_file.write_text("# Map\n\n## Risks\n\n- Zork is never exercised. (`untested`)\n")
    project.ingest_map("proj", str(map_file))
    assert stored(project, "map_untested")
    assert project.scan("proj")["delta"] == UNCHANGED
    map_file.write_text("# Map\n\n## Risks\n\nNothing left.\n")
    project.ingest_map("proj", str(map_file))
    assert not stored(project, "map_untested")
    assert project.scan("proj")["delta"] == UNCHANGED


def test_a_map_ingested_before_the_first_scan_does_not_make_it_a_rescan(grove: Grove, root: Path) -> None:
    grove.project_create("proj", str(root))
    map_file = root.parent / "map.md"
    map_file.write_text("# Map\n\n## Risks\n\n- Zork is never exercised. (`untested`)\n")
    grove.ingest_map("proj", str(map_file))
    assert grove.scan("proj")["delta"] == {"first_scan": True}


def test_each_list_is_cut_at_the_cap_and_the_counts_stay_true(project: Grove, root: Path) -> None:
    many = DELTA_LISTED + 7
    claims = "".join(f"- Exports ledger number {number:03d} as csv.\n" for number in range(many))
    (root / "README.md").write_text(README + claims)
    delta = project.scan("proj")["delta"]
    assert delta["added"] == many and delta["resolved"] == 0
    assert len(delta["added_keys"]) == DELTA_LISTED == delta["list_cap"] == 50
    assert delta["complete"] is False and "cut at 50" in delta["note"]
    untested = stored(project, "declared_untested")
    assert set(delta["added_keys"]) < set(untested) and len(set(delta["added_keys"])) == DELTA_LISTED

    (root / "README.md").write_text(README)
    delta = project.scan("proj")["delta"]
    assert delta["resolved"] == many and delta["added"] == 0 and delta["added_keys"] == []
    assert len(delta["resolved_items"]) == DELTA_LISTED
    assert delta["complete"] is False and "cut at 50" in delta["note"]
    for item in delta["resolved_items"]:
        assert sorted(item) == ["key", "kind", "summary"]
        assert untested[item["key"]]["summary"] == item["summary"] and item["kind"] == "declared_untested"

    # Exactly the cap is a whole list.
    (root / "README.md").write_text(README + "".join(claims.splitlines(keepends=True)[:DELTA_LISTED]))
    delta = project.scan("proj")["delta"]
    assert delta["added"] == len(delta["added_keys"]) == DELTA_LISTED and delta["complete"] is True


def test_a_findings_cap_in_either_scan_makes_the_delta_incomplete(project: Grove, root: Path) -> None:
    for number in range(30):  # more undocumented modules than are stored
        (root / "src" / f"quux{number:02d}.py").write_text("def frob():\n    pass\n")
    result = project.scan("proj")
    assert result["findings_cap"]["applied"], "this scan hit the cap"
    assert result["delta"]["added"] > 0
    assert result["delta"]["complete"] is False and "findings_cap" in result["delta"]["note"]

    result = project.scan("proj")  # nothing changed, and both scans were capped
    assert result["findings_cap"]["applied"]
    assert (result["delta"]["added"], result["delta"]["resolved"]) == (0, 0)
    assert result["delta"]["complete"] is False

    for path in (root / "src").glob("quux*.py"):
        path.unlink()
    result = project.scan("proj")  # only the scan before was capped
    assert not result["findings_cap"]["applied"]
    assert result["delta"]["resolved"] > 0
    assert result["delta"]["complete"] is False and "findings_cap" in result["delta"]["note"]

    assert project.scan("proj")["delta"] == UNCHANGED


def test_the_cli_and_the_mcp_tool_report_the_same_delta(
    tmp_path: Path, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def cli(home: Path, *args: str) -> dict:
        assert main(["--home", str(home), *args]) == 0
        return json.loads(capsys.readouterr().out)["data"]

    def mcp(home: Path, tool: str, **arguments) -> dict:
        envelope = call_tool(home, tool, arguments)
        assert envelope["ok"], envelope
        return envelope["data"]

    cli_home, mcp_home = tmp_path / "cli-home", tmp_path / "mcp-home"
    cli(cli_home, "project", "create", "proj", "--root", str(root))
    mcp(mcp_home, "grove_project_create", name="proj", root_path=str(root))

    def scan_both() -> dict:
        by_cli = cli(cli_home, "scan", "proj")["delta"]
        assert mcp(mcp_home, "grove_scan", project="proj")["delta"] == by_cli
        return by_cli

    assert scan_both() == {"first_scan": True}
    assert scan_both() == UNCHANGED
    (root / "README.md").write_text(README + CLAIM)
    added = scan_both()
    assert added["added"] == 1 and added["resolved"] == 0 and len(added["added_keys"]) == 1
    (root / "tests" / "test_ledger.py").write_text("def test_exports_ledger():\n    pass\n")
    resolved = scan_both()
    assert resolved["added"] == 0 and [item["key"] for item in resolved["resolved_items"]] == added["added_keys"]
    assert resolved["resolved_items"][0]["kind"] == "declared_untested"


def test_the_scan_description_names_the_delta() -> None:
    assert "delta (findings added or resolved)" in TOOLS_BY_NAME["grove_scan"].description
