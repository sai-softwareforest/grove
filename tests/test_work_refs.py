"""WO-15, R-WORK-6, R-REC-2: a work item's ``refs`` are read from its text; nothing is stored or fetched."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sf_grove.cli import main
from sf_grove.db import connect
from sf_grove.service import MAX_REF_CHARS, MAX_REFS, OPEN_STATUSES, STATUSES, Grove, _refs
from sf_grove.tools import call_tool

README = "# Proj\n\n## Behaviours\n\n- Parses a config file.\n- Renders an invoice as text.\n"
KEY = "0123456789ab"


@pytest.fixture
def project(grove: Grove, tmp_path: Path) -> Grove:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "README.md").write_text(README)
    (root / "src" / "config.py").write_text("def parse_config():\n    pass\n\n\ndef render_invoice():\n    pass\n")
    grove.project_create("proj", str(root))
    grove.scan("proj")
    return grove


def refs(*texts: str) -> list[str]:
    found, omitted = _refs(*texts)
    assert omitted == 0
    return found


@pytest.mark.parametrize(
    "text,expected",
    [
        ("serves R-HOME-2.", ["R-HOME-2"]),
        ("(R-WORK-6, R-REC-2)", ["R-REC-2", "R-WORK-6"]),
        ("r-home-2, R-home-2, R-HOME-x, R-12, XR-HOME-2, R-HOME-2b", []),
        ("see knowledge:greet-plan.", ["knowledge:greet-plan"]),
        ("knowledge:a.b_c-1, then", ["knowledge:a.b_c-1"]),
        ("knowledge: spaced, knowledge:-dash, Knowledge:upper, myknowledge:x", []),
        (f"covers finding:{KEY}.", [f"finding:{KEY}"]),
        (f"finding:{KEY}#2 and finding:{KEY}#13;", [f"finding:{KEY}#13", f"finding:{KEY}#2"]),
        (f"finding:{KEY}cd finding:{KEY[:11]} finding:{KEY.upper()} finding:{KEY}#0x", [f"finding:{KEY}"]),
        ("https://example.invalid/pull/7", ["https://example.invalid/pull/7"]),
        ("(see https://example.invalid/pull/7).", ["https://example.invalid/pull/7"]),
        ("[the change](https://example.invalid/pull/7), merged", ["https://example.invalid/pull/7"]),
        ("<https://example.invalid/a?b=1&c=2#top>!", ["https://example.invalid/a?b=1&c=2#top"]),
        ("https://example.invalid/wiki/Tree_(graph)", ["https://example.invalid/wiki/Tree_(graph)"]),
        ("http://example.invalid/x ftp://example.invalid/x https:// xhttps://example.invalid", []),
        # Read left to right: what stands inside a URL is part of the URL.
        (f"https://example.invalid/R-HOME-2/finding:{KEY}", [f"https://example.invalid/R-HOME-2/finding:{KEY}"]),
        ("", []),
    ],
)
def test_each_pattern(text: str, expected: list[str]) -> None:
    assert refs(text) == expected


def test_refs_are_read_from_title_plan_and_notes_sorted_and_without_repeats(project: Grove) -> None:
    item = project.work_create("proj", "Test the parser (R-SCAN-3)", plan=f"R-HOME-2 first.\nThen finding:{KEY}, R-HOME-2 again.")
    assert item["refs"] == ["R-HOME-2", "R-SCAN-3", f"finding:{KEY}"]
    assert "refs_omitted" not in item
    updated = project.work_update(item["id"], notes="plan is in knowledge:parser-plan; change: https://example.invalid/pull/7")
    expected = ["R-HOME-2", "R-SCAN-3", f"finding:{KEY}", "https://example.invalid/pull/7", "knowledge:parser-plan"]
    assert updated["refs"] == expected == sorted(expected)
    assert project.work_get(item["id"])["refs"] == expected
    assert project.work_list("proj")["items"][0]["refs"] == expected
    # Read from the text each time: replace the text and the reference is gone.
    assert project.work_update(item["id"], plan="", notes="")["refs"] == ["R-SCAN-3"]
    assert project.work_create("proj", "Nothing to point at")["refs"] == []


def test_a_history_note_and_the_issue_url_are_not_read(project: Grove) -> None:
    item = project.work_create("proj", "Plain", issue_url="https://example.invalid/issues/7")
    project.work_update(item["id"], note="see R-HOME-2")
    assert project.work_get(item["id"])["refs"] == []


def test_nothing_is_stored(project: Grove, home: Path) -> None:
    project.work_create("proj", "R-HOME-2")
    conn = connect(home)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 5
        columns = [row[1] for row in conn.execute("PRAGMA table_info(work_items)")]
    finally:
        conn.close()
    assert not [column for column in columns if "ref" in column]


def test_the_caps_are_reported(project: Grove) -> None:
    many = " ".join(f"R-CAP-{number}" for number in range(MAX_REFS + 7))
    item = project.work_create("proj", "Many", plan=many)
    assert len(item["refs"]) == MAX_REFS and item["refs_omitted"] == 7
    assert item["refs"] == sorted(f"R-CAP-{number}" for number in range(MAX_REFS + 7))[:MAX_REFS]
    # A reference that is too long is left out and counted, never cut.
    fits = "https://example.invalid/" + "a" * (MAX_REF_CHARS - len("https://example.invalid/"))
    item = project.work_create("proj", "Long", plan=f"{fits} {fits}b R-HOME-2")
    assert len(fits) == MAX_REF_CHARS
    assert item["refs"] == ["R-HOME-2", fits] and item["refs_omitted"] == 1
    assert project.work_list("proj")["items"][-1]["refs_omitted"] == 1


def test_both_surfaces_return_refs(project: Grove, home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    created = call_tool(home, "grove_work_create", {"project": "proj", "title": "T", "plan": f"R-HOME-2 finding:{KEY}"})
    work_id = created["data"]["id"]
    expected = ["R-HOME-2", f"finding:{KEY}"]
    assert call_tool(home, "grove_work_get", {"id": work_id})["data"]["refs"] == expected
    assert call_tool(home, "grove_work_list", {"project": "proj"})["data"]["items"][0]["refs"] == expected
    for command in (["work", "get", str(work_id)], ["work", "list", "proj"]):
        assert main(["--home", str(home), *command]) == 0
        data = json.loads(capsys.readouterr().out)["data"]
        assert (data["items"][0] if "items" in data else data)["refs"] == expected


def test_recommend_skips_a_finding_with_open_work_and_returns_to_it(project: Grove) -> None:
    first = project.recommend_next("proj")
    assert first["action"] == "cover_untested_behaviour" and first["skipped_findings"] == 0
    assert "Passed over" not in first["rationale"]
    key = first["finding"]["key"]

    item = project.work_create("proj", "Cover it", plan=f"For R-HOME-2 and finding:{key}.")
    assert item["refs"] == ["R-HOME-2", f"finding:{key}"]
    for status in OPEN_STATUSES:
        project.work_update(item["id"], status=status)
        second = project.recommend_next("proj")
        assert second["finding"]["key"] != key, status
        assert second["action"] == "cover_untested_behaviour" and second["skipped_findings"] == 1
        assert "Passed over: 1 finding(s)" in second["rationale"]
    # A rescan gives the finding a new id and the same key: it stays skipped.
    project.scan("proj")
    assert project.recommend_next("proj")["finding"]["key"] == second["finding"]["key"]
    # The finding itself is untouched.
    assert key in {finding["key"] for finding in project.gaps("proj", limit=200)["items"]}

    project.work_update(item["id"], status="done")
    assert set(STATUSES) - set(OPEN_STATUSES) == {"done"}
    again = project.recommend_next("proj")
    assert again["finding"]["key"] == key and again["skipped_findings"] == 0


def test_recommend_moves_down_the_order_when_every_finding_of_a_tier_has_open_work(project: Grove) -> None:
    keys = [f["key"] for f in project.gaps("proj", kind="declared_untested", limit=200)["items"]]
    assert len(keys) == 2
    item = project.work_create("proj", "Cover both", plan=" ".join(f"finding:{key}" for key in keys))
    step = project.recommend_next("proj")
    assert step["action"] == "start_work_item" and step["work_item"]["id"] == item["id"]
    assert step["work_item"]["refs"] == sorted(f"finding:{key}" for key in keys)
    assert step["skipped_findings"] == 2 and "Passed over: 2 finding(s)" in step["rationale"]


def test_a_reference_in_another_project_or_to_no_finding_skips_nothing(project: Grove, tmp_path: Path) -> None:
    key = project.recommend_next("proj")["finding"]["key"]
    (tmp_path / "other").mkdir()
    project.project_create("other", str(tmp_path / "other"))
    project.work_create("other", "Elsewhere", plan=f"finding:{key}")
    project.work_create("proj", "Unknown key", plan="finding:ffffffffffff")
    step = project.recommend_next("proj")
    assert step["finding"]["key"] == key and step["skipped_findings"] == 0


def test_a_url_is_text_and_reading_refs_loads_no_network_module(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    code = (
        "import sys\n"
        "from sf_grove.service import Grove\n"
        f"grove = Grove({str(tmp_path / 'home')!r})\n"
        f"grove.project_create('p', {str(root)!r})\n"
        "item = grove.work_create('p', 'T', plan='https://example.invalid/pull/7')\n"
        "assert grove.work_get(item['id'])['refs'] == ['https://example.invalid/pull/7']\n"
        "assert grove.work_list('p')['items'][0]['refs'] and grove.recommend_next('p')\n"
        "loaded = sorted(n for n in sys.modules if n.split('.')[0] in ('socket', 'ssl', 'http', 'urllib', 'asyncio'))\n"
        "assert not loaded, loaded\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
