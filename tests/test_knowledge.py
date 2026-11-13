"""Requirement 2: knowledge write, revision bump, FTS search."""

from __future__ import annotations

import pytest

from sf_grove.errors import GroveError
from sf_grove.service import Grove


def test_write_bumps_revision_and_keeps_history(tiny: Grove) -> None:
    first = tiny.knowledge_write("tiny", "release-process", "Release process", "Tag the commit, then build wheels.")
    second = tiny.knowledge_write("tiny", "release-process", "Release process", "Tag the commit, build wheels, publish.")
    assert (first["revision"], second["revision"]) == (1, 2)
    assert first["id"] != second["id"]

    latest = tiny.knowledge_get("release-process")
    assert latest["revision"] == 2 and latest["latest_revision"] == 2
    assert latest["body"].endswith("publish.")
    assert latest["project"] == "tiny"

    original = tiny.knowledge_get("release-process", revision=1)
    assert original["revision"] == 1
    assert original["body"] == "Tag the commit, then build wheels."

    with pytest.raises(GroveError) as missing:
        tiny.knowledge_get("release-process", revision=9)
    assert missing.value.code == "not_found"


def test_fts_search_finds_latest_revision_only(tiny: Grove) -> None:
    tiny.knowledge_write("tiny", "caching", "Caching notes", "The old design used memcached everywhere.")
    tiny.knowledge_write("tiny", "caching", "Caching notes", "The new design uses an in-process dictionary.")
    tiny.knowledge_write("tiny", "style", "Style guide", "Prefer short functions.")

    hits = tiny.knowledge_search("dictionary")
    assert hits["total"] == 1
    assert hits["items"][0]["key"] == "caching" and hits["items"][0]["revision"] == 2
    assert "[dictionary]" in hits["items"][0]["snippet"]
    assert "body" not in hits["items"][0]

    assert tiny.knowledge_search("memcached")["total"] == 0  # superseded revision
    assert tiny.knowledge_search("caching")["items"][0]["key"] == "caching"  # title match
    assert tiny.knowledge_search("function")["total"] == 1  # porter stemming: functions
    assert tiny.knowledge_search("dict*")["total"] == 1  # prefix
    assert tiny.knowledge_search("dictionary functions")["total"] == 0  # words are ANDed


def test_search_survives_fts_syntax_in_user_text(tiny: Grove) -> None:
    tiny.knowledge_write("tiny", "odd", "Odd characters", "Handles foo-bar and \"quoted\" text (AND OR NOT).")
    for query in ['foo-bar', '"quoted', "AND OR NOT", "text)", "col:umn", "foo AND"]:
        assert tiny.knowledge_search(query)["total"] >= 0
    assert tiny.knowledge_search("foo-bar")["total"] == 1
    with pytest.raises(GroveError) as empty:
        tiny.knowledge_search("  ---  ")
    assert empty.value.code == "invalid"


def test_search_is_paged(tiny: Grove) -> None:
    for index in range(5):
        tiny.knowledge_write("tiny", f"note-{index}", f"Note {index}", "Shared marker word: juniper.")
    page = tiny.knowledge_search("juniper", limit=2, offset=2)
    assert page["total"] == 5 and page["limit"] == 2 and page["offset"] == 2
    assert len(page["items"]) == 2


def test_workspace_level_notes_and_key_scopes(grove: Grove, tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    grove.project_create("alpha", str(tmp_path / "a"))
    grove.project_create("beta", str(tmp_path / "b"))

    workspace = grove.knowledge_write(None, "conventions", "Conventions", "Workspace-wide conventions.")
    assert workspace["project"] is None and workspace["revision"] == 1

    grove.knowledge_write("alpha", "map", "Alpha map", "alpha body")
    grove.knowledge_write("beta", "map", "Beta map", "beta body")
    assert grove.knowledge_get("map", project="alpha")["body"] == "alpha body"
    assert grove.knowledge_get("map", project="beta")["revision"] == 1  # scopes revise independently
    with pytest.raises(GroveError) as ambiguous:
        grove.knowledge_get("map")
    assert ambiguous.value.code == "invalid"

    grove.knowledge_write("alpha", "conventions", "Alpha conventions", "alpha only")
    assert grove.knowledge_get("conventions")["project"] is None  # workspace-level wins without a project
    assert grove.knowledge_search("conventions", project="alpha")["total"] == 1


def test_key_must_be_a_slug(tiny: Grove) -> None:
    with pytest.raises(GroveError) as bad:
        tiny.knowledge_write("tiny", "Not A Slug", "Title", "Body")
    assert bad.value.code == "invalid"
    with pytest.raises(GroveError) as unknown:
        tiny.knowledge_get("never-written")
    assert unknown.value.code == "not_found"


# -- excerpts ----------------------------------------------------------------

from sf_grove.service import EXCERPT_CHARS  # noqa: E402


def long_map() -> str:
    sections = [f"## Section {index}\n\n" + ("This module does a careful thing. " * 40) + "\n" for index in range(30)]
    return "# Big map\n\n```\n# not a heading\n```\n\n" + "\n".join(sections)


def test_knowledge_get_defaults_to_an_excerpt(tiny: Grove) -> None:
    body = long_map()
    assert len(body) > EXCERPT_CHARS * 5
    tiny.knowledge_write("tiny", "big-map", "Big map", body)

    excerpt = tiny.knowledge_get("big-map")
    assert excerpt["excerpted"] is True
    assert excerpt["body_chars"] == len(body)
    assert len(excerpt["body"]) == excerpt["excerpt_chars"] <= EXCERPT_CHARS
    assert body.startswith(excerpt["body"])
    assert "full=true" in excerpt["more"]
    assert excerpt["outline"][0] == {"level": 1, "title": "Big map", "line": 1}
    assert excerpt["outline_total"] == 31  # the fenced "# not a heading" is not counted
    assert [heading["title"] for heading in excerpt["outline"]][-1] == "Section 29"


def test_knowledge_get_full_returns_everything(tiny: Grove) -> None:
    body = long_map()
    tiny.knowledge_write("tiny", "big-map", "Big map", body)
    whole = tiny.knowledge_get("big-map", full=True)
    assert whole["excerpted"] is False and whole["body"] == body and whole["body_chars"] == len(body)
    assert "outline" not in whole and "more" not in whole
    with pytest.raises(GroveError) as bad:
        tiny.knowledge_get("big-map", full="yes")
    assert bad.value.code == "invalid"


def test_short_documents_are_never_excerpted(tiny: Grove) -> None:
    tiny.knowledge_write("tiny", "short", "Short", "Just a line.")
    short = tiny.knowledge_get("short")
    assert short["excerpted"] is False and short["body"] == "Just a line." and short["body_chars"] == 12


def test_mcp_tool_takes_the_full_flag(home) -> None:
    from sf_grove.tools import TOOLS_BY_NAME, call_tool

    assert TOOLS_BY_NAME["grove_knowledge_get"].schema["properties"]["full"]["default"] is False
    assert call_tool(home, "grove_knowledge_write", {"key": "big", "title": "Big", "body": long_map()})["ok"]
    excerpt = call_tool(home, "grove_knowledge_get", {"key": "big"})["data"]
    whole = call_tool(home, "grove_knowledge_get", {"key": "big", "full": True})["data"]
    assert excerpt["excerpted"] is True and whole["excerpted"] is False
    assert len(whole["body"]) == excerpt["body_chars"]


# -- authors -------------------------------------------------------------------


def test_knowledge_author_explicit_env_and_missing(tiny: Grove, monkeypatch: pytest.MonkeyPatch) -> None:
    assert tiny.knowledge_write("tiny", "note", "Note", "first")["author"] is None
    assert tiny.knowledge_write("tiny", "note", "Note", "second", author=" ana ")["author"] == "ana"
    monkeypatch.setenv("GROVE_AUTHOR", "build-bot")
    assert tiny.knowledge_write("tiny", "note", "Note", "third")["author"] == "build-bot"
    assert tiny.knowledge_write("tiny", "note", "Note", "fourth", author="ana")["author"] == "ana"  # argument wins

    assert [tiny.knowledge_get("note", revision=n)["author"] for n in (1, 2, 3, 4)] == [None, "ana", "build-bot", "ana"]
    assert tiny.knowledge_search("fourth")["items"][0]["author"] == "ana"

    for bad in ("x" * 65, "two\nlines"):
        with pytest.raises(GroveError) as raised:
            tiny.knowledge_write("tiny", "note", "Note", "body", author=bad)
        assert raised.value.code == "invalid"


def test_ingested_map_records_the_env_author(tiny: Grove, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import MAP_SAMPLE

    tiny.ingest_map("tiny", str(MAP_SAMPLE))
    monkeypatch.setenv("GROVE_AUTHOR", "mapper")
    tiny.ingest_map("tiny", str(MAP_SAMPLE))
    assert tiny.knowledge_get("map_sample", revision=1)["author"] is None
    assert tiny.knowledge_get("map_sample")["author"] == "mapper"


def test_ingest_map_takes_an_author_that_wins_over_the_environment(tiny: Grove, monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import MAP_SAMPLE

    tiny.ingest_map("tiny", str(MAP_SAMPLE), author="ana")
    monkeypatch.setenv("GROVE_AUTHOR", "mapper")
    tiny.ingest_map("tiny", str(MAP_SAMPLE), author="ana")
    tiny.ingest_map("tiny", str(MAP_SAMPLE), author="  ")  # blank is no name: the environment applies
    tiny.ingest_map("tiny", str(MAP_SAMPLE), None)
    assert [tiny.knowledge_get("map_sample", revision=n)["author"] for n in (1, 2, 3, 4)] == ["ana", "ana", "mapper", "mapper"]

    # A bad name is refused before the revision, the items or the findings are written.
    items = tiny.blueprint_get("tiny")["total"]
    for bad in ("x" * 65, "two\nlines", 7):
        with pytest.raises(GroveError) as raised:
            tiny.ingest_map("tiny", str(MAP_SAMPLE), author=bad)
        assert raised.value.code == "invalid"
    assert tiny.knowledge_get("map_sample")["revision"] == 4 and tiny.blueprint_get("tiny")["total"] == items


# -- listing without a query (R-KNOW-6) ------------------------------------------


def test_search_without_a_query_lists_latest_revisions_newest_first(grove: Grove, tmp_path) -> None:
    (tmp_path / "a").mkdir()
    grove.project_create("alpha", str(tmp_path / "a"))
    assert grove.knowledge_search()["items"] == []  # an empty home lists nothing, without error

    grove.knowledge_write("alpha", "first", "First", "one")
    grove.knowledge_write(None, "shared", "Shared", "workspace note", author="ana")
    grove.knowledge_write("alpha", "first", "First, revised", "one, but longer: caf\u00e9 \U0001f333")

    listing = grove.knowledge_search()
    assert (listing["query"], listing["total"]) == (None, 2)
    assert (listing["limit"], listing["offset"]) == (50, 0)
    # One row per document (its latest revision), newest write first.
    assert [(item["key"], item["revision"], item["project"]) for item in listing["items"]] == [
        ("first", 2, "alpha"),
        ("shared", 1, None),
    ]
    newest = listing["items"][0]
    assert set(newest) == {"id", "project", "project_id", "key", "title", "revision", "created_at", "author", "body_chars"}
    assert newest["title"] == "First, revised"
    # body_chars agrees with what knowledge_get reports, non-ASCII characters included.
    assert newest["body_chars"] == grove.knowledge_get("first", project="alpha")["body_chars"] == 23
    assert listing["items"][1]["author"] == "ana"


def test_listing_is_scoped_and_paged(grove: Grove, tmp_path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    grove.project_create("alpha", str(tmp_path / "a"))
    grove.project_create("beta", str(tmp_path / "b"))
    for index in range(5):
        grove.knowledge_write("alpha", f"note-{index}", f"Note {index}", "body")
    grove.knowledge_write("beta", "other", "Other", "body")
    grove.knowledge_write(None, "shared", "Shared", "body")

    assert grove.knowledge_search()["total"] == 7
    scoped = grove.knowledge_search(project="alpha")
    assert scoped["total"] == 5 and {item["project"] for item in scoped["items"]} == {"alpha"}  # no workspace notes
    page = grove.knowledge_search(project="alpha", limit=2, offset=1)
    assert [item["key"] for item in page["items"]] == ["note-3", "note-2"] and page["total"] == 5
    with pytest.raises(GroveError) as unknown:
        grove.knowledge_search(project="nope")
    assert unknown.value.code == "not_found"


def test_a_search_says_it_is_a_search_and_an_empty_query_is_still_an_error(tiny: Grove) -> None:
    tiny.knowledge_write("tiny", "note", "Note", "juniper berries")
    found = tiny.knowledge_search("juniper")
    assert found["query"] == "juniper" and "snippet" in found["items"][0]
    for bad in ("", "   ", "---"):
        with pytest.raises(GroveError) as raised:
            tiny.knowledge_search(bad)
        assert raised.value.code == "invalid"


def test_listing_through_the_mcp_tool_and_the_cli(home, capsys) -> None:
    import json

    from sf_grove.cli import main
    from sf_grove.tools import TOOLS_BY_NAME, call_tool

    tool = TOOLS_BY_NAME["grove_knowledge_search"]
    assert tool.schema["required"] == [] and "query" in tool.schema["properties"]
    assert "Omit query to list" in tool.description
    assert call_tool(home, "grove_knowledge_write", {"key": "one", "title": "One", "body": "first"})["ok"]

    listed = call_tool(home, "grove_knowledge_search", {})
    assert listed["ok"] and listed["data"]["query"] is None and listed["data"]["items"][0]["key"] == "one"
    assert "snippet" not in listed["data"]["items"][0] and "body" not in listed["data"]["items"][0]
    assert call_tool(home, "grove_knowledge_search", {"query": None})["data"]["query"] is None
    assert "snippet" in call_tool(home, "grove_knowledge_search", {"query": "first"})["data"]["items"][0]

    assert main(["--home", str(home), "search"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["query"] is None
    assert main(["--home", str(home), "search", "first", "--limit", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["query"] == "first"


# -- the same key in another scope (R-KNOW-8, result half) -----------------------


def test_knowledge_get_names_the_other_scopes_that_hold_the_key(grove: Grove, tmp_path) -> None:
    from sf_grove.service import OTHER_SCOPES_LISTED

    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
        grove.project_create(name, str(tmp_path / name))
    grove.knowledge_write(None, "conventions", "Conventions", "Workspace-wide conventions.")
    grove.knowledge_write("alpha", "only-here", "Only here", "one scope")

    # A key held by one scope says nothing: the fields are absent, not empty.
    alone = grove.knowledge_get("conventions")
    assert "other_scopes" not in alone and "other_scopes_total" not in alone
    assert "other_scopes" not in grove.knowledge_get("only-here")

    grove.knowledge_write("alpha", "conventions", "Alpha conventions", "alpha only")
    grove.knowledge_write("alpha", "conventions", "Alpha conventions", "alpha only, revised")

    # R-KNOW-3 still decides which document comes back; the result now says there is another.
    workspace = grove.knowledge_get("conventions")
    assert workspace["project"] is None and workspace["body"] == "Workspace-wide conventions."
    assert workspace["other_scopes"] == [{"project": "alpha"}]  # one entry per scope, not per revision
    assert workspace["other_scopes_total"] == 1

    # A named entry is what the caller passes as project to read that document.
    named = grove.knowledge_get("conventions", project=workspace["other_scopes"][0]["project"])
    assert named["project"] == "alpha" and named["revision"] == 2
    assert named["other_scopes"] == [{"project": None}]  # null is the workspace, as in the document's own field
    assert grove.knowledge_get("conventions", project="alpha", revision=1)["other_scopes"] == [{"project": None}]

    # The workspace first, then projects by name; the returned scope is never listed.
    grove.knowledge_write("beta", "conventions", "Beta conventions", "beta only")
    assert grove.knowledge_get("conventions")["other_scopes"] == [{"project": "alpha"}, {"project": "beta"}]
    from_beta = grove.knowledge_get("conventions", project="beta")
    assert from_beta["other_scopes"] == [{"project": None}, {"project": "alpha"}]
    assert from_beta["other_scopes_total"] == 2

    # The list is capped and the cap is reported (section 8): the total is the true count.
    for index in range(OTHER_SCOPES_LISTED + 1):
        name = f"p{index:02d}"
        (tmp_path / name).mkdir()
        grove.project_create(name, str(tmp_path / name))
        grove.knowledge_write(name, "conventions", "Conventions", "one more scope")
    capped = grove.knowledge_get("conventions", project="alpha")
    assert capped["other_scopes_total"] == OTHER_SCOPES_LISTED + 3  # the workspace, beta and the new projects
    assert len(capped["other_scopes"]) == OTHER_SCOPES_LISTED == 20
    assert capped["other_scopes"][:3] == [{"project": None}, {"project": "beta"}, {"project": "p00"}]


def test_other_scopes_come_with_an_excerpt_and_with_the_whole_body(grove: Grove, tmp_path) -> None:
    (tmp_path / "a").mkdir()
    grove.project_create("alpha", str(tmp_path / "a"))
    grove.knowledge_write(None, "big-map", "Big map", long_map())
    grove.knowledge_write("alpha", "big-map", "Alpha map", "short")
    excerpt = grove.knowledge_get("big-map")
    assert excerpt["excerpted"] is True and excerpt["other_scopes"] == [{"project": "alpha"}]
    assert grove.knowledge_get("big-map", full=True)["other_scopes"] == [{"project": "alpha"}]


def test_other_scopes_through_the_mcp_tool_and_the_cli(home, tmp_path, capsys) -> None:
    import json

    from sf_grove.cli import main
    from sf_grove.tools import call_tool

    (tmp_path / "a").mkdir()
    assert call_tool(home, "grove_project_create", {"name": "alpha", "root_path": str(tmp_path / "a")})["ok"]
    for project, body in ((None, "workspace body"), ("alpha", "alpha body")):
        arguments = {"key": "conventions", "title": "Conventions", "body": body}
        assert call_tool(home, "grove_knowledge_write", arguments | ({"project": project} if project else {}))["ok"]
    assert call_tool(home, "grove_knowledge_write", {"key": "alone", "title": "Alone", "body": "one scope"})["ok"]

    # MCP: one key in the workspace and in a project.
    workspace = call_tool(home, "grove_knowledge_get", {"key": "conventions"})["data"]
    assert workspace["project"] is None and workspace["body"] == "workspace body"
    assert (workspace["other_scopes"], workspace["other_scopes_total"]) == ([{"project": "alpha"}], 1)
    named = call_tool(home, "grove_knowledge_get", {"key": "conventions", "project": "alpha"})["data"]
    assert named["body"] == "alpha body" and named["other_scopes"] == [{"project": None}]
    assert "other_scopes" not in call_tool(home, "grove_knowledge_get", {"key": "alone"})["data"]

    # CLI: the same data directory, the same answers.
    assert main(["--home", str(home), "knowledge", "get", "conventions"]) == 0
    printed = json.loads(capsys.readouterr().out)["data"]
    assert printed["project"] is None and printed["other_scopes"] == [{"project": "alpha"}]
    assert printed["other_scopes_total"] == 1
    assert main(["--home", str(home), "knowledge", "get", "conventions", "--project", "alpha"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["other_scopes"] == [{"project": None}]
    assert main(["--home", str(home), "knowledge", "get", "alone"]) == 0
    assert "other_scopes" not in json.loads(capsys.readouterr().out)["data"]
