"""WO-38, R-GAP-6: `gaps` takes `query`, text to find in a finding.

The text is looked for in the summary, in the source path of the evidence and
in the key, whatever the case of ASCII letters; `%` and `_` stand for
themselves. It combines with `kind`. `total` follows both filters, `counts`
follows the text and stays per kind. A blank or absent query is no filter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import MAP_SAMPLE, TINY
from sf_grove.cli import main
from sf_grove.errors import GroveError
from sf_grove.service import Grove
from sf_grove.tools import TOOLS_BY_NAME, call_tool

KINDS = ("declared_untested", "declared_unseen", "actual_undocumented", "map_untested")


@pytest.fixture
def mapped(tiny: Grove) -> Grove:
    """The fixture project, scanned and with a map: findings of three kinds."""
    tiny.scan("tiny")
    tiny.ingest_map("tiny", str(MAP_SAMPLE))
    return tiny


@pytest.fixture
def odd(grove: Grove, tmp_path: Path) -> Grove:
    """A project whose statements and paths hold `%` and `_`, each beside a near twin without it."""
    root = tmp_path / "odd"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text(
        "# Odd\n\nIt always rounds to 100% of the quota.\n\nIt always rounds to 1000 of the quota.\n", encoding="utf-8"
    )
    (root / "docs" / "a_b.md").write_text("# Under\n\nIt always frobs the widget.\n", encoding="utf-8")
    (root / "docs" / "axb.md").write_text("# Plain\n\nIt always greps the gadget.\n", encoding="utf-8")
    grove.project_create("odd", str(root))
    grove.scan("odd")
    return grove


def everything(grove: Grove, project: str) -> list[dict]:
    return grove.gaps(project, limit=200)["items"]


def keys(result: dict) -> list[str]:
    return [finding["key"] for finding in result["items"]]


def test_a_path_returns_only_the_findings_of_that_file(mapped: Grove) -> None:
    listed = mapped.gaps("tiny", query="README.md")
    assert listed["total"] == len(listed["items"]) >= 1
    assert {finding["evidence"].get("source_path") for finding in listed["items"]} == {"README.md"}
    expected = [f["key"] for f in everything(mapped, "tiny") if f["evidence"].get("source_path") == "README.md"]
    assert keys(listed) == expected
    assert listed["total"] < mapped.gaps("tiny")["total"]


def test_the_case_of_the_text_does_not_matter(mapped: Grove) -> None:
    assert mapped.gaps("tiny", query="readme.MD") == mapped.gaps("tiny", query="README.md")
    assert mapped.gaps("tiny", query="  README.md\n") == mapped.gaps("tiny", query="README.md")


def test_words_of_the_summary_are_found(mapped: Grove) -> None:
    listed = mapped.gaps("tiny", query="is not mentioned in the declared layer")
    assert listed["total"] >= 1
    assert {finding["kind"] for finding in listed["items"]} == {"actual_undocumented"}
    # Not through the path: an undocumented module has no source_path in its evidence.
    assert all("source_path" not in finding["evidence"] for finding in listed["items"])
    assert keys(mapped.gaps("tiny", query="src/tiny/calc.py")) == keys(listed)


def test_a_full_key_returns_that_one_finding(mapped: Grove) -> None:
    findings = everything(mapped, "tiny")
    assert len(findings) >= 3
    for finding in findings:
        listed = mapped.gaps("tiny", query=finding["key"])
        assert listed["items"] == [finding] and listed["total"] == 1
        assert mapped.gaps("tiny", query=finding["key"].upper())["items"] == [finding]
        assert mapped.gaps("tiny", query=finding["key"][2:9])["items"] == [finding]


def test_text_that_is_nowhere_gives_an_empty_page_and_no_error(mapped: Grove) -> None:
    listed = mapped.gaps("tiny", query="no finding says this")
    assert (listed["items"], listed["total"]) == ([], 0)
    assert listed["counts"] == dict.fromkeys(KINDS, 0)


def test_percent_and_underscore_are_read_as_themselves(odd: Grove) -> None:
    findings = everything(odd, "odd")
    summaries = [finding["summary"] for finding in findings]
    assert any("100%" in summary for summary in summaries) and any("1000 of" in summary for summary in summaries)

    def matching(text: str) -> list[str]:
        return [
            f["key"]
            for f in findings
            if text in f["summary"].lower() or text in f["evidence"].get("source_path", "").lower() or text in f["key"]
        ]

    for text in ("100%", "a_b", "%", "_", "100% of", "docs/a_b.md"):
        assert keys(odd.gaps("odd", query=text, limit=200)) == matching(text) != [], text
    # As wildcards these would match: `100_` the twin "1000", `a_b` the path axb.md, `%` everything.
    assert keys(odd.gaps("odd", query="100_")) == []
    assert keys(odd.gaps("odd", query="a%b")) == []
    assert {f["evidence"]["source_path"] for f in odd.gaps("odd", query="a_b")["items"]} == {"docs/a_b.md"}
    assert len(matching("%")) < len(findings)
    assert keys(odd.gaps("odd", query="\\")) == []


def test_query_and_kind_narrow_together(mapped: Grove) -> None:
    findings = everything(mapped, "tiny")
    text = "greet"
    hits = [f for f in findings if text in f["summary"].lower()]
    assert len({f["kind"] for f in hits}) >= 2, "the fixture must match in more than one kind"
    for kind in KINDS:
        listed = mapped.gaps("tiny", kind=kind, query=text)
        assert keys(listed) == [f["key"] for f in hits if f["kind"] == kind]
        assert listed["total"] == len(listed["items"])
    with pytest.raises(GroveError) as caught:
        mapped.gaps("tiny", kind="map_untestd", query=text)
    assert caught.value.code == "invalid"


def test_total_and_counts_follow_the_query(mapped: Grove) -> None:
    findings = everything(mapped, "tiny")
    unfiltered = mapped.gaps("tiny")
    text = "greet"
    hits = [f for f in findings if text in f["summary"].lower()]
    expected = {kind: sum(1 for f in hits if f["kind"] == kind) for kind in KINDS}
    listed = mapped.gaps("tiny", query=text)
    assert listed["total"] == len(hits) < unfiltered["total"]
    assert listed["counts"] == expected != unfiltered["counts"]
    assert sum(listed["counts"].values()) == listed["total"]
    # With a kind as well: the total is that kind's count, and the counts still show every kind.
    for kind in KINDS:
        both = mapped.gaps("tiny", kind=kind, query=text)
        assert both["total"] == expected[kind] and both["counts"] == expected
    # Paging counts the filtered set.
    first = mapped.gaps("tiny", query=text, limit=1)
    assert first["total"] == len(hits) and len(first["items"]) == 1
    assert keys(mapped.gaps("tiny", query=text, limit=1, offset=1)) == [hits[1]["key"]]


def test_complete_follows_the_filters(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "many"
    (root / "pkg").mkdir(parents=True)
    (root / "README.md").write_text("# Many\n\nIt always frobs the widget.\n", encoding="utf-8")
    for index in range(30):  # more undocumented modules than the cap of 25 stores
        (root / "pkg" / f"zorka{chr(97 + index % 26)}{index // 26}.py").write_text("def f():\n    pass\n", encoding="utf-8")
    grove.project_create("many", str(root))
    grove.scan("many")
    capped = grove.gaps("many", kind="actual_undocumented")
    assert capped["complete"] is False and capped["omitted"] > 0
    # The omitted candidates were never stored, so a query cannot rule them out.
    listed = grove.gaps("many", query="pkg/zorka")
    assert listed["total"] == capped["total"] == 25
    assert listed["complete"] is False and listed["omitted"] == capped["omitted"]
    assert listed["true_total"] == listed["total"] + listed["omitted"]
    # A kind that no cap touched is complete, with or without the text.
    for query in (None, "README.md", "nowhere"):
        other = grove.gaps("many", kind="declared_untested", query=query)
        assert other["complete"] is True and other["omitted"] == 0 and other["true_total"] == other["total"]


@pytest.mark.parametrize("query", [None, "", "   ", "\t\n"])
def test_a_blank_or_absent_query_is_no_filter(mapped: Grove, query: str | None) -> None:
    assert mapped.gaps("tiny", query=query) == mapped.gaps("tiny")
    assert mapped.gaps("tiny", kind="map_untested", query=query) == mapped.gaps("tiny", kind="map_untested")
    assert mapped.gaps("tiny")["total"] > 0


@pytest.mark.parametrize("query", [7, True, 1.5, ["README.md"], {"query": "README.md"}])
def test_a_query_that_is_not_text_is_invalid(mapped: Grove, query: object) -> None:
    with pytest.raises(GroveError) as caught:
        mapped.gaps("tiny", query=query)
    assert (caught.value.code, caught.value.message) == ("invalid", "query must be a string")


def test_a_query_longer_than_200_characters_is_invalid(mapped: Grove) -> None:
    assert mapped.gaps("tiny", query="q" * 200)["total"] == 0
    with pytest.raises(GroveError) as caught:
        mapped.gaps("tiny", query="q" * 201)
    assert (caught.value.code, caught.value.message) == ("invalid", "query is longer than 200 characters")


def test_blueprint_get_escapes_as_before(odd: Grove) -> None:
    # The pattern is built by the one helper both operations use.
    assert odd.blueprint_get("odd", query="100%")["total"] >= 1
    assert odd.blueprint_get("odd", query="100_")["total"] == 0
    paths = {item["source_path"] for item in odd.blueprint_get("odd", query="a_b")["items"]}
    assert paths == {"docs/a_b.md"}


@pytest.fixture
def cli(home: Path, capsys: pytest.CaptureFixture[str]):
    def invoke(*args: str) -> tuple[int, dict]:
        code = main(["--home", str(home), *args])
        return code, json.loads(capsys.readouterr().out)

    return invoke


@pytest.fixture
def stored(cli, home: Path) -> Path:
    for args in (("project", "create", "tiny", "--root", str(TINY)), ("scan", "tiny"), ("ingest-map", "tiny", str(MAP_SAMPLE))):
        assert cli(*args)[0] == 0
    return home


def test_the_cli_and_the_mcp_tool_give_the_same_answer(cli, stored: Path) -> None:
    code, unfiltered = cli("gaps", "tiny")
    assert code == 0 and unfiltered["data"]["total"] > 1
    key = unfiltered["data"]["items"][0]["key"]
    for query in ("README.md", "readme.md", "greet", key, "%", "_", "nowhere at all", ""):
        code, out = cli("gaps", "tiny", "--query", query)
        assert code == 0 and out["ok"] is True
        assert call_tool(stored, "grove_gaps", {"project": "tiny", "query": query}) == out, query
    code, out = cli("gaps", "tiny", "--query", "README.md")
    assert {f["evidence"].get("source_path") for f in out["data"]["items"]} == {"README.md"}
    assert 0 < out["data"]["total"] < unfiltered["data"]["total"]
    assert cli("gaps", "tiny", "--query", key)[1]["data"]["total"] == 1
    assert cli("gaps", "tiny", "--query", "")[1] == unfiltered
    assert call_tool(stored, "grove_gaps", {"project": "tiny", "query": None}) == unfiltered
    code, out = cli("gaps", "tiny", "--kind", "map_untested", "--query=greet", "--limit", "1")
    assert code == 0 and out["data"]["total"] >= 1 and len(out["data"]["items"]) == 1
    assert call_tool(stored, "grove_gaps", {"project": "tiny", "kind": "map_untested", "query": "greet", "limit": 1}) == out


def test_both_surfaces_refuse_a_bad_query_alike(cli, stored: Path) -> None:
    refused = {"ok": False, "error": {"code": "invalid", "message": "query is longer than 200 characters"}}
    assert cli("gaps", "tiny", "--query", "q" * 201) == (1, refused)
    assert call_tool(stored, "grove_gaps", {"project": "tiny", "query": "q" * 201}) == refused
    assert call_tool(stored, "grove_gaps", {"project": "tiny", "query": 7})["error"] == {
        "code": "invalid",
        "message": "query must be a string",
    }


def test_what_an_mcp_client_reads_about_query() -> None:
    tool = TOOLS_BY_NAME["grove_gaps"]
    assert tool.schema["properties"]["query"] == {"type": "string"}
    assert tool.schema["required"] == ["project"]
    assert "query filters by text." in tool.description
