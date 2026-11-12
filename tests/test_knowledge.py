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
