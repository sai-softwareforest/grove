"""Prism's library of lessons, without storage (WO-41).

A lesson is one entry of a curated list: a title, a link, one line of text,
and tags that say which projects it could matter to. This module reads the
three reviewed data files that ship beside it, reads list files a user has
copied to this machine, and works out what a refresh has to record. It opens
no connection of any kind: a refresh never fetches (R-INV-1), it reads a
directory. The database side is ``service.Grove.prism_refresh``.

Everything read from a list is someone else's text (R-SEC-1, R-SEC-4). It is
never interpreted: control and format characters are removed, length is
capped, and only ``https://`` links are kept. Every cap is counted and
reported by the refresh (REQUIREMENTS.md, section 8).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .scan import MAX_LINE_CHARS
from .scan import _FENCE  # an entry inside a code fence is an example, not an entry

KEY_CHARS = 12
MAX_TITLE_CHARS = 200
MAX_SUMMARY_CHARS = 500
MAX_URL_CHARS = 500
MAX_LIST_BYTES = 2 * 1024 * 1024  # one list file; a larger one is not read at all
MAX_LIST_ENTRIES = 5000  # entries kept from one list; a list cut here retires nothing
EVENTS = ("added", "retired", "revived", "changed")
ORIGINS = ("seed", "refresh")
TAG_KINDS = ("language", "dependency", "capability")
SEED_REF = "seed"  # the source_ref of the events the seed writes

PACK_CAP = 50  # lessons in one review pack
VERDICTS = ("adopt", "edit", "delete", "not-relevant")
VERDICT_KEY_PREFIX = "prism."  # a verdict is the knowledge document prism.KEY of the project
STATES = ("open", "reopened", "settled")  # the order of a pack
PART_HASH_CHARS = 16

SEED_FILE = "prism_seed.json"
TAGS_FILE = "prism_tags.json"
SOURCES_FILE = "prism_sources.json"

# One list entry: "- [title](url) - text". The title holds no bracket and the
# link no space or parenthesis, so each part is read once, left to right, and
# the pattern stays linear on any line (R-SCAN-7). Lines over MAX_LINE_CHARS
# never reach it.
_ENTRY = re.compile(r"^\s{0,24}[-*+]\s+\[([^\[\]]+)\]\(\s*([^()\s]+)\s*\)(.*)$")
_SEPARATOR = re.compile(r"^\s*[-–—:]+\s*")
_HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?(?::[0-9]{1,5})?$")
_URL_UNSAFE = re.compile(r"[\s<>\"'`\\^{}|]")
_DEPENDENCY = re.compile(r"^[a-z0-9@][a-z0-9._/@-]{0,99}$")
_LIST_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_LINE_SUFFIX = re.compile(r":[0-9]+$")
_VERDICT_LINE = re.compile(r"^(verdict|reason|work)[ \t]*:[ \t]*(.*)$")
_SCHEME = "https://"
# Unicode categories that are removed from a lesson's text: controls, format
# characters (the bidirectional controls, zero-width characters, the byte
# order mark), surrogates and private use. Line and paragraph separators
# become a space with the rest of the white space.
_REMOVED_CATEGORIES = ("Cc", "Cf", "Cs", "Co")


class PrismDataError(ValueError):
    """A reviewed data file, or a list of this machine, is not what a refresh can read."""


@dataclass(frozen=True)
class Entry:
    """One lesson as a list (or the seed) states it."""

    key: str
    title: str
    summary: str
    source_url: str
    source_list: str  # "NAME:LINE"
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Source:
    """One list a refresh reads: its name, where its file lies inside the directory, and its tags."""

    name: str
    path: str
    tags: tuple[str, ...]
    repo: str | None = None


@dataclass
class ParsedList:
    entries: list[Entry] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    clipped: dict[str, int] = field(default_factory=dict)
    complete: bool = True


@dataclass(frozen=True)
class Current:
    """A stored lesson as it stands: the text of its latest event that carries text, and its state."""

    key: str
    origin: str
    title: str
    summary: str
    source_list: str
    tags: tuple[str, ...]
    retired: bool
    source_url: str = ""


@dataclass(frozen=True)
class Action:
    """One row a refresh has to append. ``entry`` is None when the event carries no text."""

    event: str
    key: str
    entry: Entry | None
    new_lesson: bool = False
    list_name: str = ""


# -- text, links, keys -------------------------------------------------------


def clean_text(text: str, limit: int) -> tuple[str, bool]:
    """One line of plain text of at most ``limit`` characters, and whether it was cut.

    Control and format characters are removed (R-SEC-1: a bidirectional
    control or a zero-width character can hide what a line says), white space
    is collapsed, and a text that is still too long ends in "…".
    """
    kept = []
    for char in text:
        if char in "\t\n\r\x0b\x0c\x1c\x1d\x1e\x1f\x85  ":
            kept.append(" ")
        elif unicodedata.category(char) not in _REMOVED_CATEGORIES:
            kept.append(char)
    cleaned = " ".join("".join(kept).split())
    if len(cleaned) <= limit:
        return cleaned, False
    return cleaned[: limit - 1].rstrip() + "…", True


def _split_url(url: str) -> tuple[str, str] | None:
    """(host in lower case, the rest as written) of an ``https://`` link, or None when it is not a usable one."""
    url = url.strip()
    if len(url) > MAX_URL_CHARS or url[: len(_SCHEME)].lower() != _SCHEME:
        return None
    if _URL_UNSAFE.search(url) or any(unicodedata.category(char) in _REMOVED_CATEGORIES for char in url):
        return None
    rest = url[len(_SCHEME) :]
    cut = min((rest.find(mark) for mark in "/?#" if mark in rest), default=len(rest))
    host, tail = rest[:cut].lower(), rest[cut:]
    return (host, tail) if _HOST.match(host) else None


def normalise_url(url: str) -> str | None:
    """The form of an ``https://`` link that a lesson is keyed by, or None when it is not one.

    Scheme and host are lower-cased, and a path that is only ``/``, or ends
    in one, loses it; nothing else is touched, so two entries are the same
    lesson exactly when they link the same address. A link with a user name,
    a character that does not belong in a link, or more than MAX_URL_CHARS
    characters is refused. Written without ``urllib``: Grove imports no
    network module (R-INV-1).
    """
    parts = _split_url(url)
    if parts is None:
        return None
    host, tail = parts
    if "?" not in tail and "#" not in tail:
        tail = tail.rstrip("/")
    return _SCHEME + host + tail


def lesson_key(normalised_url: str) -> str:
    """The stable key of a lesson: 12 hex digits of a SHA-256 over its normalised link.

    The key takes the link and nothing else, so an entry that moves to
    another line or another list, or whose text is edited, keeps it.
    """
    return hashlib.sha256(normalised_url.encode("utf-8", errors="replace")).hexdigest()[:KEY_CHARS]


def list_name(source_list: str) -> str:
    """``awesome-python`` for ``awesome-python:156``: the list without the line."""
    return _LINE_SUFFIX.sub("", source_list)


# -- the reviewed data files -------------------------------------------------


def _data(name: str) -> Any:
    path = Path(__file__).with_name(name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PrismDataError(f"cannot read Grove's own {name}: {exc}") from exc


def load_tag_map() -> dict[str, Any]:
    """The tag vocabulary: languages (with their file extensions) and capabilities (with what shows them)."""
    data = _data(TAGS_FILE)
    languages, capabilities = data.get("languages"), data.get("capabilities")
    if not isinstance(languages, dict) or not isinstance(capabilities, dict) or not languages or not capabilities:
        raise PrismDataError(f"{TAGS_FILE} must hold 'languages' and 'capabilities'")
    return {"languages": languages, "capabilities": capabilities}


def check_tags(tags: Any, tag_map: dict[str, Any], where: str) -> tuple[str, ...]:
    """Tags as a sorted tuple without repeats; PrismDataError when one is not in the vocabulary.

    A tag is ``language:NAME`` or ``capability:NAME`` with a name the tag map
    knows, or ``dependency:NAME`` with a package name written in lower case.
    """
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise PrismDataError(f"{where}: tags must be a list of strings")
    for tag in tags:
        kind, _, name = tag.partition(":")
        known = (
            (kind == "language" and name in tag_map["languages"])
            or (kind == "capability" and name in tag_map["capabilities"])
            or (kind == "dependency" and bool(_DEPENDENCY.match(name)))
        )
        if not known:
            raise PrismDataError(f"{where}: tag {tag!r} is not in {TAGS_FILE}")
    return tuple(sorted(set(tags)))


def load_sources(tag_map: dict[str, Any] | None = None) -> list[Source]:
    """The lists a refresh reads, in the order of the file. Nothing else under the directory is opened."""
    tag_map = tag_map or load_tag_map()
    lists = _data(SOURCES_FILE).get("lists")
    if not isinstance(lists, list) or not lists:
        raise PrismDataError(f"{SOURCES_FILE} must hold a non-empty 'lists'")
    sources: list[Source] = []
    for row in lists:
        name, path = (row.get("list"), row.get("path")) if isinstance(row, dict) else (None, None)
        if not isinstance(name, str) or not _LIST_NAME.match(name):
            raise PrismDataError(f"{SOURCES_FILE}: {name!r} is not a list name")
        parts = path.split("/") if isinstance(path, str) else []
        if not parts or any(part in ("", ".", "..") or "\\" in part for part in parts):
            raise PrismDataError(f"{SOURCES_FILE}: the path of {name} must be relative, with / and without ..")
        if any(source.name == name for source in sources):
            raise PrismDataError(f"{SOURCES_FILE}: {name} is listed twice")
        repo = row.get("repo") if isinstance(row.get("repo"), str) else None
        sources.append(Source(name, path, check_tags(row.get("tags"), tag_map, f"{SOURCES_FILE}: {name}"), repo))
    return sources


def make_entry(title: Any, url: Any, text: Any, source_list: str, tags: tuple[str, ...]) -> tuple[Entry | None, str, dict[str, int]]:
    """An entry from raw parts: (entry, why it was skipped, what was cut). One path for the seed and for lists."""
    if not isinstance(title, str) or not isinstance(url, str) or not isinstance(text, str):
        return None, "no_title", {}
    clean_url = url.strip()
    if clean_url[: len(_SCHEME)].lower() != _SCHEME:
        return None, "not_https", {}
    normalised = normalise_url(clean_url)
    if normalised is None:
        return None, "bad_url", {}
    clean_title, title_cut = clean_text(title, MAX_TITLE_CHARS)
    if not clean_title:
        return None, "no_title", {}
    summary, summary_cut = clean_text(text, MAX_SUMMARY_CHARS)
    clipped = {name: 1 for name, cut in (("titles", title_cut), ("summaries", summary_cut)) if cut}
    host, tail = _split_url(clean_url) or ("", "")
    # Stored as written, but for the scheme and the host, which are case-insensitive and stored in lower case.
    return Entry(lesson_key(normalised), clean_title, summary, _SCHEME + host + tail, source_list, tags), "", clipped


def load_seed(tag_map: dict[str, Any] | None = None) -> list[Entry]:
    """The lessons a new library starts with, in the order of the file.

    The seed is reviewed text, and it is still held to the rules of a list:
    an entry a refresh would skip or cut is an error here, not a silent
    difference between the file and the library.
    """
    tag_map = tag_map or load_tag_map()
    rows = _data(SEED_FILE).get("lessons")
    if not isinstance(rows, list) or not rows:
        raise PrismDataError(f"{SEED_FILE} must hold a non-empty 'lessons'")
    entries: dict[str, Entry] = {}
    for index, row in enumerate(rows):
        where = f"{SEED_FILE}: lesson {index + 1}"
        if not isinstance(row, dict):
            raise PrismDataError(f"{where} is not an object")
        source_list = row.get("source_list")
        if not isinstance(source_list, str) or not _LIST_NAME.match(list_name(source_list)) or source_list == list_name(source_list):
            raise PrismDataError(f"{where}: source_list must be LIST:LINE")
        tags = check_tags(row.get("tags"), tag_map, where)
        entry, skipped, clipped = make_entry(row.get("title"), row.get("source_url"), row.get("summary"), source_list, tags)
        if entry is None or clipped:
            raise PrismDataError(f"{where}: {skipped or 'the text is longer than a lesson may be'}")
        if (entry.title, entry.summary, entry.source_url) != (row["title"], row["summary"], row["source_url"]):
            raise PrismDataError(f"{where}: the text is not clean (control characters or stray white space)")
        if entry.key in entries:
            raise PrismDataError(f"{where}: the same link as an earlier lesson")
        entries[entry.key] = entry
    return list(entries.values())


# -- reading a list ----------------------------------------------------------


def _count(counts: dict[str, int], name: str, by: int = 1) -> None:
    counts[name] = counts.get(name, 0) + by


def parse_list(text: str, name: str, tags: tuple[str, ...]) -> ParsedList:
    """The entries of one list: every line of the form ``- [title](url) - text``, outside code fences.

    Only the entry's own line is read; nothing is rendered or followed. What
    is not kept is counted under ``skipped``: ``not_https`` (any other kind
    of link, an anchor of the table of contents included), ``bad_url``,
    ``no_title``, ``duplicate`` (a link the list already gave) and
    ``long_lines``. After MAX_LIST_ENTRIES entries the rest of the list is
    not read and ``complete`` is false.
    """
    parsed = ParsedList()
    seen: set[str] = set()
    in_fence = False
    if text.startswith("﻿"):
        text = text[1:]
    for number, line in enumerate(text.split("\n"), start=1):
        if len(line) > MAX_LINE_CHARS:
            _count(parsed.skipped, "long_lines")
            continue
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _ENTRY.match(line)
        if not match:
            continue
        if len(parsed.entries) >= MAX_LIST_ENTRIES:
            parsed.complete = False
            break
        rest = _SEPARATOR.sub("", match.group(3), count=1)
        entry, skipped, clipped = make_entry(match.group(1), match.group(2), rest, f"{name}:{number}", tags)
        if entry is None:
            _count(parsed.skipped, skipped)
        elif entry.key in seen:
            _count(parsed.skipped, "duplicate")
        else:
            seen.add(entry.key)
            parsed.entries.append(entry)
            for part in clipped:
                _count(parsed.clipped, part)
    return parsed


def find_list_file(root: Path, relative: str) -> tuple[Path | None, str]:
    """The file of one list inside ``root``: (path, status).

    ``root`` is already resolved. The path is followed as written; when the
    file is not there, its directory is looked through for the same name in
    another case (``readme.md`` for ``README.md``), in sorted order. The
    file must resolve to a place inside ``root``: a symbolic link that
    leaves the directory is ``outside`` and is not read. Status is one of
    ``read`` (found, not yet read), ``missing``, ``outside``, ``unreadable``.
    """
    parts = relative.split("/")
    try:
        directory = root.joinpath(*parts[:-1])
        candidate = directory / parts[-1]
        if not candidate.is_file():
            if not directory.is_dir():
                return None, "missing"
            same = sorted(name for name in os.listdir(directory) if name.lower() == parts[-1].lower())
            candidates = [directory / name for name in same if (directory / name).is_file()]
            if not candidates:
                return None, "missing"
            candidate = candidates[0]
        resolved = candidate.resolve()
    except OSError:
        return None, "unreadable"
    if not resolved.is_relative_to(root):
        return None, "outside"
    return resolved, "read"


def read_list_file(path: Path) -> tuple[str | None, str]:
    """The text of a list file, or (None, ``too_large`` or ``unreadable``). At most one byte past the cap is held."""
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_LIST_BYTES + 1)
    except OSError:
        return None, "unreadable"
    if len(data) > MAX_LIST_BYTES:
        return None, "too_large"
    return data.decode("utf-8", errors="replace"), "read"


def checkout_above(path: Path, root: Path) -> Path | None:
    """The nearest directory at or above ``path``, and not above ``root``, that is a git checkout.

    Only a real ``.git`` directory counts. A link, or the pointer file of a
    linked worktree, would lead the reader of the commit out of ``root``.
    """
    for directory in (path, *path.parents):
        if not directory.is_relative_to(root):
            return None
        git = directory / ".git"
        if git.is_dir() and not git.is_symlink():
            return directory
    return None


# -- what a refresh records --------------------------------------------------


def plan_refresh(current: dict[str, Current], seen: dict[str, Entry], complete_lists: set[str]) -> tuple[list[Action], int]:
    """The events a refresh appends, in key order, and how many lessons need none.

    ``seen`` holds the entries of every list that was read; ``complete_lists``
    names the lists that were read to their end.

    * An entry with a new key is ``added``.
    * A retired lesson that is seen again is ``revived``.
    * A lesson that is no longer seen is ``retired``, but only when the list
      it was last seen in was read to its end: a list that is not in the
      directory, or was cut at a cap, says nothing about its entries.
    * A lesson whose title, summary, list or tags differ from what is stored
      is ``changed``, and the event carries the new text; a revived lesson
      carries it in its ``revived`` event. A line number alone is no change.
    * A lesson of the seed keeps its reviewed text: a refresh retires and
      revives it and never writes ``changed`` for it.
    """
    actions: list[Action] = []
    unchanged = 0
    for key in sorted(set(current) | set(seen)):
        stored, entry = current.get(key), seen.get(key)
        if stored is None:
            assert entry is not None
            actions.append(Action("added", key, entry, new_lesson=True, list_name=list_name(entry.source_list)))
            continue
        stored_list = list_name(stored.source_list)
        if entry is None:
            if not stored.retired and stored_list in complete_lists:
                actions.append(Action("retired", key, None, list_name=stored_list))
            elif not stored.retired:
                unchanged += 1
            continue
        differs = stored.origin == "refresh" and (stored.title, stored.summary, stored_list, stored.tags) != (
            entry.title,
            entry.summary,
            list_name(entry.source_list),
            entry.tags,
        )
        if stored.retired:
            actions.append(Action("revived", key, entry if differs else None, list_name=list_name(entry.source_list)))
        elif differs:
            actions.append(Action("changed", key, entry, list_name=list_name(entry.source_list)))
        else:
            unchanged += 1
    return actions, unchanged


# -- matching lessons to a project ---------------------------------------------


@dataclass(frozen=True)
class ProjectTags:
    """What the latest scan says a project is made of, as tags, and what stands behind each tag.

    ``manifests`` maps a dependency to the manifest files that name it,
    ``manifest_hashes`` a manifest file to the hash of its text, and
    ``capability_files`` a capability to the source files that import one of
    its modules (empty when only a dependency shows the capability).
    """

    tags: frozenset[str]
    manifests: dict[str, tuple[str, ...]]
    manifest_hashes: dict[str, str]
    capability_files: dict[str, tuple[str, ...]]


def project_tags(
    languages: list[str],
    manifests: dict[str, list[str]],
    manifest_hashes: dict[str, str],
    importers: dict[str, list[str]],
    tag_map: dict[str, Any],
) -> ProjectTags:
    """A project's tags: its languages, its dependencies by exact name, and the capabilities those show.

    A capability is present when a manifest names one of its packages or a
    source file imports one of its modules (``prism_tags.json``). Nothing is
    guessed from prose or from file names.
    """
    tags = {f"language:{name}" for name in languages if name in tag_map["languages"]}
    tags |= {f"dependency:{name}" for name in manifests}
    capability_files: dict[str, tuple[str, ...]] = {}
    for name, shown_by in sorted(tag_map["capabilities"].items()):
        shown_by = shown_by if isinstance(shown_by, dict) else {}
        packages = [package for package in shown_by.get("dependencies", []) if package in manifests]
        files = sorted({path for module in shown_by.get("imports", []) for path in importers.get(module, [])})
        if packages or files:
            tags.add(f"capability:{name}")
            capability_files[name] = tuple(files)
    return ProjectTags(
        frozenset(tags), {name: tuple(sorted(set(paths))) for name, paths in manifests.items()}, dict(manifest_hashes), capability_files
    )


def part_hash(lines: list[str]) -> str:
    """A short hash of a list of lines, for a part of a fingerprint that would be long as text."""
    return hashlib.sha256("\n".join(lines).encode("utf-8", errors="replace")).hexdigest()[:PART_HASH_CHARS]


def touch_parts(matched_on: list[str], project: ProjectTags) -> dict[str, Any]:
    """What a selected lesson rests on in a project, part by part (R-PRISM-5).

    ``tags``: the tags it matched on. ``manifest:PATH``: the hash of each
    manifest that names a matched dependency. ``imports:NAME``: a hash of
    the list of files that import a module of a matched capability; the
    files' content is not part of it, so an edit inside one changes nothing.
    A lesson matched on a language alone has only ``tags``.
    """
    parts: dict[str, Any] = {"tags": list(matched_on)}
    for tag in matched_on:
        kind, _, name = tag.partition(":")
        if kind == "dependency":
            for path in project.manifests.get(name, ()):
                parts[f"manifest:{path}"] = project.manifest_hashes.get(path, "")
        elif kind == "capability":
            parts[f"imports:{name}"] = part_hash(list(project.capability_files.get(name, ())))
    return parts


def changed_parts(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """The parts that differ between two fingerprints, by name. ``requirement:`` parts are compared elsewhere."""
    names = {name for name in set(old) | set(new) if not name.startswith("requirement:")}
    return sorted(name for name in names if old.get(name) != new.get(name))


def parse_verdict(body: str) -> tuple[dict[str, Any] | None, str | None]:
    """A verdict from the start of a note's body: (verdict, None) or (None, what is wrong).

    The body starts with ``verdict: adopt|edit|delete|not-relevant`` and a
    ``reason: <text>`` line; ``adopt`` also needs ``work: <id>``, the work
    item that will carry the change. The lines stand together at the top,
    in any order after the first; whatever follows them is the agent's own
    text and is not read here.
    """
    fields: dict[str, str] = {}
    started = False
    for raw in body.lstrip("\ufeff").splitlines()[:50]:
        line = raw.strip()
        if not line and not started:
            continue
        match = _VERDICT_LINE.match(line) if len(line) <= MAX_LINE_CHARS else None
        if not match:
            break
        started = True
        fields.setdefault(match.group(1), match.group(2).strip())
        if "verdict" not in fields:  # the first line was not the verdict
            break
    expected = "|".join(VERDICTS)
    if next(iter(fields), None) != "verdict":
        return None, f"the body must start with a line 'verdict: {expected}'"
    if fields["verdict"] not in VERDICTS:
        return None, f"verdict {fields['verdict'][:40]!r} is not one of {expected}"
    if not fields.get("reason"):
        return None, "a line 'reason: <text>' must follow the verdict"
    verdict: dict[str, Any] = {"verdict": fields["verdict"], "reason": fields["reason"]}
    if fields["verdict"] == "adopt":
        work = fields.get("work", "").lstrip("#")
        if not work.isascii() or not work.isdigit():
            return None, "verdict adopt needs a line 'work: <id>', the id of the work item that will carry the change"
        verdict["work"] = int(work)
    return verdict, None
