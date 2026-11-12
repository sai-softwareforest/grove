"""What a scan leaves out is named: changelogs, capped documents, skipped files, capped findings."""

from __future__ import annotations

from pathlib import Path

import pytest

from sf_grove import gaps as gaps_module
from sf_grove import scan as scan_module
from sf_grove.scan import MAX_FILE_BYTES, is_changelog_file, scan_tree
from sf_grove.service import Grove


def declared(result) -> list:
    return [item for item in result.items if item.layer == "declared"]


# -- changelogs ---------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "CHANGELOG.md",
        "changelog",
        "HISTORY.rst",
        "CHANGES.txt",
        "NEWS.md",
        "RELEASE-NOTES.md",
        "release_notes.md",
        "docs/changelog.md",
        "docs/releases/v1.2.md",
        "changelog.d/123.feature.md",
        "pkg/CHANGELOG.md",
    ],
)
def test_changelog_paths_are_recognised(path: str) -> None:
    assert is_changelog_file(path)


@pytest.mark.parametrize("path", ["README.md", "docs/guide.md", "docs/releasing.md", "RELEASE.md", "history.py", "docs/releases/README.md"])
def test_other_paths_are_not_changelogs(path: str) -> None:
    assert not is_changelog_file(path)


def test_changelogs_add_no_declared_items_and_use_no_cap(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("# Proj\n\nProj parses configuration files.\n")
    entries = "\n".join(f"- Fixed crash number {index} when parsing configs." for index in range(1500))
    (root / "CHANGELOG.md").write_text(f"# Changelog\n\n## 1.0\n\n{entries}\n")
    (root / "HISTORY.md").write_text("# History\n\nThe parser used to reject tabs.\n")
    (root / "docs" / "changelog.md").write_text("# Changes\n\nAdded a cache for parsed files.\n")

    result = scan_tree(root)
    assert {item.source_path for item in declared(result)} == {"README.md"}
    summary = result.summary()
    assert summary["changelog_files"]["total"] == 3
    assert summary["changelog_files"]["items"] == ["CHANGELOG.md", "HISTORY.md", "docs/changelog.md"]
    assert summary["caps"]["declared_capped"] == []
    assert not [warning for warning in summary["warnings"] if "CHANGELOG" in warning]
    assert result.files_seen == 4  # still walked and counted


# -- the per-document declared cap ------------------------------------------


def test_real_sized_docs_are_kept_whole(tmp_path: Path) -> None:
    # A config reference of ~500 items (499 in the trial) used to lose 99 to the old cap of 400.
    root = tmp_path / "proj"
    root.mkdir()
    lines = [f"The option number{index} controls cache size {index} for parsed files." for index in range(499)]
    (root / "README.md").write_text("# Config reference\n\n" + "\n\n".join(lines) + "\n")
    result = scan_tree(root)
    assert len(declared(result)) == 500
    assert result.summary()["caps"]["declared_capped"] == []


def test_capped_document_is_named_and_keeps_claims_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scan_module, "MAX_DECLARED_PER_FILE", 10)
    root = tmp_path / "proj"
    (root / "docs").mkdir(parents=True)
    setup = "\n\n".join(f"Run make target{index} before the tests." for index in range(12))  # setup class
    promises = "\n\n".join(f"The server never drops message kind{index} silently." for index in range(5))
    (root / "docs" / "rfc.md").write_text(f"# RFC\n\n## Usage notes\n\n{setup}\n\n## Guarantees\n\n{promises}\n")
    (root / "README.md").write_text("# Small\n\nThe tool never loses data.\n")

    result = scan_tree(root)
    rfc = [item for item in declared(result) if item.source_path == "docs/rfc.md"]
    assert len(rfc) == 10
    # Three headings and five promises are kept; only two setup sentences fit, in document order.
    assert sum(item.extra["kind"] == "heading" for item in rfc) == 3
    assert sum(item.extra.get("class") == "behaviour" for item in rfc) == 5
    assert [item.source_line for item in rfc] == sorted(item.source_line for item in rfc)

    capped = result.summary()["caps"]["declared_capped"]
    assert capped == [
        {"path": "docs/rfc.md", "total": 20, "kept": 10, "dropped": 10, "cap": 10, "dropped_by_class": {"setup": 10}}
    ]
    assert any(warning.startswith("docs/rfc.md: kept 10 of 20") for warning in result.warnings)


def test_capped_document_is_reported_by_scan_and_project_get(
    grove: Grove, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scan_module, "MAX_DECLARED_PER_FILE", 3)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_text("# P\n\n" + "\n\n".join(f"It handles case number{i} well." for i in range(6)))
    grove.project_create("proj", str(root))
    scanned = grove.scan("proj")
    entry = scanned["caps"]["declared_capped"][0]
    assert (entry["path"], entry["kept"], entry["dropped"]) == ("README.md", 3, 4)
    assert grove.project_get("proj")["last_scan"]["caps"]["declared_capped"] == [entry]


# -- skipped files ------------------------------------------------------------


def test_skipped_files_are_named(grove: Grove, tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "ok.py").write_text("def fine():\n    pass\n")
    (root / "pkg" / "blob.py").write_bytes(b"def x():\n\0\0\0binary")
    (root / "docs").mkdir()
    (root / "docs" / "huge.md").write_text("# Huge\n\n" + "word " * (MAX_FILE_BYTES // 5 + 10))
    grove.project_create("proj", str(root))

    scanned = grove.scan("proj")
    skipped = scanned["skipped_files"]
    assert skipped["total"] == 2 and skipped["omitted"] == 0
    by_path = {entry["path"]: entry for entry in skipped["items"]}
    assert by_path["pkg/blob.py"]["reason"] == "binary"
    assert by_path["docs/huge.md"]["reason"] == "too_large"
    assert by_path["docs/huge.md"]["bytes"] > MAX_FILE_BYTES
    warning = next(warning for warning in scanned["warnings"] if "skipped" in warning)
    assert "docs/huge.md" in warning and "pkg/blob.py" in warning
    assert grove.project_get("proj")["last_scan"]["skipped_files"] == skipped


def test_a_long_skipped_list_is_capped_with_the_true_count(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for index in range(60):
        (root / f"blob{index:02}.py").write_bytes(b"\0binary")
    summary = scan_tree(root).summary()
    skipped = summary["skipped_files"]
    assert skipped["total"] == 60 and len(skipped["items"]) == 50 and skipped["omitted"] == 10
    assert skipped["items"][0] == {"path": "blob00.py", "reason": "binary"}
    warning = next(warning for warning in summary["warnings"] if "skipped" in warning)
    assert warning.startswith("60 file(s) skipped") and "+50 more" in warning


# -- findings caps -------------------------------------------------------------


def test_findings_cap_reports_the_true_total(grove: Grove, tmp_path: Path) -> None:
    cap = gaps_module.MAX_UNDOCUMENTED
    candidates = cap + 16  # the trial: 41 candidates, cap 25
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "README.md").write_text("# Proj\n\nNothing about modules here.\n")
    for index in range(candidates):
        (root / "pkg" / f"zork{chr(97 + index // 26)}{chr(97 + index % 26)}.py").write_text("def f():\n    pass\n")
    grove.project_create("proj", str(root))

    scanned = grove.scan("proj")
    assert scanned["findings"]["actual_undocumented"] == cap
    cap_info = scanned["findings_cap"]
    assert cap_info["applied"] is True and cap_info["omitted"] == 16
    assert cap_info["kinds"]["actual_undocumented"] == {"cap": cap, "candidates": candidates, "stored": cap, "omitted": 16}
    assert f"{cap} of {candidates}" in cap_info["note"]

    listed = grove.gaps("proj", kind="actual_undocumented")
    assert listed["total"] == cap  # what can be paged
    assert listed["complete"] is False
    assert listed["omitted"] == 16 and listed["true_total"] == candidates
    assert listed["findings_cap"]["applied"] is True

    everything = grove.gaps("proj")
    assert everything["true_total"] == everything["total"] + 16 and everything["complete"] is False
    other = grove.gaps("proj", kind="declared_untested")
    assert other["complete"] is True and other["omitted"] == 0 and other["true_total"] == other["total"]

    project = grove.project_get("proj")
    assert project["findings_cap"] == cap_info
    assert project["counts"]["findings"]["actual_undocumented"] == cap
    assert project["counts"]["findings_omitted"]["actual_undocumented"] == 16
    assert grove.project_list()["items"][0]["findings_cap"]["omitted"] == 16


def test_no_cap_note_when_nothing_is_omitted(tiny: Grove) -> None:
    assert tiny.project_get("tiny")["findings_cap"] == {"applied": False, "omitted": 0, "kinds": {}, "note": None}
    tiny.scan("tiny")
    listed = tiny.gaps("tiny")
    assert listed["complete"] is True and listed["omitted"] == 0 and listed["true_total"] == listed["total"]
    assert listed["findings_cap"]["applied"] is False and listed["findings_cap"]["note"] is None
    assert listed["findings_cap"]["kinds"]["actual_undocumented"]["omitted"] == 0
