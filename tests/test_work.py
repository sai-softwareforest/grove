"""Requirement 3: work item lifecycle."""

from __future__ import annotations

import pytest

from sf_grove.errors import GroveError
from sf_grove.service import Grove


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
    assert tiny.work_get(created["id"]) == renamed
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
