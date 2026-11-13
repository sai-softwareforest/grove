"""WO-28, R-REC-2: a finding keeps the same ``key`` across rescans; its id does not have to."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from conftest import MAP_SAMPLE
from sf_grove.cli import main
from sf_grove.db import MIGRATIONS, _split_statements, finding_key, normalise_key_text
from sf_grove.service import FINDING_KINDS, Grove
from sf_grove.tools import call_tool

KEY = re.compile(r"^[0-9a-f]{12}(#[1-9][0-9]*)?$")
README = "# Proj\n\n## Behaviours\n\n- Parses a config file.\n- Renders an invoice as text.\n"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "README.md").write_text(README)
    (root / "src" / "zork.py").write_text("def zork():\n    pass\n")
    return root


@pytest.fixture
def project(grove: Grove, root: Path) -> Grove:
    grove.project_create("proj", str(root))
    grove.scan("proj")
    return grove


def findings(grove: Grove, kind: str | None = None) -> list[dict]:
    page = grove.gaps("proj", kind=kind, limit=200)
    assert page["total"] == len(page["items"])
    return page["items"]


def keys_by_summary_text(grove: Grove, kind: str = "declared_untested") -> dict[str, str]:
    """key by the quoted statement, which unlike the whole summary carries no line number."""
    return {finding["summary"].split('"')[1]: finding["key"] for finding in findings(grove, kind)}


def test_every_kind_of_finding_has_a_key(project: Grove, root: Path) -> None:
    map_file = root.parent / "map.md"
    map_file.write_text("# Map\n\n## Risks\n\n- Zork is never exercised. (`untested`)\n")
    project.ingest_map("proj", str(map_file))
    found = findings(project)
    assert {finding["kind"] for finding in found} == set(FINDING_KINDS)
    for finding in found:
        assert KEY.match(finding["key"]), finding
    assert len({finding["key"] for finding in found}) == len(found)


def test_the_key_is_built_from_the_documented_inputs(project: Grove) -> None:
    by_kind = {finding["kind"]: finding for finding in reversed(findings(project))}
    for kind in ("declared_untested", "declared_unseen"):
        assert by_kind[kind]["summary"].split('"')[1] == "Parses a config file."
        assert by_kind[kind]["key"] == finding_key(kind, "README.md", "parses a config file.")
    assert by_kind["actual_undocumented"]["key"] == finding_key("actual_undocumented", "src/zork.py")
    assert finding_key("a", "bc") != finding_key("ab", "c")
    assert normalise_key_text("  Parses\ta  CONFIG\n file. ") == "parses a config file."


def test_an_unchanged_rescan_gives_the_same_keys(project: Grove) -> None:
    before = [(finding["kind"], finding["key"]) for finding in findings(project)]
    assert before
    project.scan("proj")
    assert [(finding["kind"], finding["key"]) for finding in findings(project)] == before


def test_moving_a_claim_down_one_line_keeps_its_key(project: Grove, root: Path) -> None:
    before = {kind: keys_by_summary_text(project, kind) for kind in ("declared_untested", "declared_unseen")}
    lines = {f["summary"].split('"')[1]: f["evidence"]["source_line"] for f in findings(project, "declared_untested")}
    (root / "README.md").write_text(README.replace("## Behaviours\n", "## Behaviours\n\nA new line of setup.\n"))
    project.scan("proj")
    after_findings = findings(project, "declared_untested")
    for finding in after_findings:
        text = finding["summary"].split('"')[1]
        if text in lines:
            assert finding["evidence"]["source_line"] > lines[text], "the claim should really have moved"
    for kind, keys in before.items():
        after = keys_by_summary_text(project, kind)
        assert keys and {text: after[text] for text in keys} == keys


def test_editing_the_text_of_a_claim_changes_its_key(project: Grove, root: Path) -> None:
    before = keys_by_summary_text(project)
    (root / "README.md").write_text(README.replace("Parses a config file.", "Parses a settings file."))
    project.scan("proj")
    after = keys_by_summary_text(project)
    assert "Parses a settings file." in after and "Parses a config file." not in after
    assert after["Parses a settings file."] != before["Parses a config file."]
    assert after["Renders an invoice as text."] == before["Renders an invoice as text."]
    # Only case and spacing are normalised away.
    (root / "README.md").write_text(README.replace("Parses a config file.", "PARSES  a config file."))
    project.scan("proj")
    assert keys_by_summary_text(project)["PARSES a config file."] == before["Parses a config file."]


def test_identical_claims_get_distinct_keys_in_source_order(project: Grove, root: Path) -> None:
    plain = keys_by_summary_text(project)["Parses a config file."]
    (root / "README.md").write_text(README + "\n## Again\n\n- Parses a config file.\n- Parses a config file.\n")
    project.scan("proj")
    same = [f for f in findings(project, "declared_untested") if f["summary"].split('"')[1] == "Parses a config file."]
    same.sort(key=lambda finding: finding["evidence"]["source_line"])
    assert [finding["key"] for finding in same] == [plain, f"{plain}#2", f"{plain}#3"]
    project.scan("proj")
    again = sorted(
        (f for f in findings(project, "declared_untested") if f["summary"].split('"')[1] == "Parses a config file."),
        key=lambda finding: finding["evidence"]["source_line"],
    )
    assert [finding["key"] for finding in again] == [plain, f"{plain}#2", f"{plain}#3"]


def test_a_map_finding_keeps_its_key_across_scans_and_a_new_ingest(project: Grove, root: Path) -> None:
    map_file = root.parent / "map.md"
    body = "# Map\n\n## Risks\n\n- Zork is never exercised. (`untested`)\n- Zork ignores its input. (`untested`)\n"
    map_file.write_text(body)
    project.ingest_map("proj", str(map_file))
    before = {finding["evidence"]["text"]: finding["key"] for finding in findings(project, "map_untested")}
    assert len(before) == 2 and len(set(before.values())) == 2
    for text, key in before.items():
        assert key == finding_key("map_untested", "map", normalise_key_text(text))

    project.scan("proj")
    assert {f["evidence"]["text"]: f["key"] for f in findings(project, "map_untested")} == before
    map_file.write_text(body.replace("## Risks\n", "## Risks\n\nMoved down.\n"))
    project.ingest_map("proj", str(map_file))
    assert {f["evidence"]["text"]: f["key"] for f in findings(project, "map_untested")} == before


def test_map_findings_have_keys_before_the_first_scan(grove: Grove, root: Path) -> None:
    grove.project_create("proj", str(root))
    result = grove.ingest_map("proj", str(MAP_SAMPLE))
    assert result["sample_findings"]
    for finding in result["sample_findings"] + findings(grove):
        assert finding["kind"] == "map_untested" and KEY.match(finding["key"])


def test_scan_gaps_and_recommend_show_the_key_on_both_surfaces(
    home: Path, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def cli(*args: str) -> dict:
        assert main(["--home", str(home), *args]) == 0
        return json.loads(capsys.readouterr().out)["data"]

    def mcp(name: str, **arguments) -> dict:
        envelope = call_tool(home, name, arguments)
        assert envelope["ok"], envelope
        return envelope["data"]

    cli("project", "create", "proj", "--root", str(root))
    scanned = cli("scan", "proj")
    stored = {finding["key"] for finding in cli("gaps", "proj")["items"]}
    assert stored and all(KEY.match(key) for key in stored)
    assert scanned["sample_findings"] and {finding["key"] for finding in scanned["sample_findings"]} <= stored
    assert cli("recommend", "proj")["finding"]["key"] in stored

    assert {finding["key"] for finding in mcp("grove_gaps", project="proj")["items"]} == stored
    assert mcp("grove_recommend_next", project="proj")["finding"]["key"] in stored
    rescanned = mcp("grove_scan", project="proj")
    assert {finding["key"] for finding in rescanned["sample_findings"]} <= stored


def test_a_version_4_database_gets_the_keys_a_fresh_scan_gives(tmp_path: Path, root: Path) -> None:
    (root / "README.md").write_text(README + "\n## Again\n\n- Parses a config file.\n")
    map_file = tmp_path / "map.md"
    map_file.write_text("# Map\n\n## Risks\n\n- Zork is never exercised. (`untested`)\n")
    with Grove(tmp_path / "new") as grove:
        grove.project_create("proj", str(root))
        grove.scan("proj")
        grove.ingest_map("proj", str(map_file))
        fresh = [(finding["id"], finding["kind"], finding["key"]) for finding in findings(grove)]
        assert {kind for _id, kind, _key in fresh} == set(FINDING_KINDS)
        assert any("#2" in key for _id, _kind, key in fresh)

    # The same rows as an older Grove stored them: no key column at all.
    old_home = tmp_path / "old"
    old_home.mkdir()
    old = sqlite3.connect(old_home / "grove.db")
    for script in MIGRATIONS[:4]:
        for statement in _split_statements(script):
            old.execute(statement)
    old.execute("PRAGMA user_version = 4")
    assert "key" not in [column[1] for column in old.execute("PRAGMA table_info(findings)")]
    new = sqlite3.connect(tmp_path / "new" / "grove.db")
    for table in ("projects", "blueprint_items", "findings"):
        columns = ", ".join(column[1] for column in old.execute(f"PRAGMA table_info({table})"))
        marks = ", ".join("?" for _ in columns.split(", "))
        old.executemany(f"INSERT INTO {table} ({columns}) VALUES ({marks})", new.execute(f"SELECT {columns} FROM {table}"))
    new.close()
    old.commit()
    old.close()

    with Grove(old_home) as grove:
        assert grove.conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) >= 5
        assert [(finding["id"], finding["kind"], finding["key"]) for finding in findings(grove)] == fresh
        assert grove.conn.execute("SELECT COUNT(*) FROM findings WHERE key IS NULL").fetchone()[0] == 0
        indexes = [row[1] for row in grove.conn.execute("PRAGMA index_list(findings)")]
        assert "findings_key" in indexes
        grove.scan("proj")  # and a scan after the upgrade keeps them
        assert [(finding["kind"], finding["key"]) for finding in findings(grove)] == [row[1:] for row in fresh]
