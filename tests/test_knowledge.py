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


# -- an excerpt from a line (R-KNOW-8, start-line half) --------------------------


def read_on(grove: Grove, key: str, first: dict) -> list[dict]:
    """Every excerpt from ``first`` to the end of the document, following ``next_line``."""
    pieces = [first]
    while "next_line" in pieces[-1]:
        pieces.append(grove.knowledge_get(key, from_line=pieces[-1]["next_line"]))
        assert len(pieces) < 500, "next_line does not reach the end"
    return pieces


def test_from_line_starts_the_excerpt_at_a_line_of_the_outline(tiny: Grove) -> None:
    body = long_map()
    tiny.knowledge_write("tiny", "big-map", "Big map", body)
    first = tiny.knowledge_get("big-map")
    section = next(heading for heading in first["outline"] if heading["title"] == "Section 20")
    assert not first["body"].count("Section 20")  # the default excerpt does not reach it

    excerpt = tiny.knowledge_get("big-map", from_line=section["line"])
    assert excerpt["body"].startswith("## Section 20\n")
    assert excerpt["excerpted"] is True and excerpt["body_chars"] == len(body)
    assert len(excerpt["body"]) == excerpt["excerpt_chars"] <= EXCERPT_CHARS  # the same size limit, no second one
    assert excerpt["body"] in body
    # The caller took the line from an outline, so no outline comes back.
    assert "outline" not in excerpt and "outline_total" not in excerpt
    assert f"from line {section['line']}" in excerpt["more"] and "full=true" in excerpt["more"]

    # Every line the outline names is the line the excerpt then starts at.
    for heading in first["outline"]:
        start = tiny.knowledge_get("big-map", from_line=heading["line"])["body"]
        assert start.splitlines()[0] == "#" * heading["level"] + " " + heading["title"]

    # from_line=1 is the first excerpt, without the outline.
    again = tiny.knowledge_get("big-map", from_line=1)
    assert again["body"] == first["body"] and again["next_line"] == first["next_line"] and "outline" not in again


def test_an_excerpt_names_the_line_to_read_on_from(tiny: Grove) -> None:
    body = long_map()
    tiny.knowledge_write("tiny", "big-map", "Big map", body)
    first = tiny.knowledge_get("big-map")
    # The default excerpt says it too: the line that starts where the excerpt was cut.
    before = "".join(body.splitlines(keepends=True)[: first["next_line"] - 1])
    assert before == first["body"] + "\n"
    assert f"from_line={first['next_line']}" in first["more"] and "--from-line" in first["more"]

    pieces = read_on(tiny, "big-map", first)
    assert len(pieces) > 5 and all(piece["excerpted"] for piece in pieces)
    lines = [piece["next_line"] for piece in pieces[:-1]]
    assert lines == sorted(set(lines)), "each call reads on from a later line"
    # Every cut fell on a line break, so the excerpts are the document, and nothing is read twice.
    assert "\n".join(piece["body"] for piece in pieces) == body
    last = pieces[-1]
    assert "next_line" not in last and "to the end" in last["more"] and "from_line=" not in last["more"]


def test_from_line_past_the_end_and_other_bad_lines_are_invalid(tiny: Grove) -> None:
    body = long_map()
    count = len(body.splitlines())
    tiny.knowledge_write("tiny", "big-map", "Big map", body)

    last = tiny.knowledge_get("big-map", from_line=count)  # the last line is a line
    assert last["body"] == body.splitlines(keepends=True)[-1] and "next_line" not in last
    with pytest.raises(GroveError) as past:
        tiny.knowledge_get("big-map", from_line=count + 1)
    assert past.value.code == "invalid"
    assert past.value.message == f"from_line {count + 1} is past the end: the document has {count} lines"

    for bad in (0, -3, True, 1.5, "ten", [4]):
        with pytest.raises(GroveError) as raised:
            tiny.knowledge_get("big-map", from_line=bad)
        assert raised.value.code == "invalid" and "from_line" in raised.value.message, bad
    # A bad line is refused before the key is looked up, like a bad full.
    with pytest.raises(GroveError) as early:
        tiny.knowledge_get("no-such-key", from_line=0)
    assert early.value.code == "invalid"

    # full returns the whole body, so the two together are refused, not guessed at.
    with pytest.raises(GroveError) as both:
        tiny.knowledge_get("big-map", full=True, from_line=3)
    assert both.value.code == "invalid" and "full" in both.value.message and "from_line" in both.value.message
    assert tiny.knowledge_get("big-map", full=True, from_line=None)["body"] == body


def test_from_line_on_a_document_that_is_not_excerpted(tiny: Grove) -> None:
    body = "# Short\n\nfirst\nsecond\n\n## Tail\n\nlast\n"
    tiny.knowledge_write("tiny", "short", "Short", body)
    whole = tiny.knowledge_get("short")
    assert whole["excerpted"] is False and "next_line" not in whole and "more" not in whole

    # From its first line a short document is whole, and says so as before.
    assert tiny.knowledge_get("short", from_line=1) == whole

    # From a later line the body starts there: it is no longer the whole document, and the result says so.
    tail = tiny.knowledge_get("short", from_line=6)
    assert tail["body"] == "## Tail\n\nlast\n"
    assert tail["excerpted"] is True and (tail["excerpt_chars"], tail["body_chars"]) == (14, len(body))
    assert tail["more"] == (
        f"body is 14 of {len(body)} characters, from line 6 to the end; "
        "call again with full=true (CLI: --full) for the whole document"
    )
    assert "next_line" not in tail and "outline" not in tail

    assert tiny.knowledge_get("short", from_line=8)["body"] == "last\n"
    with pytest.raises(GroveError) as past:
        tiny.knowledge_get("short", from_line=9)
    assert past.value.code == "invalid" and "has 8 lines" in past.value.message


def test_from_line_counts_lines_as_the_outline_does(tiny: Grove) -> None:
    # Windows line ends, a form feed and a line separator: str.splitlines ends a line at each.
    paragraph = "A sentence about the workshop. " * 30
    parts = []
    for index in range(12):
        parts += [f"## Part {index}", "", paragraph, "page\x0cbreak", "line\u2028separator", ""]
    body = "\r\n".join(["# Mixed", ""] + parts)
    tiny.knowledge_write("tiny", "mixed", "Mixed", body)
    first = tiny.knowledge_get("mixed")
    assert first["outline_total"] == 13
    for heading in first["outline"]:
        start = tiny.knowledge_get("mixed", from_line=heading["line"])["body"]
        assert start.splitlines()[0] == "#" * heading["level"] + " " + heading["title"]
    pieces = read_on(tiny, "mixed", first)
    assert "\n".join(piece["body"] for piece in pieces) == body  # a cut takes the \n of a \r\n and nothing else


def test_a_line_longer_than_an_excerpt_is_cut_and_said_so(tiny: Grove) -> None:
    long_line = "x" * (EXCERPT_CHARS * 2 + 500)
    body = f"intro\n{long_line}\nend\n"
    tiny.knowledge_write("tiny", "wide", "Wide", body)

    # The first excerpt runs into the long line; reading on starts that line again, whole lines first.
    first = tiny.knowledge_get("wide")
    assert len(first["body"]) == EXCERPT_CHARS and first["next_line"] == 2 and "is cut" not in first["more"]

    # From the long line itself only its first 4000 characters fit. Reading on from the same
    # line would return them again, so the next line is the one after, and the result says
    # which line was cut: its rest is passed over, and only full returns it.
    cut = tiny.knowledge_get("wide", from_line=2)
    assert cut["body"] == "x" * EXCERPT_CHARS and cut["next_line"] == 3
    assert "line 2 is longer than an excerpt and is cut" in cut["more"]
    assert "from_line=3" in cut["more"] and "full=true" in cut["more"]
    assert tiny.knowledge_get("wide", from_line=3)["body"] == "end\n"
    assert long_line in tiny.knowledge_get("wide", full=True)["body"]

    # An excerpt that lacks only the last line end names no line either: there is none.
    tiny.knowledge_write("tiny", "brim", "Brim", "y" * EXCERPT_CHARS + "\n")
    brim = tiny.knowledge_get("brim")
    assert brim["body"] == "y" * EXCERPT_CHARS and brim["excerpted"] is True
    assert "next_line" not in brim and "is cut" not in brim["more"]

    tiny.knowledge_write("tiny", "brim-crlf", "Brim", "y" * EXCERPT_CHARS + "\r\n")
    assert "next_line" not in tiny.knowledge_get("brim-crlf")

    # A document that is one long line has no line to read on from.
    tiny.knowledge_write("tiny", "one-line", "One line", long_line)
    only = tiny.knowledge_get("one-line")
    assert only["body"] == "x" * EXCERPT_CHARS
    assert only["excerpted"] is True and "next_line" not in only
    assert only["more"] == (
        f"body is the first {EXCERPT_CHARS} of {len(long_line)} characters; line 1 is longer than an "
        "excerpt and is cut; call again with full=true (CLI: --full) for the whole document"
    )


def test_reading_on_reaches_the_end_of_any_document(tiny: Grove) -> None:
    """Seeded documents of odd shapes: next_line always moves on, and whole lines are never lost."""
    import random
    import re

    rng = random.Random(19)
    seen_long = False
    ends = ["\n", "\n", "\n", "\r\n", "\n\n", "\r", "\x0c", "\u2028"]
    for number in range(40):
        widths = [rng.choice([0, 3, 40, 300, 1500, 1999]) for _ in range(rng.randint(1, 120))]
        if number % 4 == 0:  # some documents hold lines longer than half an excerpt, or than a whole one
            widths += [rng.choice([2500, 3999, 4000, 4001, 9000]) for _ in range(3)]
            rng.shuffle(widths)
        if number % 5 == 0:  # and some end in a line that fills an excerpt to the brim
            widths.append(rng.choice([3999, 4000, 4001]))
        body = "".join("w" * width + rng.choice(ends) for width in widths) + rng.choice(["", "tail"])
        if not body.strip():
            body = "tail"
        key = f"doc-{number}"
        tiny.knowledge_write("tiny", key, "Doc", body)
        lines = body.splitlines()
        pieces = read_on(tiny, key, tiny.knowledge_get(key))
        starts = [1] + [piece["next_line"] for piece in pieces[:-1]]
        assert starts == sorted(set(starts)) and starts[-1] <= len(lines), key
        whole = set()
        for start, piece in zip(starts, pieces):
            assert len(piece["body"]) <= EXCERPT_CHARS, key
            held = piece["body"].splitlines()
            assert all(lines[start - 1 + index].startswith(text) for index, text in enumerate(held)), key
            whole |= {start + index for index, text in enumerate(held) if text == lines[start - 1 + index]}
        # A line is missed only when it is longer than an excerpt, and then a result named it;
        # or when it is empty and the cut took its line end.
        named = {int(line) for piece in pieces for line in re.findall(r"line (\d+) is longer", piece.get("more", ""))}
        missed = set(range(1, len(lines) + 1)) - whole
        assert named <= missed and all(len(lines[line - 1]) > EXCERPT_CHARS for line in named), key
        assert all(lines[line - 1] == "" for line in missed - named), key
        seen_long = seen_long or bool(named)
    assert seen_long, "no document held a line longer than an excerpt"


def test_from_line_reads_the_revision_and_scope_that_were_asked_for(grove: Grove, tmp_path) -> None:
    (tmp_path / "a").mkdir()
    grove.project_create("alpha", str(tmp_path / "a"))
    grove.knowledge_write("alpha", "notes", "Notes", "one\ntwo\nthree\n")
    grove.knowledge_write("alpha", "notes", "Notes", "one\ntwo\n")
    grove.knowledge_write(None, "notes", "Notes", "workspace\nlines\n")
    assert grove.knowledge_get("notes", project="alpha", revision=1, from_line=3)["body"] == "three\n"
    with pytest.raises(GroveError) as past:  # the latest revision is shorter
        grove.knowledge_get("notes", project="alpha", from_line=3)
    assert past.value.code == "invalid" and "has 2 lines" in past.value.message
    workspace = grove.knowledge_get("notes", from_line=2)
    assert workspace["body"] == "lines\n" and workspace["other_scopes"] == [{"project": "alpha"}]


def test_from_line_through_the_mcp_tool_and_the_cli(home, capsys) -> None:
    import json

    from sf_grove.cli import main
    from sf_grove.tools import TOOLS_BY_NAME, call_tool

    tool = TOOLS_BY_NAME["grove_knowledge_get"]
    assert tool.schema["properties"]["from_line"]["type"] == "integer"
    assert tool.schema["properties"]["from_line"]["minimum"] == 1 and tool.schema["required"] == ["key"]
    # The description says what the parameter is, and where its values come from (R-IF-10).
    described = tool.schema["properties"]["from_line"]["description"]
    assert "outline" in described and "next_line" in described and "next_line" in tool.description
    # What was tightened to pay for it is still said, once each.
    for fact in ("by key", "unique per project", "workspace-level document wins", "4000 characters", "outline"):
        assert fact in tool.description, fact
    assert "latest if omitted" in tool.schema["properties"]["revision"]["description"]
    assert "whole body" in tool.schema["properties"]["full"]["description"]

    body = long_map()
    assert call_tool(home, "grove_knowledge_write", {"key": "big", "title": "Big", "body": body})["ok"]
    first = call_tool(home, "grove_knowledge_get", {"key": "big"})["data"]
    line = next(heading["line"] for heading in first["outline"] if heading["title"] == "Section 7")

    # MCP.
    excerpt = call_tool(home, "grove_knowledge_get", {"key": "big", "from_line": line})["data"]
    assert excerpt["body"].startswith("## Section 7\n") and excerpt["excerpted"] is True and "outline" not in excerpt
    assert call_tool(home, "grove_knowledge_get", {"key": "big", "from_line": None})["data"] == first
    read_on_from = call_tool(home, "grove_knowledge_get", {"key": "big", "from_line": first["next_line"]})["data"]
    assert body.startswith(first["body"] + "\n" + read_on_from["body"])
    past = call_tool(home, "grove_knowledge_get", {"key": "big", "from_line": 10_000})
    assert past["ok"] is False and past["error"]["code"] == "invalid" and "past the end" in past["error"]["message"]
    both = call_tool(home, "grove_knowledge_get", {"key": "big", "from_line": line, "full": True})
    assert both["ok"] is False and both["error"]["code"] == "invalid"
    assert call_tool(home, "grove_knowledge_get", {"key": "big", "from_line": 0})["error"]["code"] == "invalid"

    # CLI: the same data directory, the same answers.
    assert main(["--home", str(home), "knowledge", "get", "big", "--from-line", str(line)]) == 0
    assert json.loads(capsys.readouterr().out)["data"] == excerpt
    assert main(["--home", str(home), "knowledge", "get", "big"]) == 0
    assert json.loads(capsys.readouterr().out)["data"] == first
    assert main(["--home", str(home), "knowledge", "get", "big", "--from-line", "10000"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == past["error"]
    assert main(["--home", str(home), "knowledge", "get", "big", "--from-line", str(line), "--full"]) == 1
    assert json.loads(capsys.readouterr().out)["error"] == both["error"]
