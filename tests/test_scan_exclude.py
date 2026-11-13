"""R-SCAN-9: a project's exclude list keeps paths out of its blueprint, and every scan says so."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import tree_snapshot
from sf_grove.cli import build_parser, main
from sf_grove.errors import GroveError
from sf_grove.scan import ExcludeError, scan_tree
from sf_grove.service import CLEAR_EXCLUDE, MAX_EXCLUDE_CHARS, MAX_EXCLUDE_PATTERNS, Grove
from sf_grove.tools import TOOLS_BY_NAME, call_tool


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A product with a pretend project under fixtures/, vendored code and a survey under docs/."""
    root = tmp_path / "proj"
    for directory in ("src", "tests", "fixtures/sample/src", "vendor/lib", "docs"):
        (root / directory).mkdir(parents=True)
    (root / "README.md").write_text("# Proj\n\nParses a config file.\n")
    (root / "src" / "config.py").write_text("def parse_config(path):\n    return {}\n")
    (root / "tests" / "test_config.py").write_text("def test_parse_config():\n    pass\n")
    (root / "fixtures" / "sample" / "README.md").write_text("# Sample\n\nGreets a user by name.\n")
    (root / "fixtures" / "sample" / "src" / "greet.py").write_text("def greet(name):\n    return name\n")
    (root / "vendor" / "lib" / "zork.py").write_text("def zork():\n    pass\n")
    (root / "docs" / "guide.md").write_text("# Guide\n\nThe parser rejects empty files.\n")
    (root / "docs" / "survey.md").write_text("# Survey\n\nOther tools render dashboards nightly.\n")
    (root / "docs" / "CHANGELOG.md").write_text("# Changes\n\nAdded a cache.\n")
    return root


@pytest.fixture
def proj(grove: Grove, root: Path) -> Grove:
    grove.project_create("proj", str(root))
    return grove


def sources(grove: Grove) -> set[str]:
    return {item["source_path"] for item in grove.blueprint_get("proj", limit=200)["items"]}


# -- the walk --------------------------------------------------------------------


def test_excluded_files_are_counted_and_never_become_items(root: Path) -> None:
    everything = scan_tree(root)
    assert everything.summary()["excluded"] == {"patterns": [], "files": 0}

    result = scan_tree(root, exclude=["fixtures/", "vendor/", "docs/survey.md"])
    assert {item.source_path for item in result.items} == {"README.md", "src/config.py", "tests/test_config.py", "docs/guide.md"}
    assert result.summary()["excluded"] == {"patterns": ["fixtures/", "vendor/", "docs/survey.md"], "files": 4}
    # Excluded files are not "seen": the two counts add up to the whole walk.
    assert result.files_seen + result.excluded_files == everything.files_seen
    # An excluded changelog is not listed as a changelog either.
    assert scan_tree(root, exclude=["docs/"]).summary()["changelog_files"]["total"] == 0


def test_patterns_are_gitignore_style_and_relative_to_the_root(root: Path) -> None:
    def kept(*patterns: str) -> set[str]:
        return {item.source_path for item in scan_tree(root, exclude=patterns).items}

    assert "fixtures/sample/src/greet.py" in kept("/src/")  # anchored: only the top-level src
    assert "src/config.py" not in kept("/src/")
    assert not {path for path in kept("src/") if "/src/" in f"/{path}"}  # unanchored: any src directory
    assert not {path for path in kept("*.py") if path.endswith(".py")}
    # A later negation brings a file back, even from under an excluded directory.
    assert {path for path in kept("docs/", "!docs/guide.md") if path.startswith("docs/")} == {"docs/guide.md"}
    # A list that matches nothing shows a count of zero, so a mistyped pattern is visible.
    assert scan_tree(root, exclude=["fixture/"]).excluded_files == 0


def test_excluded_files_do_not_use_up_the_file_cap(root: Path) -> None:
    kept = scan_tree(root, exclude=["fixtures/", "vendor/", "docs/"])
    assert kept.files_seen == 3
    capped = scan_tree(root, max_files=3, exclude=["fixtures/", "vendor/", "docs/"])
    assert capped.caps_hit == [] and capped.files_seen == 3 and capped.excluded_files == kept.excluded_files


def test_the_time_cap_holds_while_excluded_files_are_passed_over(root: Path) -> None:
    result = scan_tree(root, max_seconds=1e-9, exclude=["*"])
    assert result.caps_hit == ["max_seconds"] and result.files_seen == 0 and result.excluded_files == 0
    assert any("max_seconds" in warning for warning in result.warnings)


def test_a_pattern_that_cannot_be_compiled_is_refused_before_the_walk(root: Path) -> None:
    with pytest.raises(ExcludeError):
        scan_tree(root, exclude=["docs/", "!"])


# -- stored on the project -------------------------------------------------------


def test_every_scan_result_reports_excluded(proj: Grove) -> None:
    first = proj.scan("proj")
    assert first["excluded"] == {"patterns": [], "files": 0}
    assert "fixtures/sample/src/greet.py" in sources(proj) and "vendor/lib/zork.py" in sources(proj)

    scanned = proj.scan("proj", exclude=["fixtures/", "vendor/"])
    assert scanned["excluded"] == {"patterns": ["fixtures/", "vendor/"], "files": 3}
    assert scanned["files_seen"] == first["files_seen"] - 3
    assert not {path for path in sources(proj) if path.startswith(("fixtures/", "vendor/"))}
    # The project shows the list that produced its blueprint.
    assert proj.project_get("proj")["last_scan"]["excluded"] == scanned["excluded"]


def test_the_stored_list_applies_when_exclude_is_omitted(proj: Grove) -> None:
    given = proj.scan("proj", exclude=["fixtures/", "vendor/", "docs/survey.md"])
    again = proj.scan("proj")  # no argument: the stored list applies
    assert again["excluded"] == given["excluded"] == {"patterns": ["fixtures/", "vendor/", "docs/survey.md"], "files": 4}
    for key in ("items", "findings", "files_seen", "files_read", "gap_notes"):
        assert again[key] == given[key], key
    # It is stored in the database, not in the process: a new connection sees it too.
    with Grove(proj.home) as other:
        assert other.scan("proj")["excluded"] == given["excluded"]


def test_a_given_list_replaces_the_stored_one(proj: Grove) -> None:
    proj.scan("proj", exclude=["fixtures/", "vendor/"])
    replaced = proj.scan("proj", exclude=["docs/survey.md"])
    assert replaced["excluded"] == {"patterns": ["docs/survey.md"], "files": 1}  # replaced, not added to
    assert "vendor/lib/zork.py" in sources(proj) and "docs/survey.md" not in sources(proj)
    assert proj.scan("proj")["excluded"]["patterns"] == ["docs/survey.md"]
    # Blank entries match nothing, as blank lines in a .gitignore do; beside a pattern they are dropped.
    assert proj.scan("proj", exclude=["", "vendor/", "  "])["excluded"] == {"patterns": ["vendor/"], "files": 1}


@pytest.mark.parametrize("empty", [[], (), [""], ["", "  "]], ids=["list", "tuple", "one blank", "only blanks"])
def test_an_empty_list_keeps_the_stored_one(proj: Grove, empty: object) -> None:
    """A client that fills in defaults sends [] without meaning it; the user's list must survive that (D-41)."""
    given = proj.scan("proj", exclude=["fixtures/", "vendor/"])
    kept = proj.scan("proj", exclude=empty)
    # The result reports the list the scan really used: the stored one, not the empty one it was sent.
    assert kept["excluded"] == given["excluded"] == {"patterns": ["fixtures/", "vendor/"], "files": 3}
    for key in ("items", "findings", "files_seen", "files_read", "gap_notes"):
        assert kept[key] == given[key], key
    assert not {path for path in sources(proj) if path.startswith(("fixtures/", "vendor/"))}
    assert proj.project_get("proj")["last_scan"]["excluded"] == given["excluded"]
    # The stored list itself is untouched: a new connection and a later scan still apply it.
    with Grove(proj.home) as other:
        assert other.scan("proj")["excluded"] == given["excluded"]


def test_an_empty_list_on_a_project_without_a_list_excludes_nothing(proj: Grove) -> None:
    assert proj.scan("proj", exclude=[])["excluded"] == {"patterns": [], "files": 0}
    assert proj.scan("proj")["excluded"] == {"patterns": [], "files": 0}


@pytest.mark.parametrize("clear", [[CLEAR_EXCLUDE], ["", CLEAR_EXCLUDE, "  "]], ids=["alone", "beside blanks"])
def test_only_the_sentinel_clears_the_stored_list(proj: Grove, clear: list[str]) -> None:
    assert CLEAR_EXCLUDE == "!"  # the documented spelling; it is part of the interface
    proj.scan("proj", exclude=["docs/survey.md"])
    assert "docs/survey.md" not in sources(proj)

    cleared = proj.scan("proj", exclude=clear)
    # The sentinel is an instruction, not a pattern: the result shows the empty list that was used.
    assert cleared["excluded"] == {"patterns": [], "files": 0}
    assert "docs/survey.md" in sources(proj)
    assert proj.project_get("proj")["last_scan"]["excluded"] == {"patterns": [], "files": 0}
    assert proj.conn.execute("SELECT exclude FROM projects WHERE name = 'proj'").fetchone()[0] is None
    assert proj.scan("proj")["excluded"] == {"patterns": [], "files": 0}  # and it stays cleared
    assert proj.scan("proj", exclude=[])["excluded"] == {"patterns": [], "files": 0}
    # Clearing a list that is already empty is not an error.
    assert proj.scan("proj", exclude=[CLEAR_EXCLUDE])["excluded"] == {"patterns": [], "files": 0}


def test_the_sentinel_is_not_a_pattern_and_a_file_of_that_name_is_still_reachable(proj: Grove, root: Path) -> None:
    (root / "src" / CLEAR_EXCLUDE).write_text("odd name\n")
    # Alone it clears, so it never excludes the file; escaped, as in a .gitignore, it is an ordinary pattern.
    assert proj.scan("proj", exclude=[CLEAR_EXCLUDE])["excluded"] == {"patterns": [], "files": 0}
    assert proj.scan("proj", exclude=["\\" + CLEAR_EXCLUDE])["excluded"] == {"patterns": ["\\!"], "files": 1}
    # Negations, which begin with the same character, are ordinary patterns too.
    listed = proj.scan("proj", exclude=["docs/", "!docs/guide.md"])["excluded"]
    assert listed == {"patterns": ["docs/", "!docs/guide.md"], "files": 2}


def test_excluding_fixtures_removes_their_findings(proj: Grove) -> None:
    def summaries() -> str:
        return " ".join(finding["summary"] for finding in proj.gaps("proj", limit=200)["items"])

    proj.scan("proj")
    assert "Greets a user by name" in summaries() and "vendor/lib/zork.py" in summaries()
    proj.scan("proj", exclude=["fixtures/", "vendor/"])
    assert "Greets a user by name" not in summaries() and "vendor/lib/zork.py" not in summaries()


def test_the_list_is_per_project_and_nothing_is_written_in_the_project(proj: Grove, root: Path) -> None:
    before = tree_snapshot(root)
    proj.project_create("twin", str(root))
    proj.scan("proj", exclude=["fixtures/"])
    assert proj.scan("twin")["excluded"] == {"patterns": [], "files": 0}
    assert proj.scan("proj")["excluded"]["patterns"] == ["fixtures/"]
    assert tree_snapshot(root) == before


@pytest.mark.parametrize(
    "bad",
    [
        "fixtures/",  # a bare string, not a list
        ["fixtures/", 7],
        {"fixtures/": True},
        ["x"] * (MAX_EXCLUDE_PATTERNS + 1),
        ["x" * (MAX_EXCLUDE_CHARS + 1)],
        ["fixtures/\nvendor/"],
        ["docs/", "a\\"],  # not a pattern pathspec can compile
        ["docs/", CLEAR_EXCLUDE],  # the sentinel clears; beside a pattern the caller's intent is unknown
        [CLEAR_EXCLUDE, CLEAR_EXCLUDE],
        [CLEAR_EXCLUDE + " "],  # only the exact entry is the sentinel; this is a pattern, and not a valid one
    ],
    ids=[
        "string",
        "non-string entry",
        "mapping",
        "too many",
        "too long",
        "two lines",
        "uncompilable",
        "sentinel beside a pattern",
        "sentinel twice",
        "sentinel with a space",
    ],
)
def test_a_bad_list_is_invalid_and_changes_nothing(proj: Grove, bad: object) -> None:
    proj.scan("proj", exclude=["vendor/"])
    before = (sources(proj), proj.project_get("proj")["last_scan"])
    with pytest.raises(GroveError) as raised:
        proj.scan("proj", exclude=bad)
    assert raised.value.code == "invalid" and "exclude" in raised.value.message
    assert (sources(proj), proj.project_get("proj")["last_scan"]) == before
    assert proj.scan("proj")["excluded"]["patterns"] == ["vendor/"]  # the stored list is untouched


def test_the_limits_themselves_are_accepted(proj: Grove) -> None:
    patterns = [f"dir{index}/" for index in range(MAX_EXCLUDE_PATTERNS - 1)] + ["x" * MAX_EXCLUDE_CHARS]
    assert proj.scan("proj", exclude=patterns)["excluded"] == {"patterns": patterns, "files": 0}


# -- both surfaces ---------------------------------------------------------------


def test_exclude_through_the_mcp_tool(home: Path, root: Path) -> None:
    schema = TOOLS_BY_NAME["grove_scan"].schema
    assert schema["properties"]["exclude"]["type"] == "array" and "exclude" not in schema["required"]
    assert schema["properties"]["exclude"]["maxItems"] == MAX_EXCLUDE_PATTERNS
    assert "excluded" in TOOLS_BY_NAME["grove_scan"].description

    assert call_tool(home, "grove_project_create", {"name": "proj", "root_path": str(root)})["ok"]
    given = call_tool(home, "grove_scan", {"project": "proj", "exclude": ["fixtures/", "vendor/"]})
    assert given["ok"] and given["data"]["excluded"] == {"patterns": ["fixtures/", "vendor/"], "files": 3}
    assert call_tool(home, "grove_scan", {"project": "proj"})["data"]["excluded"] == given["data"]["excluded"]
    # A null argument means "not given", as for every other optional parameter.
    assert call_tool(home, "grove_scan", {"project": "proj", "exclude": None})["data"]["excluded"]["files"] == 3
    refused = call_tool(home, "grove_scan", {"project": "proj", "exclude": "fixtures/"})
    assert refused["ok"] is False and refused["error"]["code"] == "invalid"


def test_keep_replace_and_clear_through_the_mcp_tool(home: Path, root: Path) -> None:
    def scan(**arguments: object) -> dict:
        result = call_tool(home, "grove_scan", {"project": "proj", **arguments})
        assert result["ok"], result
        return result["data"]["excluded"]

    # The description is all a client reads: it names the sentinel and says what an empty list does.
    described = TOOLS_BY_NAME["grove_scan"].schema["properties"]["exclude"]["description"]
    assert f'["{CLEAR_EXCLUDE}"] clears it' in described and "omitted or [] keeps the stored list" in described

    assert call_tool(home, "grove_project_create", {"name": "proj", "root_path": str(root)})["ok"]
    stored = {"patterns": ["fixtures/", "vendor/"], "files": 3}
    assert scan(exclude=["fixtures/", "vendor/"]) == stored
    assert scan() == stored  # omitted keeps
    assert scan(exclude=[]) == stored  # empty keeps, and the result shows the list really used
    assert scan(exclude=[""]) == stored
    assert scan() == stored  # the empty list changed nothing for later scans
    assert scan(exclude=["docs/survey.md"]) == {"patterns": ["docs/survey.md"], "files": 1}  # a normal list replaces
    assert scan() == {"patterns": ["docs/survey.md"], "files": 1}
    assert scan(exclude=[CLEAR_EXCLUDE]) == {"patterns": [], "files": 0}  # the sentinel clears
    assert scan() == {"patterns": [], "files": 0}
    assert scan(exclude=[]) == {"patterns": [], "files": 0}

    refused = call_tool(home, "grove_scan", {"project": "proj", "exclude": ["vendor/", CLEAR_EXCLUDE]})
    assert refused["ok"] is False and refused["error"]["code"] == "invalid"
    assert "only entry" in refused["error"]["message"]
    assert scan() == {"patterns": [], "files": 0}


def test_exclude_through_the_cli(home: Path, root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def cli(*args: str, expect: int = 0) -> dict:
        assert main(["--home", str(home), *args]) == expect
        envelope = json.loads(capsys.readouterr().out)
        return envelope["data"] if expect == 0 else envelope["error"]

    cli("project", "create", "proj", "--root", str(root))
    assert cli("scan", "proj")["excluded"] == {"patterns": [], "files": 0}
    given = cli("scan", "proj", "--exclude", "fixtures/", "--exclude", "vendor/")
    assert given["excluded"] == {"patterns": ["fixtures/", "vendor/"], "files": 3}
    assert cli("scan", "proj")["excluded"] == given["excluded"]
    assert cli("project", "get", "proj")["last_scan"]["excluded"] == given["excluded"]
    # An empty --exclude keeps the stored list, as leaving the flag out does; the result shows the list used.
    assert cli("scan", "proj", "--exclude", "")["excluded"] == given["excluded"]
    assert cli("scan", "proj", "--exclude", "", "--exclude", " ")["excluded"] == given["excluded"]
    assert cli("scan", "proj")["excluded"] == given["excluded"]
    # A normal list replaces it.
    replaced = cli("scan", "proj", "--exclude", "docs/survey.md")
    assert replaced["excluded"] == {"patterns": ["docs/survey.md"], "files": 1}
    assert cli("scan", "proj")["excluded"] == replaced["excluded"]
    # Beside a pattern the sentinel is refused, and the stored list stays.
    refused = cli("scan", "proj", "--exclude", "vendor/", "--exclude", CLEAR_EXCLUDE, expect=1)
    assert refused["code"] == "invalid" and "only entry" in refused["message"]
    assert cli("scan", "proj")["excluded"] == replaced["excluded"]
    # Alone it clears, the same as on the MCP.
    assert cli("scan", "proj", "--exclude", CLEAR_EXCLUDE)["excluded"] == {"patterns": [], "files": 0}
    assert cli("scan", "proj")["excluded"] == {"patterns": [], "files": 0}
    assert cli("project", "get", "proj")["last_scan"]["excluded"] == {"patterns": [], "files": 0}
    scan_help = build_parser()._subparsers._group_actions[0].choices["scan"].format_help()  # noqa: SLF001
    assert f"--exclude '{CLEAR_EXCLUDE}' alone clears it" in " ".join(scan_help.split())

    assert main(["--home", str(home), "--text", "scan", "proj", "--exclude", "docs/survey.md"]) == 0
    assert "excluded:" in capsys.readouterr().out
