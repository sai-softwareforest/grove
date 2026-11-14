"""A misspelt finding kind is an error that lists the kinds, not an empty page (R-GAP-5).

The service checks `kind`, so the CLI and the MCP tool refuse the same input
with the same envelope. What worked before still works: no kind, a blank
kind and a kind with spaces around it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import MAP_SAMPLE, TINY
from sf_grove.cli import build_parser, main
from sf_grove.errors import GroveError
from sf_grove.service import FINDING_KINDS, Grove
from sf_grove.tools import TOOLS_BY_NAME, call_tool

KINDS = ("declared_untested", "declared_unseen", "actual_undocumented", "map_untested")  # R-GAP-1
# The error also offers `lesson`, which is no finding kind: it asks `gaps` for the Prism review pack (R-PRISM-6).
OFFERED = KINDS + ("lesson",)
MESSAGE = "kind must be one of declared_untested, declared_unseen, actual_undocumented, map_untested, lesson"
REFUSED = {"ok": False, "error": {"code": "invalid", "message": MESSAGE}}

MISSPELT = [
    "declared_untestd",
    "Declared_Untested",
    "declared-untested",
    "untested",
    "declared_untested,map_untested",
    "declared_untested map_untested",
    "*",
    "%",
    "k" * 61,
    "k" * 5000,
]


@pytest.fixture
def mapped(tiny: Grove) -> Grove:
    """The fixture project, scanned and with a map: findings of more than one kind."""
    tiny.scan("tiny")
    tiny.ingest_map("tiny", str(MAP_SAMPLE))
    return tiny


def refusal(call) -> GroveError:
    with pytest.raises(GroveError) as caught:
        call()
    return caught.value


def test_the_kinds_are_the_documented_four() -> None:
    assert FINDING_KINDS == KINDS


@pytest.mark.parametrize("kind", MISSPELT)
def test_a_misspelt_kind_is_invalid_and_the_message_lists_the_kinds(mapped: Grove, kind: str) -> None:
    error = refusal(lambda: mapped.gaps("tiny", kind=kind))
    assert (error.code, error.message) == ("invalid", MESSAGE)


def test_a_misspelt_kind_is_invalid_before_the_first_scan_too(tiny: Grove) -> None:
    # No finding exists yet, so every page is empty; the typo is still told apart from that.
    assert tiny.gaps("tiny")["total"] == 0
    assert tiny.gaps("tiny", kind="map_untested")["total"] == 0
    assert refusal(lambda: tiny.gaps("tiny", kind="map_untestd")).message == MESSAGE


def test_every_kind_still_filters(mapped: Grove) -> None:
    everything = mapped.gaps("tiny", limit=200)
    assert everything["counts"]["declared_untested"] >= 1 and everything["counts"]["map_untested"] >= 1
    totals = 0
    for kind in KINDS:
        listed = mapped.gaps("tiny", kind=kind, limit=200)
        assert listed["total"] == everything["counts"][kind]
        assert {finding["kind"] for finding in listed["items"]} <= {kind}
        totals += listed["total"]
    assert totals == everything["total"]


@pytest.mark.parametrize("kind", [None, "", "   ", "\t\n"])
def test_no_kind_and_a_blank_kind_list_every_finding_as_before(mapped: Grove, kind: str | None) -> None:
    assert mapped.gaps("tiny", kind=kind) == mapped.gaps("tiny")
    assert mapped.gaps("tiny")["total"] == sum(mapped.gaps("tiny")["counts"].values()) > 0


def test_spaces_around_a_kind_are_ignored_as_before(mapped: Grove) -> None:
    assert mapped.gaps("tiny", kind="  map_untested\n") == mapped.gaps("tiny", kind="map_untested")


@pytest.mark.parametrize("kind", [7, True, 1.5, ["declared_untested"], {"kind": "declared_untested"}])
def test_a_kind_that_is_not_text_is_invalid(mapped: Grove, kind: object) -> None:
    error = refusal(lambda: mapped.gaps("tiny", kind=kind))
    assert (error.code, error.message) == ("invalid", "kind must be a string")


def test_an_unknown_project_is_reported_before_the_kind(mapped: Grove) -> None:
    assert refusal(lambda: mapped.gaps("no-such-project", kind="map_untestd")).code == "not_found"


@pytest.fixture
def cli(home: Path, capsys: pytest.CaptureFixture[str]):
    def invoke(*args: str) -> tuple[int, str]:
        code = main(["--home", str(home), *args])
        return code, capsys.readouterr().out

    return invoke


@pytest.fixture
def stored(cli, home: Path) -> Path:
    """The same project as `mapped`, made through the CLI in the home both surfaces read."""
    for args in (("project", "create", "tiny", "--root", str(TINY)), ("scan", "tiny"), ("ingest-map", "tiny", str(MAP_SAMPLE))):
        assert cli(*args)[0] == 0
    return home


def test_the_cli_refuses_a_misspelt_kind_with_the_envelope(cli, stored: Path) -> None:
    for kind in ("declared_untestd", "MAP_UNTESTED", "all"):
        code, out = cli("gaps", "tiny", "--kind", kind)
        assert code == 1 and json.loads(out) == REFUSED
    code, out = cli("gaps", "tiny", "--kind=map_untestd", "--text")
    assert code == 1 and out == f"error [invalid]: {MESSAGE}\n"


def test_the_cli_still_takes_every_kind_and_a_blank_one(cli, stored: Path) -> None:
    code, out = cli("gaps", "tiny")
    everything = json.loads(out)["data"]
    assert code == 0 and everything["total"] > 0
    for kind in KINDS:
        code, out = cli("gaps", "tiny", "--kind", kind)
        assert code == 0 and json.loads(out)["data"]["total"] == everything["counts"][kind]
    code, out = cli("gaps", "tiny", "--kind", "")
    assert code == 0 and json.loads(out)["data"] == everything


def test_the_cli_help_offers_the_kinds() -> None:
    gaps = build_parser()._subparsers._group_actions[0].choices["gaps"]  # noqa: SLF001 - the `gaps` subcommand
    offered = "[--kind {" + ",".join(OFFERED) + "}]"
    assert offered in gaps.format_usage()
    option = next(line for line in gaps.format_help().splitlines() if line.strip().startswith("--kind"))
    assert "{" + ",".join(OFFERED) + "}" in option


def test_the_mcp_tool_refuses_a_misspelt_kind_with_the_same_envelope(cli, stored: Path) -> None:
    for kind in ("declared_untestd", "MAP_UNTESTED", "all"):
        assert call_tool(stored, "grove_gaps", {"project": "tiny", "kind": kind}) == REFUSED
        assert json.loads(cli("gaps", "tiny", "--kind", kind)[1]) == REFUSED
    assert call_tool(stored, "grove_gaps", {"project": "tiny", "kind": 7})["error"] == {
        "code": "invalid",
        "message": "kind must be a string",
    }


def test_the_mcp_tool_still_takes_every_kind_a_blank_one_and_none(cli, stored: Path) -> None:
    everything = call_tool(stored, "grove_gaps", {"project": "tiny"})
    assert everything["ok"] is True and everything["data"]["total"] > 0
    assert everything == json.loads(cli("gaps", "tiny")[1])
    for kind in KINDS:
        listed = call_tool(stored, "grove_gaps", {"project": "tiny", "kind": kind})
        assert listed["ok"] is True and listed["data"]["total"] == everything["data"]["counts"][kind]
    assert call_tool(stored, "grove_gaps", {"project": "tiny", "kind": ""}) == everything
    assert call_tool(stored, "grove_gaps", {"project": "tiny", "kind": None}) == everything


def test_what_an_mcp_client_reads_names_the_kinds_the_service_accepts() -> None:
    tool = TOOLS_BY_NAME["grove_gaps"]
    assert [kind for kind in KINDS if kind not in tool.description] == []
    # The schema carries no `enum` yet (the tool list has no room for it, R-GROK-3).
    # When one is added, it is this list and nothing else.
    assert tool.schema["properties"]["kind"].get("enum", list(KINDS)) == list(KINDS)
