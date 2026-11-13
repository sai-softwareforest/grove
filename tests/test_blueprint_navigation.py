"""Finding a part of a blueprint without paging all of it (R-GROK-8, WO-16).

`summary` lists the source files with their item count in each layer, and
`source_path` reads one file or one directory. Each is tested on the service,
through the MCP tool table and through the CLI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import MAP_SAMPLE
from sf_grove.cli import main
from sf_grove.service import Grove
from sf_grove.tools import TOOLS_BY_NAME, call_tool

FILES = {
    "README.md": "# Proj\n\nThe parser reads every record from the input file.\n\nThe writer must flush all records on close.\n",
    "docs/guide.md": "# Guide\n\nThe exporter writes one line for each record.\n",
    "docs/deep/notes.md": "# Notes\n\nThe importer skips every blank line it reads.\n",
    "docs_extra.md": "# Not under docs\n\nThis file only looks like part of the docs directory.\n",
    "src/app.py": "def parse(text):\n    return text\n\n\ndef write(records):\n    return records\n",
    "src/App.py": "def other():\n    return 1\n",
    "src/a_b.py": "def underscore():\n    return 1\n",
    "src/a%b.py": "def percent():\n    return 1\n",
    "src/axb.py": "def plain():\n    return 1\n",
    "tests/test_app.py": "def test_parse():\n    assert True\n\n\ndef test_write():\n    assert True\n",
}
# Per source file: declared, actual, tests. A document gives its heading and its sentences;
# a module gives itself and its functions; a test file gives itself and its tests.
EXPECTED = {
    "README.md": (3, 0, 0),
    "docs/deep/notes.md": (2, 0, 0),
    "docs/guide.md": (2, 0, 0),
    "src/App.py": (0, 2, 0),
    "src/a%b.py": (0, 2, 0),
    "src/a_b.py": (0, 2, 0),
    "src/app.py": (0, 3, 0),
    "src/axb.py": (0, 2, 0),
    "tests/test_app.py": (0, 0, 3),
}
ROW_KEYS = ["source_path", "declared", "actual", "tests"]


def rows(expected: dict[str, tuple[int, int, int]]) -> list[dict]:
    """The summary rows of ``expected``, in the order Grove returns them: by path."""
    return [dict(zip(ROW_KEYS, (path, *counts))) for path, counts in sorted(expected.items())]


def under(prefix: str) -> dict[str, tuple[int, int, int]]:
    return {path: counts for path, counts in EXPECTED.items() if path.startswith(prefix)}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    for name, text in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def proj(grove: Grove, root: Path) -> Grove:
    grove.project_create("proj", str(root))
    grove.scan("proj")
    return grove


def all_items(grove: Grove, **filters) -> list[dict]:
    return grove.blueprint_get("proj", limit=200, **filters)["items"]


def test_the_fixture_is_what_the_expected_counts_say(proj: Grove) -> None:
    """The counts above are compared with the items themselves, not with the summary."""
    counted: dict[str, list[int]] = {}
    for item in all_items(proj):
        counted.setdefault(item["source_path"], [0, 0, 0])[ROW_KEYS.index(item["layer"]) - 1] += 1
    assert {path: tuple(counts) for path, counts in counted.items()} == EXPECTED
    # "docs_extra.md" is not a document the scanner reads; it is in the tree to show that
    # the prefix "docs/" is a path prefix and takes nothing that merely starts with "docs".
    assert "docs_extra.md" not in EXPECTED


def test_summary_lists_each_source_file_with_its_counts_and_no_item(proj: Grove) -> None:
    summary = proj.blueprint_get("proj", summary=True)
    assert summary["items"] == rows(EXPECTED)
    assert [list(row) for row in summary["items"]] == [ROW_KEYS] * len(EXPECTED)
    # The page counts files, and carries what an item page carries around its items.
    assert summary["total"] == len(EXPECTED) == 9
    full = proj.blueprint_get("proj")
    assert {key: value for key, value in summary.items() if key != "items"} == {
        **{key: value for key, value in full.items() if key != "items"},
        "total": 9,
    }
    assert full["total"] == sum(sum(counts) for counts in EXPECTED.values()) == 21


def test_summary_is_paged_by_file(proj: Grove) -> None:
    expected = rows(EXPECTED)
    pages = [proj.blueprint_get("proj", summary=True, limit=4, offset=offset) for offset in (0, 4, 8, 12)]
    assert [page["items"] for page in pages] == [expected[0:4], expected[4:8], expected[8:9], []]
    assert all(page["total"] == 9 and page["limit"] == 4 for page in pages)
    assert [page["offset"] for page in pages] == [0, 4, 8, 12]
    # The page rules are the ones every list has (R-IF-6).
    assert proj.blueprint_get("proj", summary=True, limit=500)["limit"] == 200
    for bad in ({"limit": 0}, {"offset": -1}):
        with pytest.raises(Exception) as caught:
            proj.blueprint_get("proj", summary=True, **bad)
        assert caught.value.code == "invalid"


def test_the_filters_narrow_the_summary(proj: Grove) -> None:
    # A layer: only the files that have items in it, and only that layer is counted.
    assert proj.blueprint_get("proj", summary=True, layer="tests")["items"] == rows({"tests/test_app.py": (0, 0, 3)})
    declared = proj.blueprint_get("proj", summary=True, layer="declared")
    assert [row["source_path"] for row in declared["items"]] == ["README.md", "docs/deep/notes.md", "docs/guide.md"]
    assert all(row["actual"] == 0 and row["tests"] == 0 for row in declared["items"])
    # A query: the files with a matching item, and the number of matching items.
    # ("records" is also in the signature of write() in src/app.py, which is the body of that item.)
    matched = proj.blueprint_get("proj", summary=True, query="record")
    assert matched["items"] == rows({"README.md": (2, 0, 0), "docs/guide.md": (1, 0, 0), "src/app.py": (0, 1, 0)})
    assert proj.blueprint_get("proj", query="record")["total"] == 4
    # A directory, and all three together.
    assert proj.blueprint_get("proj", summary=True, source_path="docs/")["items"] == rows(under("docs/"))
    narrowed = proj.blueprint_get("proj", summary=True, layer="declared", query="line", source_path="docs/")
    assert narrowed["items"] == rows({"docs/deep/notes.md": (1, 0, 0), "docs/guide.md": (1, 0, 0)})
    assert narrowed["total"] == 2


def test_source_path_reads_one_file(proj: Grove) -> None:
    page = proj.blueprint_get("proj", source_path="src/app.py")
    assert page["total"] == 3
    assert [(item["layer"], item["title"]) for item in page["items"]] == [
        ("actual", "src/app.py"),
        ("actual", "parse"),
        ("actual", "write"),
    ]
    assert {item["source_path"] for item in page["items"]} == {"src/app.py"}
    # Items keep their shape: a path filter is not a second result shape.
    assert list(page["items"][0]) == list(proj.blueprint_get("proj", limit=1)["items"][0])
    # What the summary says a file holds is what reading the file returns.
    for row in proj.blueprint_get("proj", summary=True)["items"]:
        read = proj.blueprint_get("proj", source_path=row["source_path"])
        assert read["total"] == row["declared"] + row["actual"] + row["tests"], row


def test_source_path_is_the_whole_path_or_a_prefix_that_ends_in_a_slash(proj: Grove) -> None:
    def paths(source_path: str) -> set[str]:
        return {item["source_path"] for item in all_items(proj, source_path=source_path)}

    assert paths("docs/") == {"docs/guide.md", "docs/deep/notes.md"}
    assert paths("docs/deep/") == {"docs/deep/notes.md"}
    assert paths("src/") == set(under("src/"))
    # Without the slash it is a whole path, and "docs" is not the path of any item.
    assert paths("docs") == set()
    assert paths("docs/guide") == set() and paths("src/app") == set()
    # A prefix is the start of the path, not a part of it.
    assert paths("deep/") == set() and paths("app.py") == set()
    # Paths are written as items show them: relative to the project root.
    assert paths("./src/app.py") == set() and paths("/src/") == set()


def test_source_path_is_matched_exactly(proj: Grove, root: Path) -> None:
    def paths(source_path: str) -> set[str]:
        return {item["source_path"] for item in all_items(proj, source_path=source_path)}

    # Case counts, as it does in the tree (the query filter ignores it).
    assert paths("src/app.py") == {"src/app.py"} and paths("src/App.py") == {"src/App.py"}
    assert paths("SRC/") == set() and paths("src/APP.PY") == set()
    # "_" and "%" are characters of a path, never wildcards.
    assert paths("src/a_b.py") == {"src/a_b.py"}
    assert paths("src/a%b.py") == {"src/a%b.py"}
    assert paths("src/%") == set() and paths("%/") == set() and paths("src_/") == set()
    # An absolute path of a scanned file is not how an item shows it.
    assert paths(str(root / "src" / "app.py")) == set() and paths(str(root) + "/") == set()


def test_source_path_pages_like_any_other_filter(proj: Grove) -> None:
    everything = all_items(proj, source_path="src/")
    assert len(everything) == 11
    pages = [proj.blueprint_get("proj", source_path="src/", limit=4, offset=offset) for offset in (0, 4, 8)]
    assert [item for page in pages for item in page["items"]] == everything
    assert all(page["total"] == 11 for page in pages)
    # With the other two filters.
    assert proj.blueprint_get("proj", source_path="src/", layer="tests")["total"] == 0
    hits = proj.blueprint_get("proj", source_path="src/", layer="actual", query="PARSE")
    assert [item["title"] for item in hits["items"]] == ["src/app.py", "parse"]  # the module's body names its symbols
    assert proj.blueprint_get("proj", source_path="src/a_b.py", query="PARSE")["total"] == 0


def test_a_blank_source_path_is_no_filter_and_a_wrong_type_is_refused(proj: Grove) -> None:
    everything = proj.blueprint_get("proj")["total"]
    for blank in (None, "", "   "):
        assert proj.blueprint_get("proj", source_path=blank)["total"] == everything
        assert proj.blueprint_get("proj", summary=True, source_path=blank)["total"] == 9
    # No file: an empty page, not an error. The set of paths is open, unlike the layers.
    assert proj.blueprint_get("proj", source_path="no/such/file.py") == {
        **proj.blueprint_get("proj", limit=1),
        "items": [],
        "total": 0,
        "limit": 50,
    }
    for bad in (7, ["src/"], True):
        with pytest.raises(Exception) as caught:
            proj.blueprint_get("proj", source_path=bad)
        assert (caught.value.code, caught.value.message) == ("invalid", "source_path must be a string")


def test_summary_is_true_or_false_and_false_changes_nothing(proj: Grove) -> None:
    plain = proj.blueprint_get("proj")
    assert proj.blueprint_get("proj", summary=False) == plain
    assert proj.blueprint_get("proj", summary=None) == plain
    for bad in ("true", "yes", 1, 0):
        with pytest.raises(Exception) as caught:
            proj.blueprint_get("proj", summary=bad)
        assert (caught.value.code, caught.value.message) == ("invalid", "summary must be true or false")


def test_a_project_that_was_never_scanned_has_an_empty_summary(grove: Grove, root: Path) -> None:
    grove.project_create("proj", str(root))
    summary = grove.blueprint_get("proj", summary=True)
    assert summary == {"items": [], "total": 0, "offset": 0, "limit": 50, "project": "proj", "last_scanned_at": None}
    with pytest.raises(Exception) as caught:
        grove.blueprint_get("missing", summary=True)
    assert caught.value.code == "not_found"


def test_items_seeded_by_a_map_are_listed_under_the_map_file(proj: Grove) -> None:
    """A map's items carry the map's own path, which is absolute: the summary shows it, and it reads back."""
    seeded = proj.ingest_map("proj", str(MAP_SAMPLE))["seeded"]
    map_path = str(MAP_SAMPLE.resolve())
    summary = proj.blueprint_get("proj", summary=True)
    assert summary["total"] == 10
    row = next(row for row in summary["items"] if row["source_path"] == map_path)
    assert (row["declared"], row["actual"], row["tests"]) == (seeded["declared"], seeded["actual"], 0)
    assert row["declared"] > 0 and row["actual"] > 0
    read = proj.blueprint_get("proj", source_path=map_path)
    assert read["total"] == row["declared"] + row["actual"]
    assert {item["origin"] for item in read["items"]} == {"map"}
    # A prefix works on such a path as on any other.
    assert proj.blueprint_get("proj", source_path=str(MAP_SAMPLE.resolve().parent) + "/")["total"] == read["total"]


def test_the_summary_of_a_large_blueprint_is_a_fraction_of_one_page_of_it(grove: Grove, tmp_path: Path) -> None:
    """R-GROK-8, measured: forty documents of forty sentences each."""
    root = tmp_path / "big"
    (root / "docs").mkdir(parents=True)
    for number in range(40):
        sentences = "\n\n".join(
            f"Rule {number}-{line}: the service must keep record {line} of batch {number} until it is read."
            for line in range(40)
        )
        (root / "docs" / f"part{number:02d}.md").write_text(f"# Part {number}\n\n{sentences}\n", encoding="utf-8")
    grove.project_create("big", str(root))
    assert grove.scan("big")["items"]["declared"] == 40 * 41
    summary = grove.blueprint_get("big", summary=True)
    assert summary["total"] == 40 and len(summary["items"]) == 40
    assert all(row == {"source_path": row["source_path"], "declared": 41, "actual": 0, "tests": 0} for row in summary["items"])
    one_page = grove.blueprint_get("big", layer="declared")
    assert one_page["total"] == 1640 and len(one_page["items"]) == 50
    # Every file of the project in one call, for less than a quarter of one default page of
    # items; and the layer is thirty-three such pages.
    assert len(json.dumps(summary)) * 4 < len(json.dumps(one_page))
    # And one file is one call: nothing of the other thirty-nine is paged.
    one_file = grove.blueprint_get("big", source_path="docs/part17.md")
    assert one_file["total"] == 41 and len(one_file["items"]) == 41


# -- both surfaces ----------------------------------------------------------


def check_the_surface(summary: dict, by_layer: dict, directory: dict, one_file: dict, paged: dict) -> None:
    assert summary["items"] == rows(EXPECTED) and summary["total"] == 9
    assert by_layer["items"] == rows({"tests/test_app.py": (0, 0, 3)})
    assert directory["items"] == rows(under("docs/")) and directory["total"] == 2
    assert [item["title"] for item in one_file["items"]] == ["src/app.py", "parse", "write"]
    assert one_file["total"] == 3
    assert paged["items"] == rows(EXPECTED)[2:4] and (paged["total"], paged["limit"], paged["offset"]) == (9, 2, 2)


def test_summary_and_source_path_through_the_mcp_tools(root: Path, home: Path) -> None:
    def tool(**arguments) -> dict:
        envelope = call_tool(home, "grove_blueprint_get", {"project": "proj", **arguments})
        assert envelope["ok"] is True, envelope
        return envelope["data"]

    def refused(**arguments) -> dict:
        envelope = call_tool(home, "grove_blueprint_get", {"project": "proj", **arguments})
        assert envelope["ok"] is False, envelope
        return envelope["error"]

    assert call_tool(home, "grove_project_create", {"name": "proj", "root_path": str(root)})["ok"]
    assert call_tool(home, "grove_scan", {"project": "proj"})["ok"]
    check_the_surface(
        tool(summary=True),
        tool(summary=True, layer="tests"),
        tool(summary=True, source_path="docs/"),
        tool(source_path="src/app.py"),
        tool(summary=True, limit=2, offset=2),
    )
    # Left out, null or false: the items, as before the parameters existed.
    plain = tool()
    assert tool(summary=False) == plain and tool(summary=None, source_path=None) == plain
    assert list(plain["items"][0]) == ["id", "layer", "title", "body", "source_path", "source_line", "origin", "extra"]
    assert refused(summary="true") == {"code": "invalid", "message": "summary must be true or false"}
    assert refused(source_path=3) == {"code": "invalid", "message": "source_path must be a string"}
    assert refused(sourcePath="src/")["code"] == "invalid"  # an unknown spelling is refused, not ignored (R-COMPAT-3)


def test_summary_and_source_path_through_the_cli(root: Path, home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def cli(*args: str, expect: int = 0) -> dict:
        assert main(["--home", str(home), *args]) == expect
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["ok"] is (expect == 0)
        return envelope["data"] if expect == 0 else envelope["error"]

    cli("project", "create", "proj", "--root", str(root))
    cli("scan", "proj")
    check_the_surface(
        cli("blueprint", "proj", "--summary"),
        cli("blueprint", "proj", "--summary", "--layer", "tests"),
        cli("blueprint", "proj", "--summary", "--source-path", "docs/"),
        cli("blueprint", "proj", "--source-path", "src/app.py"),
        cli("blueprint", "proj", "--summary", "--limit", "2", "--offset", "2"),
    )
    # Without the flags the command is what it was.
    plain = cli("blueprint", "proj")
    assert plain["total"] == 21
    assert list(plain["items"][0]) == ["id", "layer", "title", "body", "source_path", "source_line", "origin", "extra"]
    # --summary is a switch and takes no value; --source-path needs one. Usage mistakes are envelopes (R-IF-2).
    assert cli("blueprint", "proj", "--summary=yes", expect=1)["code"] == "invalid"
    assert cli("blueprint", "proj", "--source-path", expect=1)["code"] == "invalid"
    # The plain rendering shows a summary row whole.
    assert main(["--home", str(home), "blueprint", "proj", "--summary", "--source-path", "tests/", "--text"]) == 0
    text = capsys.readouterr().out
    assert '- {"actual": 0, "declared": 0, "source_path": "tests/test_app.py", "tests": 3}' in text
    assert "total: 1" in text


def test_the_tool_describes_both_parameters() -> None:
    """R-IF-10, R-GROK-2: the description is all an MCP client reads."""
    tool = TOOLS_BY_NAME["grove_blueprint_get"]
    properties = tool.schema["properties"]
    assert list(properties) == ["project", "layer", "query", "limit", "offset", "summary", "source_path"]
    assert tool.schema["required"] == ["project"]
    # Each parameter says what it does, where a schema-only reader looks.
    summary = properties["summary"]
    assert summary["type"] == "boolean" and summary["default"] is False
    assert "per source file" in summary["description"] and "instead of items" in summary["description"]
    assert "Filters apply" in summary["description"]
    source_path = properties["source_path"]
    assert source_path["type"] == "string"
    assert "as items show it" in source_path["description"] and "'/'" in source_path["description"]
    # The description says when to use them, in the order of the walk.
    walk = tool.description.split("In a large blueprint", 1)
    assert len(walk) == 2 and 0 <= walk[1].find("summary") < walk[1].find("source_path")
    # What the description said before it made room is still said, here or on the parameter.
    assert "Case-insensitive substring of title, body or source path" in properties["query"]["description"]
    assert properties["layer"]["enum"] == ["declared", "actual", "tests"]
    for word in ("paginated", "declared", "actual", "tests", "does not rescan"):
        assert word in tool.description, word
