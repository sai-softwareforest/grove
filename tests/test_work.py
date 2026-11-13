"""Requirement 3: work item lifecycle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import TINY
from sf_grove.cli import main
from sf_grove.errors import GroveError
from sf_grove.service import HISTORY_EVENTS, MAX_NOTE_CHARS, STATUSES, Grove
from sf_grove.tools import call_tool


def test_work_item_lifecycle(tiny: Grove) -> None:
    created = tiny.work_create("tiny", "Add a test for greet", issue_url="https://example.invalid/issues/7", plan="1. write test")
    assert created["status"] == "ready"
    assert created["issue_url"] == "https://example.invalid/issues/7"
    assert created["plan"] == "1. write test" and created["notes"] == ""

    started = tiny.work_update(created["id"], status="in_progress", notes="picked up")
    assert started["status"] == "in_progress" and started["notes"] == "picked up"
    assert started["plan"] == "1. write test"  # untouched fields stay

    for status in ("review", "done"):
        assert tiny.work_update(created["id"], status=status)["status"] == status

    renamed = tiny.work_update(created["id"], title="Add tests for greet", plan="done")
    assert renamed["title"] == "Add tests for greet" and renamed["status"] == "done"
    fetched = tiny.work_get(created["id"])
    assert {key: value for key, value in fetched.items() if key != "history"} == renamed  # get adds only the history
    assert renamed["updated_at"] >= created["updated_at"]


def test_work_list_filters_by_status_and_pages(tiny: Grove) -> None:
    ids = [tiny.work_create("tiny", f"Item {index}")["id"] for index in range(4)]
    tiny.work_update(ids[0], status="blocked")
    assert tiny.work_list("tiny")["total"] == 4
    assert [item["id"] for item in tiny.work_list("tiny", status="blocked")["items"]] == [ids[0]]
    ready = tiny.work_list("tiny", status="ready", limit=2, offset=1)
    assert ready["total"] == 3 and [item["id"] for item in ready["items"]] == ids[2:4]


def test_work_item_errors(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Something")
    cases = [
        (lambda: tiny.work_update(item["id"], status="shipped"), "invalid"),
        (lambda: tiny.work_update(item["id"]), "invalid"),
        (lambda: tiny.work_update(9999, status="done"), "not_found"),
        (lambda: tiny.work_get(9999), "not_found"),
        (lambda: tiny.work_create("tiny", "   "), "invalid"),
        (lambda: tiny.work_create("nope", "Title"), "not_found"),
        (lambda: tiny.work_list("tiny", status="shipped"), "invalid"),
    ]
    for call, code in cases:
        with pytest.raises(GroveError) as raised:
            call()
        assert raised.value.code == code


def test_recommend_order_work_items_then_undocumented(grove: Grove, tmp_path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_text("# Proj\n\nNothing claimed here yet.\n")
    (root / "widget.py").write_text("def spin():\n    return 1\n")
    (root / "test_widget.py").write_text("def test_nothing_claimed_here_yet():\n    pass\n")
    grove.project_create("proj", str(root))
    grove.scan("proj")
    assert grove.gaps("proj", kind="declared_untested")["total"] == 0
    assert grove.recommend_next("proj")["action"] == "document_module"

    work = grove.work_create("proj", "Do the thing")
    recommendation = grove.recommend_next("proj")
    assert recommendation["action"] == "start_work_item"
    assert recommendation["work_item_ids"] == [work["id"]]

    grove.work_update(work["id"], status="in_progress")
    assert grove.recommend_next("proj")["action"] == "document_module"


def test_work_author_explicit_env_and_missing(tiny: Grove, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tiny.work_create("tiny", "No author")
    assert missing["author"] is None
    assert tiny.work_create("tiny", "Blank author", author="  ")["author"] is None
    explicit = tiny.work_create("tiny", "Explicit", author="ana")
    assert explicit["author"] == "ana"
    monkeypatch.setenv("GROVE_AUTHOR", "sam")
    from_env = tiny.work_create("tiny", "From env")
    assert from_env["author"] == "sam"
    assert tiny.work_create("tiny", "Argument wins", author="ana")["author"] == "ana"

    assert tiny.work_get(missing["id"])["author"] is None
    assert tiny.work_update(explicit["id"], status="in_progress")["author"] == "ana"  # updates keep it
    listed = {item["title"]: item["author"] for item in tiny.work_list("tiny")["items"]}
    assert listed == {"No author": None, "Blank author": None, "Explicit": "ana", "From env": "sam", "Argument wins": "ana"}


# -- history (R-WORK-5, WO-14) ------------------------------------------------


def test_a_second_note_does_not_erase_the_first(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Shared job", author="ana")
    assert tiny.work_get(item["id"])["history"] == {"total": 0, "events": []}  # creation is not an event

    tiny.work_update(item["id"], note="parser half done", author="ana")
    tiny.work_update(item["id"], note="reviewed the parser; one question", author="sam")

    history = tiny.work_get(item["id"])["history"]
    assert history["total"] == 2
    newest, oldest = history["events"]
    assert (newest["author"], newest["note"]) == ("sam", "reviewed the parser; one question")
    assert (oldest["author"], oldest["note"]) == ("ana", "parser half done")
    # A note alone changes no status; the event says which status the item was in.
    assert {(event["old_status"], event["new_status"]) for event in history["events"]} == {("ready", "ready")}
    assert set(newest) == {"id", "created_at", "author", "old_status", "new_status", "note", "refs"}  # refs: WO-15
    assert tiny.work_get(item["id"])["author"] == "ana"  # the item keeps its creator


def test_a_status_change_is_recorded_with_author_and_time(tiny: Grove, monkeypatch: pytest.MonkeyPatch) -> None:
    item = tiny.work_create("tiny", "Job")
    updated = tiny.work_update(item["id"], status="in_progress", author="ana")
    monkeypatch.setenv("GROVE_AUTHOR", "sam")
    tiny.work_update(item["id"], status="review", note="tests added")
    monkeypatch.delenv("GROVE_AUTHOR")
    tiny.work_update(item["id"], status="done")

    done, review, started = tiny.work_get(item["id"])["history"]["events"]
    assert (started["old_status"], started["new_status"], started["author"], started["note"]) == (
        "ready",
        "in_progress",
        "ana",
        None,
    )
    assert started["created_at"] == updated["updated_at"]
    assert (review["old_status"], review["new_status"], review["author"], review["note"]) == (
        "in_progress",
        "review",
        "sam",  # from $GROVE_AUTHOR
        "tests added",
    )
    assert (done["old_status"], done["new_status"], done["author"]) == ("review", "done", None)  # never guessed


def test_only_a_status_change_or_a_note_adds_an_event(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job")
    tiny.work_update(item["id"], status="ready")  # the status it already has
    tiny.work_update(item["id"], plan="a plan", notes="some notes", title="Renamed job", author="ana")
    assert tiny.work_get(item["id"])["history"]["total"] == 0
    tiny.work_update(item["id"], status="ready", note="still waiting")  # same status, but a note
    assert tiny.work_get(item["id"])["history"]["total"] == 1


def test_notes_and_plan_are_still_replaced_and_the_history_survives_it(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job", plan="first plan")
    tiny.work_update(item["id"], notes="first notes", note="logged by ana", author="ana")
    replaced = tiny.work_update(item["id"], notes="second notes", plan="second plan")
    assert (replaced["notes"], replaced["plan"]) == ("second notes", "second plan")
    assert tiny.work_update(item["id"], notes="")["notes"] == ""  # still clearable

    fetched = tiny.work_get(item["id"])
    assert (fetched["notes"], fetched["plan"]) == ("", "second plan")
    assert [event["note"] for event in fetched["history"]["events"]] == ["logged by ana"]


def test_history_is_the_newest_twenty_and_a_true_total(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Long job")
    other = tiny.work_create("tiny", "Other job")
    tiny.work_update(other["id"], note="not this item's")
    for number in range(HISTORY_EVENTS + 5):
        tiny.work_update(item["id"], note=f"step {number}")

    history = tiny.work_get(item["id"])["history"]
    assert history["total"] == HISTORY_EVENTS + 5 == 25
    assert [event["note"] for event in history["events"]] == [f"step {number}" for number in range(24, 4, -1)]
    ids = [event["id"] for event in history["events"]]
    assert ids == sorted(ids, reverse=True)
    assert tiny.work_get(other["id"])["history"]["total"] == 1


def test_every_transition_is_still_allowed_and_each_is_recorded(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job")
    current, changes = "ready", 0
    for target in [status for first in STATUSES for status in (first, *STATUSES)]:
        assert tiny.work_update(item["id"], status=target)["status"] == target  # R-WORK-3
        changes += target != current
        current = target
    history = tiny.work_get(item["id"])["history"]
    assert history["total"] == changes
    assert all(event["old_status"] != event["new_status"] for event in history["events"])


def test_history_errors_and_what_does_not_carry_history(tiny: Grove) -> None:
    item = tiny.work_create("tiny", "Job")
    cases = [
        lambda: tiny.work_update(item["id"], note="x" * (MAX_NOTE_CHARS + 1)),
        lambda: tiny.work_update(item["id"], note="   "),  # a blank note is no note: nothing to update
        lambda: tiny.work_update(item["id"], author="ana"),  # an author alone changes nothing
        lambda: tiny.work_update(item["id"], note=7),
        lambda: tiny.work_update(item["id"], note="fine", author="two\nlines"),
        lambda: tiny.work_update(item["id"], status="shipped", note="a refused update logs nothing"),
    ]
    for call in cases:
        with pytest.raises(GroveError) as raised:
            call()
        assert raised.value.code == "invalid"
    assert tiny.work_get(item["id"])["history"]["total"] == 0

    at_the_cap = tiny.work_update(item["id"], note="  " + "x" * MAX_NOTE_CHARS + "\n")
    assert tiny.work_get(item["id"])["history"]["events"][0]["note"] == "x" * MAX_NOTE_CHARS  # stripped, then measured
    # Only work_get carries the history; lists and write results stay small.
    assert "history" not in at_the_cap and "history" not in item
    assert all("history" not in listed for listed in tiny.work_list("tiny")["items"])


def test_cli_and_mcp_write_and_read_the_same_history(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def cli(*argv: str) -> dict:
        assert main(["--home", str(home), *argv]) == 0
        return json.loads(capsys.readouterr().out)["data"]

    def mcp(name: str, **arguments: object) -> dict:
        envelope = call_tool(home, name, arguments)
        assert envelope["ok"], envelope
        return envelope["data"]

    cli("project", "create", "tiny", "--root", str(TINY))
    work_id = cli("work", "create", "tiny", "--title", "Shared job")["id"]
    cli("work", "update", str(work_id), "--status", "in_progress", "--note", "from the command line", "--author", "ana")
    mcp("grove_work_update", id=work_id, status="review", note="from the tool", author="sam")
    cli("work", "update", str(work_id), "--notes", "replaced notes")  # --notes still replaces; no event

    from_cli = cli("work", "get", str(work_id))
    assert from_cli == mcp("grove_work_get", id=work_id)
    assert from_cli["notes"] == "replaced notes"
    assert from_cli["history"]["total"] == 2
    assert [(event["author"], event["old_status"], event["new_status"], event["note"]) for event in from_cli["history"]["events"]] == [
        ("sam", "in_progress", "review", "from the tool"),
        ("ana", "ready", "in_progress", "from the command line"),
    ]

    # Both surfaces refuse the same things.
    assert call_tool(home, "grove_work_update", {"id": work_id, "note": "x" * (MAX_NOTE_CHARS + 1)})["error"]["code"] == "invalid"
    assert main(["--home", str(home), "work", "update", str(work_id), "--note", "x" * (MAX_NOTE_CHARS + 1)]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid"
