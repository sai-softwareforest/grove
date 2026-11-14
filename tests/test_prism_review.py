"""Prism, second part: lessons matched to a project, verdicts, reopening and the review pack
(WO-41, R-PRISM-3 to R-PRISM-6).

Selection is computed on each read from the latest scan and is never stored.
A verdict is an ordinary knowledge note. A scan records what each selected
lesson rests on, so that a judged lesson comes back when that changes.
"""

from __future__ import annotations

import json
import socket
import sqlite3
from pathlib import Path

import pytest

from conftest import tree_snapshot
from sf_grove import prism
from sf_grove.cli import main
from sf_grove.db import MIGRATIONS, _split_statements, now_iso
from sf_grove.errors import GroveError
from sf_grove.mcp_server import tool_definitions
from sf_grove.scan import MAX_SYMBOLS_PER_FILE, extract_imports, manifest_dependencies, manifest_ecosystem, scan_tree
from sf_grove.service import Grove
from sf_grove.tools import TOOLS, call_tool

TOOL_NAMES = [
    "grove_status", "grove_project_create", "grove_project_list", "grove_project_get", "grove_scan",
    "grove_blueprint_get", "grove_gaps", "grove_ingest_map", "grove_knowledge_write", "grove_knowledge_get",
    "grove_knowledge_search", "grove_work_create", "grove_work_list", "grove_work_get", "grove_work_update",
    "grove_recommend_next",
]  # fmt: skip
TOOLS_LIST_BYTES = 14_985  # R-GROK-3: what tools/list measured before WO-41, and measures after it


def _lesson(grove: Grove, name: str, *tags: str) -> str:
    """Put one lesson with exactly these tags into the library; returns its key.

    A library that holds a lesson is not seeded, so a test that starts this
    way knows every lesson in it.
    """
    entry, skipped, _ = prism.make_entry(
        name.title(), f"https://example.org/{name}", f"What {name} suggests.", "fixture-list:1", tuple(sorted(tags))
    )
    assert entry is not None, skipped
    with grove._write():
        grove._prism_add(entry, "refresh", None, now_iso())
    return entry.key


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A small Go project with a Python requirements file: no seeded lesson matches Go by itself."""
    root = tmp_path / "proj"
    (root / "cmd").mkdir(parents=True)
    (root / "cmd" / "main.go").write_text('package main\n\nimport "fmt"\n\nfunc Run() {\n\tfmt.Println("run")\n}\n')
    (root / "requirements.txt").write_text("# runtime\nrequests>=2.0\n")
    (root / "README.md").write_text("# Proj\n\nR-APP-1: the tool prints a line when it is run.\n")
    return root


@pytest.fixture
def proj(grove: Grove, root: Path) -> Grove:
    grove.project_create("proj", str(root))
    return grove


def _pack(grove: Grove, **options: object) -> dict:
    return grove.prism_review("proj", **options)


def _states(grove: Grove) -> dict[str, str]:
    return {row["key"].split(":")[1]: row["state"] for row in _pack(grove, include_settled=True)["items"]}


def _judge(grove: Grove, key: str, body: str) -> dict:
    return grove.knowledge_write("proj", prism.VERDICT_KEY_PREFIX + key, "Verdict", body)


# -- selection -------------------------------------------------------------


def test_selection_follows_the_manifest_from_scan_to_scan(proj: Grove, root: Path) -> None:
    http = _lesson(proj, "http-lesson", "capability:http")
    exact = _lesson(proj, "exact-lesson", "dependency:sqlite-utils")
    database = _lesson(proj, "db-lesson", "capability:db")
    _lesson(proj, "python-lesson", "language:python")  # no Python module in the project
    go = _lesson(proj, "go-lesson", "language:go")
    assert _pack(proj)["items"] == [] and "not been scanned" in _pack(proj)["hint"]

    proj.scan("proj")
    pack = _pack(proj)
    assert pack["hint"] is None and pack["counts"] == {"open": 2, "reopened": 0, "settled": 0}
    rows = {row["key"]: row for row in pack["items"]}
    # `requests` is a package of the http capability; the Go file gives the language.
    assert set(rows) == {f"lesson:{http}", f"lesson:{go}"}
    assert rows[f"lesson:{http}"]["matched_on"] == ["capability:http"] and rows[f"lesson:{go}"]["matched_on"] == ["language:go"]
    row = rows[f"lesson:{http}"]
    assert (row["title"], row["summary"], row["source_url"]) == ("Http-Lesson", "What http-lesson suggests.", "https://example.org/http-lesson")
    assert (row["state"], row["tags"], row["verdict_key"], row["kind"]) == ("open", ["capability:http"], f"prism.{http}", "lesson")

    # A dependency is added: nothing changes until the project is scanned again.
    (root / "requirements.txt").write_text("requests>=2.0\nSQLite_Utils[extra]==3.1 ; python_version > '3.8'\n")
    assert len(_pack(proj)["items"]) == 2
    proj.scan("proj")
    rows = {row["key"]: row["matched_on"] for row in _pack(proj)["items"]}
    assert rows == {
        f"lesson:{http}": ["capability:http"],
        f"lesson:{go}": ["language:go"],
        f"lesson:{exact}": ["dependency:sqlite-utils"],  # the exact package name, normalised, without its version
        f"lesson:{database}": ["capability:db"],  # and the capability that package shows
    }

    # A dependency is removed.
    (root / "requirements.txt").write_text("sqlite-utils\n")
    proj.scan("proj")
    assert {row["key"] for row in _pack(proj)["items"]} == {f"lesson:{go}", f"lesson:{exact}", f"lesson:{database}"}


def test_a_selection_is_computed_on_each_read_and_never_stored(proj: Grove, lists_dir: Path) -> None:
    proj.scan("proj")  # the library is empty, so the scan seeds it
    assert proj.conn.execute("SELECT COUNT(*) FROM prism_lessons WHERE origin = 'seed'").fetchone()[0] > 100
    before = _pack(proj)
    assert before["total"] > 0 and "Fresh" not in {row["title"] for row in before["items"]}
    # A lesson that arrives after the scan is in the next read, with no scan in between.
    result = proj.prism_refresh(str(lists_dir))
    assert result["added"] == 1 and result["seeded"] == 0
    after = _pack(proj)
    key = next(row["key"] for row in after["items"] if row["title"] == "Fresh")
    # (The seeded lessons of that list are not in this copy of it, so the same refresh retired them.)
    assert after["total"] == before["total"] + 1 - result["retired"]
    # And one that is retired leaves it the same way.
    (lists_dir / "awesome-cli-apps" / "README.md").write_text("# Nothing left\n")
    assert proj.prism_refresh(str(lists_dir))["retired"] >= 1
    assert key not in {row["key"] for row in _pack(proj)["items"]}
    # No table holds which lessons a project was shown: prism_touch is filled by scans only.
    touched = proj.conn.execute("SELECT COUNT(*) FROM prism_touch WHERE key = ?", (key.split(":")[1],)).fetchone()[0]
    assert touched == 0


@pytest.fixture
def lists_dir(tmp_path: Path, root: Path) -> Path:
    """A list whose tag (capability:cli) the project has: the Go file below imports `flag`."""
    (root / "cmd" / "flags.go").write_text('package main\n\nimport (\n\t"flag"\n\tstr "strings"\n)\n\nvar _ = flag.Arg\nvar _ = str.ToUpper\n')
    lists = tmp_path / "lists" / "awesome-cli-apps"
    lists.mkdir(parents=True)
    (lists / "README.md").write_text("# CLI\n\n- [Fresh](https://example.org/fresh) - A lesson added after the scan.\n")
    return lists.parent


# -- verdicts ---------------------------------------------------------------


def test_a_verdict_note_settles_a_lesson_and_a_malformed_one_does_not(proj: Grove) -> None:
    keys = [_lesson(proj, f"lesson-{number}", "language:go") for number in range(6)]
    proj.scan("proj")
    assert set(_states(proj).values()) == {"open"}

    _judge(proj, keys[0], "verdict: not-relevant\nreason: this is a command-line tool with no server\n\nMore thoughts.")
    _judge(proj, keys[1], "verdict: edit\nreason: the summary undersells it")
    _judge(proj, keys[2], "\n\nverdict: delete\nreason: the link is a product page, not a practice\n")
    work = proj.work_create("proj", "Adopt lesson three")
    _judge(proj, keys[3], f"verdict: adopt\nreason: we lack this\nwork: {work['id']}\n")
    _judge(proj, keys[4], "I think we should adopt this.\nverdict: adopt")
    states = _states(proj)
    assert [states[key] for key in keys] == ["settled", "settled", "settled", "settled", "open", "open"]

    pack = _pack(proj)
    assert pack["counts"] == {"open": 2, "reopened": 0, "settled": 4} and pack["total"] == 2 and pack["complete"]
    rows = {row["key"].split(":")[1]: row for row in pack["items"]}
    assert rows[keys[4]]["verdict_error"] == "the body must start with a line 'verdict: adopt|edit|delete|not-relevant'"
    assert "verdict" not in rows[keys[4]] and "verdict_error" not in rows[keys[5]]
    everything = {row["key"].split(":")[1]: row for row in _pack(proj, include_settled=True)["items"]}
    assert [everything[key]["verdict"] for key in keys[:4]] == ["not-relevant", "edit", "delete", "adopt"]
    assert everything[keys[0]]["verdict_revision"] == 1 and "reopen_reason" not in everything[keys[0]]
    # Open first, settled last; by key inside a state.
    order = [row["state"] for row in _pack(proj, include_settled=True)["items"]]
    assert order == ["open", "open", "settled", "settled", "settled", "settled"]

    # Each way a body can be wrong leaves the lesson open and says why.
    for body, said in (
        ("verdict: maybe\nreason: unsure", "is not one of adopt|edit|delete|not-relevant"),
        ("verdict: edit", "a line 'reason: <text>' must follow the verdict"),
        ("verdict: edit\nreason:   ", "a line 'reason: <text>' must follow the verdict"),
        ("verdict: adopt\nreason: yes", "verdict adopt needs a line 'work: <id>'"),
        ("verdict: adopt\nreason: yes\nwork: soon", "verdict adopt needs a line 'work: <id>'"),
        ("verdict: adopt\nreason: yes\nwork: 99999", "work: 99999 is not a work item of this project"),
        ("reason: first\nverdict: edit", "the body must start with a line 'verdict:"),
    ):
        _judge(proj, keys[5], body)
        row = next(row for row in _pack(proj)["items"] if row["key"] == f"lesson:{keys[5]}")
        assert row["state"] == "open" and said in row["verdict_error"], body
    # The revisions are the audit trail: nothing was overwritten, and a good verdict settles it at last.
    _judge(proj, keys[5], "verdict: not-relevant\nreason: decided after all")
    assert _states(proj)[keys[5]] == "settled"
    assert proj.knowledge_get(f"prism.{keys[5]}", "proj")["revision"] == 8
    # A verdict is a note of this project only: the same key in the workspace judges nothing here.
    proj.knowledge_write(None, f"prism.{keys[4]}", "Elsewhere", "verdict: delete\nreason: not for this project to say")
    assert _states(proj)[keys[4]] == "open"


def test_a_work_item_of_another_project_does_not_carry_an_adoption(proj: Grove, tmp_path: Path) -> None:
    key = _lesson(proj, "lesson", "language:go")
    (tmp_path / "other").mkdir()
    proj.project_create("other", str(tmp_path / "other"))
    foreign = proj.work_create("other", "Not ours")
    proj.scan("proj")
    _judge(proj, key, f"verdict: adopt\nreason: x\nwork: {foreign['id']}")
    row = _pack(proj)["items"][0]
    assert row["state"] == "open" and row["verdict_error"] == f"work: {foreign['id']} is not a work item of this project"


# -- reopening ---------------------------------------------------------------


def test_a_changed_manifest_reopens_and_an_unrelated_edit_does_not(proj: Grove, root: Path) -> None:
    exact = _lesson(proj, "exact", "dependency:requests")
    by_capability = _lesson(proj, "by-capability", "capability:http")
    by_language = _lesson(proj, "by-language", "language:go")
    proj.scan("proj")
    for key in (exact, by_capability, by_language):
        _judge(proj, key, "verdict: not-relevant\nreason: judged")
    assert set(_states(proj).values()) == {"settled"}

    # An ordinary code edit, a new file and a changed document: nothing a lesson rests on.
    (root / "cmd" / "main.go").write_text('package main\n\nimport "fmt"\n\nfunc Run() {\n\tfmt.Println("changed")\n}\n\nfunc More() {}\n')
    (root / "cmd" / "extra.go").write_text("package main\n\nfunc Extra() {}\n")
    (root / "README.md").write_text("# Proj\n\nThe tool prints two lines now.\n")
    proj.scan("proj")
    assert set(_states(proj).values()) == {"settled"}
    assert proj.conn.execute("SELECT COUNT(*) FROM prism_touch WHERE changed_at IS NOT NULL").fetchone()[0] == 0

    # The manifest behind the dependency tag changes (a version, nothing else).
    (root / "requirements.txt").write_text("# runtime\nrequests>=3.0\n")
    proj.scan("proj")
    states = _states(proj)
    assert (states[exact], states[by_capability], states[by_language]) == ("reopened", "settled", "settled")
    row = _pack(proj)["items"][0]
    assert (row["key"], row["state"], row["reopen_reason"]) == (f"lesson:{exact}", "reopened", "manifest:requirements.txt")
    assert row["verdict"] == "not-relevant" and _pack(proj)["counts"] == {"open": 0, "reopened": 1, "settled": 2}
    # It stays reopened over further scans, until it is judged again.
    proj.scan("proj")
    assert _states(proj)[exact] == "reopened"
    _judge(proj, exact, "verdict: not-relevant\nreason: looked again after the upgrade")
    assert _states(proj)[exact] == "settled"
    proj.scan("proj")
    assert _states(proj)[exact] == "settled"


def test_a_new_importing_file_reopens_a_capability_and_an_edit_inside_one_does_not(proj: Grove, root: Path) -> None:
    (root / "tool.py").write_text("import argparse\n\n\ndef parse():\n    return argparse.ArgumentParser()\n")
    cli = _lesson(proj, "cli", "capability:cli")
    python = _lesson(proj, "python", "language:python")
    proj.scan("proj")
    item = proj.blueprint_get("proj", source_path="tool.py")["items"][0]
    assert item["extra"]["imports"] == ["argparse"]  # only the modules the tag map names are kept
    _judge(proj, cli, "verdict: edit\nreason: judged")
    _judge(proj, python, "verdict: edit\nreason: judged")

    (root / "tool.py").write_text("import argparse\nimport os\n\n\ndef parse():\n    return argparse.ArgumentParser(prog=os.sep)\n")
    proj.scan("proj")
    assert (_states(proj)[cli], _states(proj)[python]) == ("settled", "settled")

    (root / "second.py").write_text("from argparse import ArgumentParser\n")
    proj.scan("proj")
    rows = {row["key"].split(":")[1]: row for row in _pack(proj, include_settled=True)["items"]}
    assert (rows[cli]["state"], rows[cli]["reopen_reason"]) == ("reopened", "imports:cli")
    # A match on the language alone has nothing under it that a code edit could change.
    assert rows[python]["state"] == "settled"


def test_a_revised_note_reopens_without_a_scan_and_a_changed_requirement_with_one(proj: Grove, root: Path) -> None:
    first = _lesson(proj, "first", "language:go")
    second = _lesson(proj, "second", "language:go")
    proj.scan("proj")
    proj.knowledge_write("proj", "design-notes", "Design", "We print one line.")
    proj.knowledge_write(None, "house-rules", "Rules", "Workspace rules.")
    _judge(proj, first, "verdict: not-relevant\nreason: see knowledge:design-notes and knowledge:house-rules.")
    _judge(proj, second, "verdict: not-relevant\nreason: R-APP-1 already covers it")
    assert set(_states(proj).values()) == {"settled"}

    # The note the verdict cites gets a new revision: reopened at the next read.
    proj.knowledge_write("proj", "design-notes", "Design", "We print two lines.")
    row = _pack(proj)["items"][0]
    assert (row["key"], row["state"], row["reopen_reason"]) == (f"lesson:{first}", "reopened", "knowledge:design-notes")
    proj.knowledge_write(None, "house-rules", "Rules", "New workspace rules.")
    assert _pack(proj)["items"][0]["reopen_reason"] == "knowledge:design-notes, knowledge:house-rules"
    _judge(proj, first, "verdict: not-relevant\nreason: still so; see knowledge:design-notes")
    assert _states(proj)[first] == "settled"

    # The statement of the requirement the other verdict cites changes in the project's documents.
    proj.scan("proj")
    assert _states(proj)[second] == "settled"
    (root / "README.md").write_text("# Proj\n\nR-APP-1: the tool prints two lines when it is run.\n\nR-APP-12: unrelated.\n")
    proj.scan("proj")
    row = next(row for row in _pack(proj)["items"] if row["key"] == f"lesson:{second}")
    assert (row["state"], row["reopen_reason"]) == ("reopened", "requirement:R-APP-1")
    assert _states(proj)[first] == "settled"


def test_a_lesson_judged_before_its_first_scan_is_not_reopened_by_that_scan(proj: Grove, lists_dir: Path) -> None:
    proj.scan("proj")
    proj.prism_refresh(str(lists_dir))
    key = next(row["key"] for row in _pack(proj)["items"] if row["title"] == "Fresh").split(":")[1]
    _judge(proj, key, "verdict: not-relevant\nreason: judged before any scan saw it; R-APP-1")
    assert _states(proj)[key] == "settled"
    proj.scan("proj")
    proj.scan("proj")
    assert _states(proj)[key] == "settled"
    touch = proj.conn.execute("SELECT * FROM prism_touch WHERE key = ?", (key,)).fetchone()
    assert touch["changed_at"] is None and "requirement:R-APP-1" in json.loads(touch["fingerprint"])


# -- the pack ----------------------------------------------------------------


def test_the_pack_stops_at_fifty_and_says_so(proj: Grove) -> None:
    keys = sorted(_lesson(proj, f"lesson-{number}", "language:go") for number in range(60))
    proj.scan("proj")
    pack = _pack(proj)
    assert (len(pack["items"]), pack["total"], pack["limit"], pack["pack_cap"], pack["complete"]) == (50, 60, 50, 50, False)
    assert [row["key"] for row in pack["items"]] == [f"lesson:{key}" for key in keys[:50]]
    asked = _pack(proj, limit=200)
    assert (len(asked["items"]), asked["limit"], asked["complete"]) == (50, 50, False)
    small = _pack(proj, limit=10)
    assert (len(small["items"]), small["total"], small["complete"]) == (10, 60, False)
    # Judging lessons is how the rest of the pack is reached.
    for key in keys[:15]:
        _judge(proj, key, "verdict: not-relevant\nreason: no")
    rest = _pack(proj)
    assert (len(rest["items"]), rest["total"], rest["complete"]) == (45, 45, True)
    assert rest["items"][0]["key"] == f"lesson:{keys[15]}"
    everything = _pack(proj, include_settled=True)
    assert (everything["total"], len(everything["items"]), everything["complete"]) == (60, 50, False)
    for bad in ({"limit": 0}, {"offset": -1}, {"query": "q" * 201}):
        with pytest.raises(GroveError):
            _pack(proj, **bad)


def test_gaps_without_a_kind_is_what_it_was_and_lesson_is_the_pack(proj: Grove) -> None:
    key = _lesson(proj, "lesson", "language:go")
    proj.scan("proj")
    findings = proj.gaps("proj")
    assert set(findings["counts"]) == {"declared_untested", "declared_unseen", "actual_undocumented", "map_untested"}
    assert all(not str(finding["key"]).startswith("lesson:") for finding in findings["items"]) and "kind" not in findings
    assert proj.gaps("proj", kind="lesson") == _pack(proj) == proj.gaps("proj", kind=" lesson ")
    assert proj.gaps("proj", kind="lesson")["items"][0]["key"] == f"lesson:{key}"
    assert proj.gaps("proj", kind="lesson", query="LESSON suggests")["total"] == 1
    assert proj.gaps("proj", kind="lesson", query=key[:8])["total"] == 1
    assert proj.gaps("proj", kind="lesson", query="nothing like it")["total"] == 0
    with pytest.raises(GroveError) as refused:
        proj.gaps("proj", kind="lessons")
    assert refused.value.message.endswith("map_untested, lesson")


def test_both_surfaces_give_the_same_pack_with_the_network_taken_away(
    proj: Grove, home: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for number in range(3):
        _lesson(proj, f"lesson-{number}", "language:go")
    proj.scan("proj")
    proj.close()

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the review pack must not open a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)

    def cli(*args: str) -> dict:
        assert main(["--home", str(home), *args]) == 0
        return json.loads(capsys.readouterr().out)

    review = cli("prism", "review", "proj")
    assert review["ok"] and len(review["data"]["items"]) == 3
    assert cli("gaps", "proj", "--kind", "lesson") == review
    assert call_tool(home, "grove_gaps", {"project": "proj", "kind": "lesson"}) == review
    assert cli("prism", "review", "proj", "--limit", "2") == call_tool(home, "grove_gaps", {"project": "proj", "kind": "lesson", "limit": 2})
    assert cli("prism", "review", "proj", "--all")["data"]["total"] == 3
    # A scan works without the network too.
    assert cli("scan", "proj")["ok"]
    assert main(["--home", str(home), "prism", "review", "nobody"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "not_found"


def test_the_same_project_and_library_give_the_same_pack(tmp_path: Path, root: Path) -> None:
    """R-INV-3: two data directories, the same tree, the seeded library: identical packs, verdicts included."""
    (root / "requirements.txt").write_text("requests\npytest\n")
    packs = []
    for run in range(2):
        with Grove(tmp_path / f"home-{run}") as grove:
            grove.project_create("proj", str(root))
            grove.scan("proj")
            first = grove.prism_review("proj")
            assert first["total"] > 0, "the seed has lessons for a project that depends on pytest"
            key = first["items"][0]["key"].split(":")[1]
            grove.knowledge_write("proj", f"prism.{key}", "Verdict", "verdict: edit\nreason: same on both")
            grove.scan("proj")
            packs.append((first, grove.prism_review("proj"), grove.prism_review("proj", include_settled=True)))
    assert packs[0] == packs[1]


def test_scans_and_reviews_leave_the_project_as_it_was(proj: Grove, root: Path) -> None:
    """R-INV-4: reading manifests and imports writes nothing in the project."""
    (root / "pyproject.toml").write_text('[project]\nname = "p"\ndependencies = ["pytest"]\n')
    before = tree_snapshot(root)
    proj.scan("proj")
    key = _pack(proj)["items"][0]["key"].split(":")[1]
    _judge(proj, key, "verdict: not-relevant\nreason: x")
    proj.scan("proj")
    _pack(proj, include_settled=True)
    proj.gaps("proj", kind="lesson")
    proj.recommend_next("proj")
    assert tree_snapshot(root) == before


def test_recommend_names_the_pack_when_nothing_ranks_higher(proj: Grove, root: Path) -> None:
    assert proj.recommend_next("proj")["action"] == "scan"
    (root / "README.md").write_text("# Proj\n")
    keys = [_lesson(proj, f"lesson-{number}", "language:go") for number in range(2)]
    proj.scan("proj")
    proj.work_create("proj", "Something ready")
    assert proj.recommend_next("proj")["action"] != "none"  # a finding or a ready item still comes first
    for item in proj.work_list("proj")["items"]:
        proj.work_update(item["id"], status="done")
    while proj.recommend_next("proj")["finding"]:  # the fixture's module is undocumented: claim what is left
        finding = proj.recommend_next("proj")["finding"]
        proj.work_create("proj", f"Covered by finding:{finding['key']}", plan="open on purpose")
        proj.work_update(proj.work_list("proj")["items"][-1]["id"], status="in_progress")
    step = proj.recommend_next("proj")
    assert step["action"] == "none"
    assert step["rationale"].startswith("No findings and no ready work items. Review 2 Prism lesson(s) (grove_gaps kind=lesson).")
    for key in keys:
        _judge(proj, key, "verdict: not-relevant\nreason: no")
    assert proj.recommend_next("proj")["rationale"].startswith("No findings and no ready work items. Nothing to recommend.")


def test_the_tool_list_is_byte_for_byte_what_it_was() -> None:
    """R-INV-9, R-GROK-3: no tool, no parameter and no word of a description was added for Prism."""
    assert [tool.name for tool in TOOLS] == TOOL_NAMES
    payload = {"tools": [tool.model_dump(by_alias=True, exclude_none=True) for tool in tool_definitions()]}
    assert len(json.dumps(payload)) == TOOLS_LIST_BYTES
    assert "kind=lesson" not in json.dumps(payload) and "prism" not in json.dumps(payload).lower()


# -- what a scan reads for it --------------------------------------------------


def test_manifests_give_package_names_and_nothing_else() -> None:
    assert [manifest_ecosystem(name) for name in ("pyproject.toml", "sub/package.json", "Cargo.toml", "go.mod")] == [
        "python", "javascript", "rust", "go",
    ]  # fmt: skip
    assert manifest_ecosystem("requirements-dev.txt") == manifest_ecosystem("deep/Requirements.txt") == "python"
    assert [manifest_ecosystem(name) for name in ("setup.py", "package-lock.json", "notes.txt", "pyproject.toml.bak")] == [None] * 4

    pyproject = """
[project]
name = "demo"
dependencies = ["Requests>=2.31", "typing_extensions ; python_version < '3.11'", "pkg[extra] @ https://example.org/pkg.whl"]
[project.optional-dependencies]
docs = ["Sphinx==7.0"]
[dependency-groups]
dev = ["pytest==9.2.0", {include-group = "lint"}]
lint = ["ruff"]
[tool.poetry.dependencies]
python = "^3.13"
Flask = "^3"
[tool.poetry.group.test.dependencies]
hypothesis = "*"
"""
    assert manifest_dependencies("pyproject.toml", pyproject) == (
        ["flask", "hypothesis", "pkg", "pytest", "requests", "ruff", "sphinx", "typing-extensions"],
        True,
    )
    requirements = "# comment\n-r other.txt\n--index-url https://example.org/simple\nDjango>=4\nzope.interface\n\n  uvicorn[standard]  # server\n"
    assert manifest_dependencies("requirements.txt", requirements) == (["django", "uvicorn", "zope-interface"], True)
    package = json.dumps(
        {"name": "demo", "version": "1.0.0", "dependencies": {"express": "^4", "@scope/pkg": "1"}, "devDependencies": {"vitest": "1"}, "scripts": {"x": "y"}}
    )
    assert manifest_dependencies("package.json", package) == (["@scope/pkg", "express", "vitest"], True)
    cargo = '[package]\nname = "demo"\n[dependencies]\nserde = { version = "1", features = ["derive"] }\nclap = "4"\nalias = { package = "real-name", version = "1" }\n[dev-dependencies]\nproptest = "1"\n[target.\'cfg(unix)\'.dependencies]\nlibc = "0.2"\n'
    assert manifest_dependencies("Cargo.toml", cargo) == (["clap", "libc", "proptest", "real-name", "serde"], True)
    gomod = "module example.org/demo\n\ngo 1.22\n\nrequire github.com/spf13/cobra v1.8.0\n\nrequire (\n\tgolang.org/x/crypto v0.20.0 // indirect\n\tgithub.com/lib/pq v1.10.9\n)\n\nreplace example.org/old v1.0.0 => ../old\n"
    assert manifest_dependencies("go.mod", gomod) == (["github.com/lib/pq", "github.com/spf13/cobra", "golang.org/x/crypto"], True)
    # What cannot be parsed gives no names and says so; what is not a name is left out.
    assert manifest_dependencies("pyproject.toml", "[project\n") == ([], False)
    assert manifest_dependencies("package.json", "{not json") == ([], False)
    assert manifest_dependencies("package.json", "[" * 100_000) == ([], False)
    assert manifest_dependencies("package.json", json.dumps({"dependencies": {"ok": "1", "Bad Name‮": "1", "x" * 300: "1"}})) == (["ok"], True)
    assert manifest_dependencies("pyproject.toml", "project = 7\ntool = []\n") == ([], True)


def test_imports_are_read_per_language() -> None:
    python = "import os, sqlite3 as db\nimport http.server\nfrom urllib.parse import quote\nfrom . import local\nfrom .sibling import x\n    import argparse\n# import pytest\n"
    assert extract_imports("python", python) == ["argparse", "http", "os", "sqlite3", "urllib"]
    javascript = "import express from 'express'\nimport { x } from \"@scope/pkg/sub\"\nconst fs = require('node:fs')\nimport './local.js'\nimport 'side-effect'\nconst lazy = await import('yargs/helpers')\nexport * from '../up'\n"
    assert extract_imports("javascript", javascript) == ["@scope/pkg", "express", "fs", "side-effect", "yargs"]
    assert extract_imports("typescript", javascript) == extract_imports("javascript", javascript)
    go = 'package main\n\nimport "fmt"\nimport alias "net/http"\n\nimport (\n\t"database/sql"\n\t_ "github.com/lib/pq" // driver\n)\n\nvar text = "not/an/import"\n'
    assert extract_imports("go", go) == ["database/sql", "fmt", "github.com/lib/pq", "net/http"]
    rust = "use std::fs;\npub use clap::Parser;\npub(crate) use ::serde::Serialize;\nextern crate rusqlite;\n// use nothing;\nlet used = 1;\n"
    assert extract_imports("rust", rust) == ["clap", "rusqlite", "serde", "std"]
    assert extract_imports("go", "") == [] and extract_imports("cobol", "import x") == []


def test_a_scan_stores_manifests_dependencies_and_watched_imports(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "tests").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "p"\ndependencies = ["requests"]\n')
    (root / "app.py").write_text("import os\nimport sqlite3\nimport json\n\n\ndef run():\n    return 1\n")
    (root / "tests" / "test_app.py").write_text("import pytest\n\n\ndef test_run():\n    assert True\n")
    (root / "README.md").write_text("# P\n\nIt returns the requests it handled.\n")
    result = scan_tree(root, watch_imports={"sqlite3", "pytest"})
    by_kind: dict[str, list] = {}
    for item in result.items:
        by_kind.setdefault(item.extra.get("kind"), []).append(item)
    manifest = by_kind["manifest"][0]
    assert (manifest.layer, manifest.title, manifest.body, manifest.source_path) == ("actual", "pyproject.toml", "requests", "pyproject.toml")
    assert manifest.extra["dependencies"] == 1 and manifest.extra["ecosystem"] == "python" and len(manifest.extra["sha256"]) == 16
    assert [(item.layer, item.title, item.extra) for item in by_kind["dependency"]] == [
        ("actual", "requests", {"kind": "dependency", "ecosystem": "python"})
    ]
    assert by_kind["module"][0].extra["imports"] == ["sqlite3"] and by_kind["test_file"][0].extra["imports"] == ["pytest"]
    # Without a watch list no import is recorded, and the items are otherwise the same.
    plain = scan_tree(root)
    assert all("imports" not in item.extra for item in plain.items) and len(plain.items) == len(result.items)

    # A package name is not code: "requests" in the manifest does not make the sentence look implemented.
    with Grove(tmp_path / "home") as grove:
        grove.project_create("p", str(root))
        grove.scan("p")
        unseen = [finding["summary"] for finding in grove.gaps("p", kind="declared_unseen")["items"]]
        assert any("the requests it handled" in summary for summary in unseen)
        assert grove.gaps("p", kind="actual_undocumented", query="pyproject")["total"] == 0


def test_a_manifest_with_too_many_dependencies_is_cut_and_reported(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    names = [f"package-{number:04d}" for number in range(MAX_SYMBOLS_PER_FILE + 7)]
    (root / "requirements.txt").write_text("\n".join(names) + "\n")
    result = scan_tree(root)
    manifest = next(item for item in result.items if item.extra.get("kind") == "manifest")
    assert (manifest.extra["dependencies"], manifest.extra["dependencies_found"]) == (MAX_SYMBOLS_PER_FILE, MAX_SYMBOLS_PER_FILE + 7)
    assert sum(1 for item in result.items if item.extra.get("kind") == "dependency") == MAX_SYMBOLS_PER_FILE
    assert result.summary()["caps"]["symbols_capped"]["items"] == [
        {"path": "requirements.txt", "kind": "dependencies", "found": MAX_SYMBOLS_PER_FILE + 7, "kept": MAX_SYMBOLS_PER_FILE, "dropped": 7}
    ]
    assert manifest.body.endswith(f"(+{MAX_SYMBOLS_PER_FILE - 40} more)")


# -- storage -------------------------------------------------------------------


def test_a_version_6_database_gains_the_touch_table_and_keeps_its_library(home: Path, root: Path) -> None:
    home.mkdir(parents=True)
    raw = sqlite3.connect(home / "grove.db")
    for script in MIGRATIONS[:6]:
        for statement in _split_statements(script):
            raw.execute(statement)
    raw.execute("PRAGMA user_version = 6")
    raw.execute("INSERT INTO projects (name, root_path, created_at) VALUES ('proj', ?, '2026-01-01T00:00:00Z')", (str(root),))
    raw.execute(
        "INSERT INTO prism_lessons (key, title, summary, source_url, source_list, tags, origin) "
        "VALUES ('aaaaaaaaaaaa', 'Kept', 'A lesson from before.', 'https://example.org/kept', 'fixture-list:1', '[\"language:go\"]', 'refresh')"
    )
    raw.execute("INSERT INTO prism_events (key, event, at) VALUES ('aaaaaaaaaaaa', 'added', '2026-01-01T00:00:00Z')")
    raw.commit()
    raw.close()
    with Grove(home) as grove:
        assert grove.conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) >= 7
        assert grove.prism_review("proj")["items"] == []  # never scanned by this Grove
        grove.scan("proj")
        pack = grove.prism_review("proj")
        assert [row["key"] for row in pack["items"]] == ["lesson:aaaaaaaaaaaa"]
        # The library held a lesson, so the scan did not seed it.
        assert grove.conn.execute("SELECT COUNT(*) FROM prism_lessons").fetchone()[0] == 1
        touch = grove.conn.execute("SELECT * FROM prism_touch").fetchone()
        assert (touch["key"], touch["changed_at"], json.loads(touch["fingerprint"])) == ("aaaaaaaaaaaa", None, {"tags": ["language:go"]})
