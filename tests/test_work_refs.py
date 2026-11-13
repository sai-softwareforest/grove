"""References on work items (R-WORK-6, WO-15).

A work item can point at the requirement, note or change it belongs to, and be
found by it. A reference is a short string that Grove stores and returns: it
is never fetched, parsed or checked against anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import TINY
from sf_grove.cli import build_parser, main
from sf_grove.errors import GroveError
from sf_grove.service import CLEAR_EXCLUDE, CLEAR_REFS, MAX_REF_CHARS, MAX_REFS, Grove
from sf_grove.tools import TOOLS_BY_NAME, call_tool

REFS = ["R-HOME-2", "knowledge:greet-plan", "https://example.invalid/acme/app/pull/12"]


def ids(page: dict) -> list[int]:
    return [item["id"] for item in page["items"]]


def history(grove: Grove, work_id: int) -> dict:
    return grove.work_get(work_id)["history"]


# -- stored and shown ------------------------------------------------------------


def test_references_are_stored_in_order_and_shown_by_every_work_result(tiny: Grove) -> None:
    created = tiny.work_create("tiny", "Add a test for greet", refs=REFS)
    assert created["refs"] == REFS
    assert tiny.work_get(created["id"])["refs"] == REFS
    assert tiny.work_list("tiny")["items"][0]["refs"] == REFS
    assert tiny.work_update(created["id"], status="in_progress")["refs"] == REFS  # an update of something else keeps them

    # An item without references shows an empty list, never a missing key or null.
    bare = tiny.work_create("tiny", "No references")
    assert bare["refs"] == [] and tiny.work_get(bare["id"])["refs"] == []
    assert tiny.work_create("tiny", "Empty list", refs=[])["refs"] == []
    # The oldest ready item is what recommend points at; it is the same row shape.
    tiny.work_update(created["id"], status="done")
    assert tiny.recommend_next("tiny")["work_item_ids"] == [bare["id"]]


def test_a_reference_is_text_and_nothing_is_read_into_it(tiny: Grove) -> None:
    # Not a known id, not an existing key, not a reachable address: stored and returned as written.
    odd = [
        "R-NOPE-999",
        "knowledge:no-such-key",
        "https://example.invalid/a b?q=%41&x=1#frag",
        "file:///etc/passwd",
        'say "hi", twice \\ once',
        "naïve-ß-参照",
        "UPPER and lower",
    ]
    item = tiny.work_create("tiny", "Odd references", refs=odd)
    assert item["refs"] == odd == tiny.work_get(item["id"])["refs"]
    for ref in odd:  # and each one finds the item again, whatever characters it holds
        assert ids(tiny.work_list("tiny", ref=ref)) == [item["id"]], ref
    assert tiny.knowledge_search()["total"] == 0  # naming a key creates nothing


def test_references_are_trimmed_and_kept_once_and_blank_ones_are_dropped(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Untidy list", refs=["  R-HOME-2 ", "", "R-HOME-2", "   ", "WO-15\n", "R-HOME-2\t"])
    assert item["refs"] == ["R-HOME-2", "WO-15"]
    assert tiny.work_create("tiny", "Only blanks", refs=["", "  "])["refs"] == []
    # Case is not folded: these are two references.
    assert tiny.work_create("tiny", "Two cases", refs=["wo-15", "WO-15"])["refs"] == ["wo-15", "WO-15"]


# -- listed by one ---------------------------------------------------------------


def test_work_list_filters_by_one_exact_reference(tiny: Grove) -> None:
    first = tiny.work_create("tiny", "First", refs=["R-HOME-2", "knowledge:greet-plan"])["id"]
    second = tiny.work_create("tiny", "Second", refs=["R-HOME-2"])["id"]
    third = tiny.work_create("tiny", "Third", refs=["R-HOME-20", "r-home-2", "see R-HOME-2"])["id"]
    bare = tiny.work_create("tiny", "No references")["id"]

    assert ids(tiny.work_list("tiny", ref="R-HOME-2")) == [first, second]
    assert ids(tiny.work_list("tiny", ref="knowledge:greet-plan")) == [first]
    # Whole and exact: no prefix, no part, no other case.
    assert ids(tiny.work_list("tiny", ref="R-HOME-20")) == [third]
    assert ids(tiny.work_list("tiny", ref="r-home-2")) == [third]
    for near_miss in ("R-HOME", "HOME-2", "R-HOME-2 ", "knowledge:", "R-HOME-200"):
        expected = [first, second] if near_miss.strip() == "R-HOME-2" else []
        assert ids(tiny.work_list("tiny", ref=near_miss)) == expected, near_miss  # trimmed, like a stored reference
    # A reference nothing carries is an empty page, not an error: the set is open.
    nothing = tiny.work_list("tiny", ref="R-NOPE-1")
    assert (nothing["total"], nothing["items"]) == (0, [])
    # A blank or missing one is no filter.
    assert ids(tiny.work_list("tiny", ref="  ")) == ids(tiny.work_list("tiny")) == [first, second, third, bare]


def test_the_reference_filter_reads_no_pattern_and_no_json(tiny: Grove) -> None:
    under = tiny.work_create("tiny", "Underscore", refs=["a_b"])["id"]
    percent = tiny.work_create("tiny", "Percent", refs=["a%b"])["id"]
    plain = tiny.work_create("tiny", "Plain", refs=["axb"])["id"]
    two = tiny.work_create("tiny", "Two", refs=["left", "right"])["id"]
    quoted = tiny.work_create("tiny", "Quoted", refs=['"left"', "[", '"', "right, left"])["id"]

    assert ids(tiny.work_list("tiny", ref="a_b")) == [under]  # LIKE would also take axb and a%b
    assert ids(tiny.work_list("tiny", ref="a%b")) == [percent]
    assert ids(tiny.work_list("tiny", ref="axb")) == [plain]
    assert ids(tiny.work_list("tiny", ref="%")) == ids(tiny.work_list("tiny", ref="_")) == []
    # The stored list is JSON. No piece of its punctuation is a reference.
    for piece in ('", "', '","', "left, right", '["left", "right"]', "]", ","):
        assert ids(tiny.work_list("tiny", ref=piece)) == [], piece
    assert ids(tiny.work_list("tiny", ref="left")) == [two]
    assert ids(tiny.work_list("tiny", ref='"left"')) == ids(tiny.work_list("tiny", ref="[")) == [quoted]
    assert ids(tiny.work_list("tiny", ref='"')) == ids(tiny.work_list("tiny", ref="right, left")) == [quoted]


def test_the_reference_filter_combines_with_status_and_paging_and_stays_in_the_project(
    tiny: Grove, tmp_path: Path
) -> None:
    other_root = tmp_path / "other"
    other_root.mkdir()
    tiny.project_create("other", str(other_root))
    elsewhere = tiny.work_create("other", "Same reference, other project", refs=["WO-15"])["id"]
    mine = [tiny.work_create("tiny", f"Item {number}", refs=["WO-15"])["id"] for number in range(5)]
    tiny.work_create("tiny", "Unrelated", refs=["WO-16"])
    tiny.work_update(mine[1], status="review")
    tiny.work_update(mine[3], status="review")

    assert ids(tiny.work_list("tiny", ref="WO-15")) == mine
    assert ids(tiny.work_list("other", ref="WO-15")) == [elsewhere]
    assert ids(tiny.work_list("tiny", status="review", ref="WO-15")) == [mine[1], mine[3]]
    assert ids(tiny.work_list("tiny", status="review", ref="WO-16")) == []
    page = tiny.work_list("tiny", ref="WO-15", limit=2, offset=3)
    assert (page["total"], page["limit"], page["offset"], ids(page)) == (5, 2, 3, mine[3:5])
    # The filter follows the stored list: replaced or cleared references are no longer found.
    tiny.work_update(mine[0], refs=["WO-16"])
    tiny.work_update(mine[2], refs=[CLEAR_REFS])
    assert ids(tiny.work_list("tiny", ref="WO-15")) == [mine[1], mine[3], mine[4]]


# -- keep, replace, clear (D-43) ---------------------------------------------------


@pytest.mark.parametrize("empty", [None, [], [""], ["  ", ""], ()])
def test_an_omitted_or_empty_list_keeps_the_stored_references(tiny: Grove, empty: object) -> None:
    item = tiny.work_create("tiny", "Job", refs=REFS)
    updated = tiny.work_update(item["id"], notes="something else", refs=empty)
    assert updated["refs"] == REFS == tiny.work_get(item["id"])["refs"]
    assert history(tiny, item["id"])["total"] == 0
    # With nothing else to do it is no update at all, as a blank note is none.
    with pytest.raises(GroveError) as raised:
        tiny.work_update(item["id"], refs=empty)
    assert raised.value.code == "invalid" and "refs" in raised.value.message
    assert tiny.work_get(item["id"])["updated_at"] == updated["updated_at"]


def test_a_given_list_replaces_the_stored_one_and_does_not_add_to_it(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job", refs=["R-HOME-2", "WO-15"])
    replaced = tiny.work_update(item["id"], refs=["knowledge:greet-plan"])
    assert replaced["refs"] == ["knowledge:greet-plan"]
    # To add one, send the whole list: the result of every read shows it.
    added = tiny.work_update(item["id"], refs=[*replaced["refs"], "WO-15"])
    assert added["refs"] == ["knowledge:greet-plan", "WO-15"] == tiny.work_get(item["id"])["refs"]
    assert tiny.work_update(item["id"], refs=["WO-15", "knowledge:greet-plan"])["refs"][0] == "WO-15"  # order is kept


@pytest.mark.parametrize("clear", [[CLEAR_REFS], [" ! "], ["", CLEAR_REFS, " "]])
def test_only_the_clearing_word_empties_the_list(tiny: Grove, clear: list[str]) -> None:
    assert CLEAR_REFS == CLEAR_EXCLUDE == "!"  # one convention for both stored lists
    item = tiny.work_create("tiny", "Job", refs=REFS)
    assert tiny.work_update(item["id"], refs=clear)["refs"] == []
    assert tiny.work_get(item["id"])["refs"] == [] and tiny.work_list("tiny", ref=REFS[0])["total"] == 0
    assert tiny.work_update(item["id"], refs=["WO-15"])["refs"] == ["WO-15"]  # and it can be filled again


def test_the_clearing_word_is_never_a_reference(tiny: Grove) -> None:
    # A new item has nothing to clear: the word leaves it without references, as [] does.
    assert tiny.work_create("tiny", "Nothing to clear", refs=[CLEAR_REFS])["refs"] == []
    item = tiny.work_create("tiny", "Job", refs=["WO-15"])
    for mixed in ([CLEAR_REFS, "WO-16"], ["WO-16", " ! "]):
        with pytest.raises(GroveError) as raised:
            tiny.work_update(item["id"], refs=mixed)
        assert raised.value.code == "invalid" and "only entry" in raised.value.message
        with pytest.raises(GroveError):
            tiny.work_create("tiny", "Refused", refs=mixed)
    assert tiny.work_get(item["id"])["refs"] == ["WO-15"]
    assert tiny.work_list("tiny", ref=CLEAR_REFS)["total"] == 0
    assert tiny.work_create("tiny", "A longer word is a reference", refs=["!!", "!important"])["refs"] == ["!!", "!important"]


# -- history ---------------------------------------------------------------------


def test_a_changed_list_is_one_history_event_that_carries_the_new_list(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job", refs=["R-HOME-2"], author="ana")
    assert history(tiny, item["id"]) == {"total": 0, "events": []}  # creation is still not an event

    updated = tiny.work_update(item["id"], refs=["R-HOME-2", "knowledge:greet-plan"], author="sam")
    event = history(tiny, item["id"])["events"][0]
    assert event == {
        "id": event["id"],
        "created_at": updated["updated_at"],
        "author": "sam",
        "old_status": "ready",
        "new_status": "ready",  # equal: the list changed, the status did not
        "note": None,
        "refs": ["R-HOME-2", "knowledge:greet-plan"],
    }
    assert tiny.work_get(item["id"])["author"] == "ana"  # the item keeps its creator


def test_a_replaced_list_can_still_be_read_in_the_history(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Shared job")
    tiny.work_update(item["id"], refs=["R-HOME-2"], author="ana")
    tiny.work_update(item["id"], refs=["https://example.invalid/pull/12"], author="sam")  # erases ana's on the item
    tiny.work_update(item["id"], refs=[CLEAR_REFS], author="ana")

    assert tiny.work_get(item["id"])["refs"] == []
    events = history(tiny, item["id"])["events"]
    assert [(event["author"], event["refs"]) for event in events] == [
        ("ana", []),  # cleared: an empty list, not null
        ("sam", ["https://example.invalid/pull/12"]),
        ("ana", ["R-HOME-2"]),
    ]


def test_an_event_without_a_change_of_references_carries_null(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job", refs=["WO-15"])
    tiny.work_update(item["id"], status="in_progress")
    tiny.work_update(item["id"], note="half done")
    tiny.work_update(item["id"], note="same list again", refs=["WO-15"])
    assert [event["refs"] for event in history(tiny, item["id"])["events"]] == [None, None, None]

    # The same list alone is no change and adds no event, as a status set to the value it already has adds none.
    before = history(tiny, item["id"])["total"]
    assert tiny.work_update(item["id"], refs=[" WO-15 ", "WO-15"])["refs"] == ["WO-15"]
    tiny.work_update(item["id"], refs=[CLEAR_REFS])
    tiny.work_update(item["id"], refs=[CLEAR_REFS])  # already empty
    assert history(tiny, item["id"])["total"] == before + 1
    # The same references in another order are another list.
    tiny.work_update(item["id"], refs=["a", "b"])
    tiny.work_update(item["id"], refs=["b", "a"])
    assert history(tiny, item["id"])["total"] == before + 3


def test_status_note_and_references_in_one_update_are_one_event(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job")
    tiny.work_update(
        item["id"], status="review", note="tests added", refs=["https://example.invalid/pull/12"], author="ana"
    )
    recorded = history(tiny, item["id"])
    assert recorded["total"] == 1
    event = recorded["events"][0]
    assert (event["old_status"], event["new_status"], event["note"], event["refs"], event["author"]) == (
        "ready",
        "review",
        "tests added",
        ["https://example.invalid/pull/12"],
        "ana",
    )


# -- caps and errors ---------------------------------------------------------------


def test_the_limits_themselves_are_accepted(tiny: Grove) -> None:
    assert (MAX_REFS, MAX_REF_CHARS) == (20, 200)
    full = [f"R-FULL-{number}" for number in range(MAX_REFS)]
    longest = "x" * MAX_REF_CHARS
    item = tiny.work_create("tiny", "At the caps", refs=full)
    assert item["refs"] == full
    assert tiny.work_update(item["id"], refs=[f"  {longest}\n"])["refs"] == [longest]  # trimmed, then measured
    # Entries that are dropped do not count: blanks and repeats.
    assert tiny.work_update(item["id"], refs=[*full, "", *full, "  "])["refs"] == full
    assert ids(tiny.work_list("tiny", ref=longest)) == []
    assert ids(tiny.work_list("tiny", ref="x" * 5000)) == []  # a filter no reference can equal finds nothing


@pytest.mark.parametrize(
    "bad",
    [
        [f"R-MANY-{number}" for number in range(MAX_REFS + 1)],
        ["x" * (MAX_REF_CHARS + 1)],
        ["two\nlines"],
        ["tab\tinside"],
        ["nul\x00"],
        "R-HOME-2",  # a string, not a list
        {"ref": "R-HOME-2"},
        [7],
        ["R-HOME-2", None],
        7,
        True,
    ],
)
def test_a_bad_list_is_invalid_and_changes_nothing(tiny: Grove, bad: object) -> None:
    item = tiny.work_create("tiny", "Job", refs=["WO-15"])
    with pytest.raises(GroveError) as raised:
        tiny.work_update(item["id"], status="done", note="a refused update logs nothing", refs=bad)
    assert raised.value.code == "invalid"
    after = tiny.work_get(item["id"])
    assert (after["refs"], after["status"], after["history"]["total"]) == (["WO-15"], "ready", 0)
    with pytest.raises(GroveError) as raised:
        tiny.work_create("tiny", "Refused", refs=bad)
    assert raised.value.code == "invalid"
    assert tiny.work_list("tiny")["total"] == 1


def test_the_refusals_name_the_limits(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job")
    with pytest.raises(GroveError, match=f"more than {MAX_REFS} references"):
        tiny.work_update(item["id"], refs=[str(number) for number in range(MAX_REFS + 1)])
    with pytest.raises(GroveError, match=f"one line of at most {MAX_REF_CHARS} characters"):
        tiny.work_update(item["id"], refs=["x" * (MAX_REF_CHARS + 1)])
    with pytest.raises(GroveError, match="list of short strings"):
        tiny.work_update(item["id"], refs="R-HOME-2")
    with pytest.raises(GroveError) as raised:
        tiny.work_list("tiny", ref=["R-HOME-2"])
    assert raised.value.code == "invalid" and "ref must be a string" in raised.value.message


# -- both surfaces -----------------------------------------------------------------


def test_the_schemas_say_what_a_client_must_know() -> None:
    """R-IF-10: the description is all an MCP client reads."""
    create = TOOLS_BY_NAME["grove_work_create"]
    update = TOOLS_BY_NAME["grove_work_update"]
    listing = TOOLS_BY_NAME["grove_work_list"]
    for tool in (create, update):
        refs = tool.schema["properties"]["refs"]
        assert (refs["type"], refs["items"], refs["maxItems"]) == ("array", {"type": "string"}, MAX_REFS)
        assert "refs" not in tool.schema["required"]
    made = create.schema["properties"]["refs"]["description"]
    assert "never fetched" in made and "R-HOME-2" in made and "knowledge:greet-plan" in made and "URL" in made
    # Keep, replace, clear: the three things an update can do to the list.
    changed = update.schema["properties"]["refs"]["description"]
    assert f'["{CLEAR_REFS}"] clears the list' in changed and "omitted or [] keeps it" in changed
    assert "grove_work_create" in changed
    assert "refs (each replaces the stored value)" in update.description
    assert "changed refs adds one event" in update.description
    ref = listing.schema["properties"]["ref"]
    assert ref["type"] == "string" and "exactly" in ref["description"] and "ref" not in listing.schema["required"]
    assert "ref" in listing.description

    # What these descriptions said before they made room is still said, here or on a parameter.
    assert "never fetched" in create.schema["properties"]["issue_url"]["description"]
    assert "ready" in create.description and "does not implement it or open a pull request" in create.description
    assert listing.schema["properties"]["status"]["enum"] == ["ready", "in_progress", "review", "done", "blocked"]
    assert "paginated" in listing.description and "what is open" in listing.description
    get = TOOLS_BY_NAME["grove_work_get"]
    assert "by id" in get.description and "newest 20 events" in get.description and "total" in get.description
    assert "author" in get.description and "time" in get.description
    for fact in ("at least one", "erases nothing", "log progress", "ready -> in_progress -> review -> done", "blocked"):
        assert fact in update.description, fact
    # An author is described once, where notes are written, and the other tools point there.
    described = TOOLS_BY_NAME["grove_knowledge_write"].schema["properties"]["author"]["description"]
    assert "$GROVE_AUTHOR" in described
    for tool in (create, update):
        author = tool.schema["properties"]["author"]
        assert author["maxLength"] == 64 and "grove_knowledge_write" in author["description"]
    assert "kept on the event" in update.schema["properties"]["author"]["description"]


def test_references_through_the_mcp_tools(home: Path) -> None:
    def mcp(tool: str, **arguments: object) -> dict:
        envelope = call_tool(home, tool, arguments)
        assert envelope["ok"], envelope
        return envelope["data"]

    mcp("grove_project_create", name="tiny", root_path=str(TINY))
    item = mcp("grove_work_create", project="tiny", title="Add a test for greet", refs=REFS)
    assert item["refs"] == REFS
    bare = mcp("grove_work_create", project="tiny", title="No references", refs=None)  # null is "not given"
    assert bare["refs"] == []

    assert ids(mcp("grove_work_list", project="tiny", ref="R-HOME-2")) == [item["id"]]
    assert ids(mcp("grove_work_list", project="tiny", ref="R-HOME")) == []
    assert ids(mcp("grove_work_list", project="tiny", ref=None)) == [item["id"], bare["id"]]
    assert ids(mcp("grove_work_list", project="tiny", status="ready", ref=REFS[2])) == [item["id"]]

    # Keep, replace, clear.
    assert mcp("grove_work_update", id=item["id"], status="in_progress")["refs"] == REFS
    assert mcp("grove_work_update", id=item["id"], notes="x", refs=[])["refs"] == REFS
    assert mcp("grove_work_update", id=item["id"], refs=["WO-15"], author="sam")["refs"] == ["WO-15"]
    assert mcp("grove_work_update", id=item["id"], refs=[CLEAR_REFS])["refs"] == []
    fetched = mcp("grove_work_get", id=item["id"])
    assert fetched["refs"] == []
    assert [(event["author"], event["refs"]) for event in fetched["history"]["events"]] == [
        (None, []),
        ("sam", ["WO-15"]),
        (None, None),  # the status change
    ]

    for arguments in (
        {"id": item["id"], "refs": "WO-15"},
        {"id": item["id"], "refs": ["x" * (MAX_REF_CHARS + 1)]},
        {"id": item["id"], "refs": [str(number) for number in range(MAX_REFS + 1)]},
        {"id": item["id"], "refs": []},  # nothing to update
        {"id": item["id"], "ref": "WO-15"},  # the filter's name, on the wrong tool
    ):
        refused = call_tool(home, "grove_work_update", arguments)
        assert refused["ok"] is False and refused["error"]["code"] == "invalid", arguments
    assert call_tool(home, "grove_work_list", {"project": "tiny", "ref": 7})["error"]["code"] == "invalid"
    assert call_tool(home, "grove_work_create", {"project": "tiny", "title": "T", "refs": [7]})["error"]["code"] == "invalid"
    assert mcp("grove_work_list", project="tiny")["total"] == 2


def test_references_through_the_cli(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def cli(*args: str, expect: int = 0) -> dict:
        assert main(["--home", str(home), *args]) == expect
        envelope = json.loads(capsys.readouterr().out)
        return envelope["data"] if expect == 0 else envelope["error"]

    cli("project", "create", "tiny", "--root", str(TINY))
    item = cli("work", "create", "tiny", "--title", "Add a test for greet", "--ref", REFS[0], "--ref", REFS[1], "--ref", REFS[2])
    assert item["refs"] == REFS
    bare = cli("work", "create", "tiny", "--title", "No references")
    assert bare["refs"] == []
    work_id = str(item["id"])

    assert ids(cli("work", "list", "tiny", "--ref", "R-HOME-2")) == [item["id"]]
    assert ids(cli("work", "list", "tiny", "--ref", "R-HOME")) == []
    assert ids(cli("work", "list", "tiny", "--ref", "")) == [item["id"], bare["id"]]
    assert ids(cli("work", "list", "tiny", "--status", "ready", "--ref", REFS[2], "--limit", "1")) == [item["id"]]

    # Left out or empty, the stored references stay; given, they are replaced; '!' alone clears them.
    assert cli("work", "update", work_id, "--status", "in_progress")["refs"] == REFS
    assert cli("work", "update", work_id, "--notes", "x", "--ref", "", "--ref", " ")["refs"] == REFS
    assert cli("work", "update", work_id, "--ref", "WO-15", "--author", "sam")["refs"] == ["WO-15"]
    refused = cli("work", "update", work_id, "--ref", "WO-16", "--ref", CLEAR_REFS, expect=1)
    assert refused["code"] == "invalid" and "only entry" in refused["message"]
    assert cli("work", "get", work_id)["refs"] == ["WO-15"]
    assert cli("work", "update", work_id, "--ref", CLEAR_REFS)["refs"] == []

    # Both surfaces read the same item and the same history.
    from_cli = cli("work", "get", work_id)
    from_mcp = call_tool(home, "grove_work_get", {"id": item["id"]})
    assert from_mcp["ok"] and from_cli == from_mcp["data"]
    assert [(event["author"], event["refs"]) for event in from_cli["history"]["events"]] == [
        (None, []),
        ("sam", ["WO-15"]),
        (None, None),
    ]

    # Both refuse the same things.
    assert cli("work", "update", work_id, "--ref", "", expect=1)["code"] == "invalid"  # nothing to update
    assert cli("work", "update", work_id, "--ref", "x" * (MAX_REF_CHARS + 1), expect=1)["code"] == "invalid"
    too_many = [part for number in range(MAX_REFS + 1) for part in ("--ref", f"R-{number}")]
    assert cli("work", "create", "tiny", "--title", "Too many", *too_many, expect=1)["code"] == "invalid"
    assert cli("work", "list", "tiny")["total"] == 2

    # The help says how the flag behaves, and the plain rendering shows the list.
    work = build_parser()._subparsers._group_actions[0].choices["work"]  # noqa: SLF001
    actions = work._subparsers._group_actions[0].choices  # noqa: SLF001
    update_help = " ".join(actions["update"].format_help().split())
    assert f"--ref '{CLEAR_REFS}' alone clears them" in update_help and "left out or empty, they stay" in update_help
    assert "never fetched" in " ".join(actions["create"].format_help().split())
    assert "exactly this reference" in " ".join(actions["list"].format_help().split())
    cli("work", "update", work_id, "--ref", "R-HOME-2", "--ref", "WO-15")
    assert main(["--home", str(home), "--text", "work", "get", work_id]) == 0
    text = capsys.readouterr().out
    assert "refs:\n  - R-HOME-2\n  - WO-15\n" in text
