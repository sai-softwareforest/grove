"""A read-only copy of one project for people: pages, and `grove export`.

Agents change a workshop through the operations in ``service``; nothing here
changes the database. This module builds the *pages* of a project (index,
requirements, one page per source file, knowledge, findings, work items) as
small block lists, and writes them as Markdown files. ``view`` renders the
same pages as HTML, so the two copies cannot drift.

A page is a list of blocks:

* ``("h", level, inline)``, ``("p", inline)``, ``("ul", [inline, ...])``;
* ``("md", text)``: stored text (a note's body, a plan), passed on as it is;
* ``("hr",)``.

``inline`` is a list of parts: a string, ``("code", text)``,
``("link", text, target)`` or ``("anchor", id)``. A target names a page, never
a file or a URL of ours: ``("index",)``, ``("requirements", anchor)``,
``("file", stored_path)``, ``("knowledge", key)``, ``("findings", key)``,
``("work", id)``, ``("url", href)``, ``("route", path)``. Each renderer
resolves targets its own way.

What a page never holds (R-VIEW-4): the data directory, the database path, a
project's root, or any other path of this machine that Grove itself supplies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from functools import cached_property
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Iterable

from . import _source_root
from .db import DB_FILENAME
from .errors import GroveError
from .scan import EXPORT_MARKER
from .service import FINDING_KINDS, LAYERS, STATUSES, Grove

MAX_SLUG_CHARS = 80
LISTED_PAGES = 50  # an export result names at most this many written pages and this many stale ones
MARKER_HEAD = "grove-export 1"
PAGE_DIRS = ("blueprint", "knowledge", "work")
REDACTED = "[redacted]"

_SLUG_JUNK = re.compile(r"[^a-z0-9]+")
_REQUIREMENT = re.compile(r"\bR-[A-Z]+-\d+\b")
_WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")
# An underscore inside a word starts no emphasis, so the names of kinds, statuses and files stay readable.
_MD_SPECIAL = re.compile(r"([\\`*\[\]<]|(?<![A-Za-z0-9])_|_(?![A-Za-z0-9]))")
_BACKTICKS = re.compile(r"`+")
_SPACES = re.compile(r"\s+")
_WEB_URL = re.compile(r"^https?://[^\s<>\"'`]+$")
# What `scripts/check-publish` refuses in a commit, as far as it can be told
# from text alone: tokens of the services it names, an agent session id, and
# the start of a home-directory path. A page is searched before it is written.
_SECRET = re.compile(
    r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|gh[ous]_[A-Za-z0-9]{20,}"
    r"|[sr]k_(?:live|test)_[A-Za-z0-9]+|whsec_[A-Za-z0-9]+|xox[baprs]-[A-Za-z0-9-]+"
    r"|A[KS]IA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"
    r"|xai-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]+|sk-proj-[A-Za-z0-9_-]+"
    r"|session_[0-9A-Za-z]{20,}"
    # /home/NAME, /Users/NAME, C:\Users\NAME: the name goes, the rest of the path stays.
    # Not after a letter, digit, dot or dash, so "example.org/home/page" and "src/home/x.py" are left alone.
    r"|(?<![\w.\-])/(?:home|Users)/[^/\s\"'`<>()\[\]]+"
    r"|(?<![\w.\-])[A-Za-z]:\\Users\\[^\\\s\"'`<>()\[\]]+"
)
# A database URL is a secret only when it carries "user:password@"; that is looked at in code,
# so the pattern itself reads each run of characters once.
_DATABASE_URL = re.compile(r"(?:postgres|mysql|mongodb(?:\+srv)?)://([^\s\"']++)")

Inline = list[Any]
Block = tuple[Any, ...]


# --------------------------------------------------------------------------
# Names


def slug(text: str) -> str:
    """A page name: lower-case letters, digits and single dashes, at most MAX_SLUG_CHARS."""
    return _SLUG_JUNK.sub("-", text.lower()).strip("-")[:MAX_SLUG_CHARS].strip("-") or "page"


def assign_slugs(names: Iterable[tuple[str, str]]) -> dict[str, str]:
    """A slug for each ``(identity, text)``, no two alike.

    In the order of ``(text, identity)`` the first holder of a slug keeps it;
    a later one gets ``-`` and eight hex digits of a SHA-256 of its identity,
    inside the same length limit.
    """
    taken: set[str] = set()
    slugs: dict[str, str] = {}
    for text, identity in sorted({(text, identity) for identity, text in names}):
        candidate = slug(text)
        attempt = 0
        while candidate in taken:
            seed = identity if attempt == 0 else f"{identity}\0{attempt}"
            digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:8]
            candidate = slug(text)[: MAX_SLUG_CHARS - 9].strip("-") + "-" + digest
            attempt += 1
        taken.add(candidate)
        slugs[identity] = candidate
    return slugs


def shown_path(stored: str | None, root: str) -> str:
    """A source path as a page shows it: relative to the project root, never a path of this machine.

    Scanned files are stored relative already. A map is stored with its full
    path: inside the root it is shown relative to it, outside only by name.
    """
    if not stored:
        return "(no source)"
    windows = bool(_WINDOWS_ABSOLUTE.match(stored))
    if not windows and not stored.startswith("/"):
        return stored
    flavour = PureWindowsPath if windows else PurePosixPath
    path = flavour(stored)
    try:
        return path.relative_to(flavour(root)).as_posix() or path.name
    except ValueError:
        return path.name or "(no source)"


def is_web_url(text: str) -> bool:
    """True for an http or https address without a space, quote or angle bracket: the only links that leave a page."""
    return bool(_WEB_URL.match(text))


def anchor_id(key: str) -> str:
    """A finding key as an anchor: a numbered key ``abc#2`` is ``abc-2``."""
    return key.replace("#", "-")


def finding_source(finding: dict[str, Any]) -> str | None:
    """The stored source path a finding is about, if it names one."""
    evidence = finding["evidence"]
    paths = evidence.get("paths") or [None]
    return evidence.get("source_path") or paths[0]


# --------------------------------------------------------------------------
# Reading one project


class Reader:
    """Everything the pages of one project show, read on demand and only read."""

    def __init__(self, grove: Grove, project: Any) -> None:
        self.grove = grove
        self.conn = grove.conn
        self.row = grove._project(project)
        self.id: int = self.row["id"]
        self.name: str = self.row["name"]
        self.root: str = self.row["root_path"]

    def shown(self, stored: str | None) -> str:
        return shown_path(stored, self.root)

    @cached_property
    def files(self) -> list[dict[str, Any]]:
        """One entry per source path: ``stored``, ``shown``, ``slug`` and the item count per layer."""
        counts = ", ".join(f"SUM(layer = '{name}') AS {name}" for name in LAYERS)
        rows = self.conn.execute(
            f"SELECT COALESCE(source_path, '') AS stored, {counts} FROM blueprint_items "
            "WHERE project_id = ? GROUP BY COALESCE(source_path, '')",
            (self.id,),
        ).fetchall()
        entries = [
            {"stored": row["stored"], "shown": self.shown(row["stored"]), **{name: row[name] for name in LAYERS}}
            for row in rows
        ]
        slugs = assign_slugs((entry["stored"], entry["shown"]) for entry in entries)
        for entry in entries:
            entry["slug"] = slugs[entry["stored"]]
        return sorted(entries, key=lambda entry: (entry["shown"], entry["stored"]))

    @cached_property
    def file_by_stored(self) -> dict[str, dict[str, Any]]:
        return {entry["stored"]: entry for entry in self.files}

    def file_by_slug(self, name: str) -> dict[str, Any] | None:
        return next((entry for entry in self.files if entry["slug"] == name), None)

    def items(self, layer: str | None = None, stored: str | None = None) -> list[dict[str, Any]]:
        where = ["project_id = ?"]
        params: list[Any] = [self.id]
        if layer is not None:
            where.append("layer = ?")
            params.append(layer)
        if stored is not None:
            where.append("COALESCE(source_path, '') = ?")
            params.append(stored)
        rows = self.conn.execute(f"SELECT * FROM blueprint_items WHERE {' AND '.join(where)} ORDER BY id", params)
        return [Grove._item_row(row) for row in rows]

    @cached_property
    def findings(self) -> list[dict[str, Any]]:
        """Every stored finding, by kind in the documented order, then by key."""
        rows = self.conn.execute("SELECT * FROM findings WHERE project_id = ?", (self.id,)).fetchall()
        found = [Grove._finding_row(row) for row in rows]
        return sorted(found, key=lambda finding: (FINDING_KINDS.index(finding["kind"]), finding["key"] or ""))

    @cached_property
    def finding_keys(self) -> set[str]:
        return {finding["key"] for finding in self.findings if finding["key"]}

    @cached_property
    def knowledge(self) -> list[dict[str, Any]]:
        """The latest revision of each of the project's documents, by key, without bodies."""
        rows = self.conn.execute(
            "SELECT k.id, k.key, k.title, k.revision, k.created_at, k.author FROM knowledge k "
            "WHERE k.project_id = ? AND k.revision = "
            "(SELECT MAX(k2.revision) FROM knowledge k2 WHERE k2.key = k.key AND k2.project_id = k.project_id) "
            "ORDER BY k.key",
            (self.id,),
        ).fetchall()
        documents = [dict(row) for row in rows]
        slugs = assign_slugs((document["key"], document["key"]) for document in documents)
        for document in documents:
            document["slug"] = slugs[document["key"]]
        return documents

    @cached_property
    def knowledge_by_key(self) -> dict[str, dict[str, Any]]:
        return {document["key"]: document for document in self.knowledge}

    def body(self, knowledge_id: int) -> str:
        return self.conn.execute("SELECT body FROM knowledge WHERE id = ?", (knowledge_id,)).fetchone()[0]

    @cached_property
    def work(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT w.*, p.name AS project FROM work_items w JOIN projects p ON p.id = w.project_id "
            "WHERE w.project_id = ? ORDER BY w.id",
            (self.id,),
        ).fetchall()
        return [Grove._work_row(row) for row in rows]

    def events(self, work_id: int) -> list[dict[str, Any]]:
        """The whole history of a work item, oldest first."""
        rows = self.conn.execute(
            "SELECT created_at, author, old_status, new_status, note FROM work_events WHERE work_item_id = ? ORDER BY id",
            (work_id,),
        )
        return [dict(row) for row in rows]

    @cached_property
    def requirement_items(self) -> dict[str, int]:
        """Requirement id -> the first declared item whose title states it."""
        first: dict[str, int] = {}
        rows = self.conn.execute(
            "SELECT id, title FROM blueprint_items WHERE project_id = ? AND layer = 'declared' AND title LIKE '%R-%' "
            "ORDER BY id",
            (self.id,),
        )
        for row in rows:
            for name in _REQUIREMENT.findall(row["title"]):
                first.setdefault(name, row["id"])
        return first


# --------------------------------------------------------------------------
# Pages


def _count_words(counts: dict[str, int], names: Iterable[str]) -> str:
    return ", ".join(f"{name} {counts.get(name, 0)}" for name in names)


def _repeats(title: str, body: str) -> bool:
    """True when the body says the title again: the same text, or the text the title was shortened from."""
    stem = " ".join(title.split())
    for mark in ("…", "..."):
        if stem.endswith(mark):
            stem = stem[: -len(mark)].rstrip()
            break
    return body.startswith(stem)


def _item_line(item: dict[str, Any]) -> Inline:
    extra = item["extra"]
    line: Inline = []
    if item["source_line"]:
        line.append(f"line {item['source_line']}: ")
    kind = extra.get("kind")
    title = item["title"]
    body = " ".join(item["body"].split())
    if body and _repeats(title, body):
        title, body = body, ""
    if kind in ("module", "test_file", "symbol", "test"):
        line.append(("code", title))
    else:
        line.append(title)
    if kind == "heading":
        notes = [f"heading, level {extra.get('level')}"]
    else:
        notes = [str(extra[name]) for name in ("class", "language") if extra.get(name)]
        if not notes and kind and kind != "sentence":
            notes = [str(kind).replace("_", " ")]
    if notes:
        line.append(f" ({', '.join(notes)})")
    if body:
        line.append(" — " + body)
    return line


def _ref_line(reader: Reader, ref: str) -> Inline:
    """One reference of a work item, linked when what it names is in this project."""
    if ref.startswith("knowledge:"):
        key = ref[len("knowledge:") :]
        if key in reader.knowledge_by_key:
            return [("link", ref, ("knowledge", key))]
        return [("code", ref), " (no document of this project has that key)"]
    if ref.startswith("finding:"):
        key = ref[len("finding:") :]
        if key in reader.finding_keys:
            return [("link", ref, ("findings", key))]
        return [("code", ref), " (not among the stored findings)"]
    if ref.startswith("https://"):
        return [("link", ref, ("url", ref))]
    if ref in reader.requirement_items:
        return [("link", ref, ("requirements", ref))]
    return [("code", ref)]


_INDEX_INTRO = {
    "export": "A read-only copy of this Grove project. It is changed through Grove (the CLI or the MCP tools), "
    "never here: an edit to an exported page is not read back, and the next export replaces it.",
    "view": "A live, read-only view of this Grove project. It is changed through Grove (the CLI or the MCP tools), "
    "never here.",
}


def index_page(reader: Reader, mode: str = "export") -> tuple[str, list[Block]]:
    """The project page. `mode` is "export" or "view": only the opening paragraph differs."""
    counts = reader.grove._counts(reader.id)
    declared_files = sum(1 for entry in reader.files if entry["declared"])
    facts: list[Inline] = [
        [f"Last scanned: {reader.row['last_scanned_at'] or 'never'}"],
        [f"Blueprint items: {_count_words(counts['items'], LAYERS)}"],
        [
            ("link", "Requirements", ("requirements", None)),
            f": {counts['items']['declared']} declared item(s) in {declared_files} file(s)",
        ],
        [
            ("link", "Findings", ("findings", None)),
            f" (heuristic): {_count_words(counts['findings'], FINDING_KINDS)}",
        ],
        [("link", "Work items", ("work", None)), f": {_count_words(counts['work_items'], STATUSES)}"],
    ]
    blocks: list[Block] = [
        ("h", 1, [reader.name]),
        ("p", [_INDEX_INTRO[mode]]),
        ("ul", facts),
        ("h", 2, ["Blueprint files"]),
    ]
    if reader.files:
        blocks.append(
            (
                "ul",
                [
                    [("link", entry["shown"], ("file", entry["stored"])), f": {_count_words(entry, LAYERS)}"]
                    for entry in reader.files
                ],
            )
        )
    else:
        blocks.append(("p", ["No blueprint items are stored. Scan the project to fill the blueprint."]))
    blocks.append(("h", 2, ["Knowledge"]))
    if reader.knowledge:
        blocks.append(
            (
                "ul",
                [
                    [("link", document["title"], ("knowledge", document["key"])), " (", ("code", document["key"]), ")"]
                    for document in reader.knowledge
                ],
            )
        )
    else:
        blocks.append(("p", ["No knowledge documents in this project. Workspace notes belong to no project."]))
    blocks.append(("h", 2, ["Work items"]))
    if reader.work:
        blocks.append(("ul", [[("link", f"#{item['id']} {item['title']}", ("work", item["id"]))] for item in reader.work]))
    else:
        blocks.append(("p", ["No work items."]))
    return reader.name, blocks


def requirements_page(reader: Reader) -> tuple[str, list[Block]]:
    blocks: list[Block] = [
        ("h", 1, ["Requirements"]),
        (
            "p",
            [
                "What the project's documents declare, grouped by the file that says it. ",
                ("link", "Back to the index", ("index",)),
                ".",
            ],
        ),
    ]
    anchors: dict[int, list[str]] = {}
    for name, item_id in sorted(reader.requirement_items.items()):
        anchors.setdefault(item_id, []).append(name)
    by_file: dict[str, list[dict[str, Any]]] = {}
    for item in reader.items(layer="declared"):
        by_file.setdefault(item["source_path"] or "", []).append(item)
    for entry in reader.files:
        items = by_file.get(entry["stored"])
        if not items:
            continue
        blocks.append(("h", 2, [("link", entry["shown"], ("file", entry["stored"]))]))
        blocks.append(
            ("ul", [[*(("anchor", name) for name in anchors.get(item["id"], [])), *_item_line(item)] for item in items])
        )
    if not by_file:
        blocks.append(("p", ["No declared items are stored."]))
    return "Requirements", blocks


def file_page(reader: Reader, entry: dict[str, Any]) -> tuple[str, list[Block]]:
    blocks: list[Block] = [
        ("h", 1, [("code", entry["shown"])]),
        ("p", ["One source file in the three layers of the blueprint. ", ("link", "Back to the index", ("index",)), "."]),
    ]
    items = reader.items(stored=entry["stored"])
    for layer in LAYERS:
        mine = [item for item in items if item["layer"] == layer]
        blocks.append(("h", 2, [f"{layer.capitalize()} ({len(mine)})"]))
        if mine:
            blocks.append(("ul", [_item_line(item) for item in mine]))
    about = [finding for finding in reader.findings if (finding_source(finding) or "") == entry["stored"]]
    blocks.append(("h", 2, [f"Findings ({len(about)})"]))
    if about:
        blocks.append(
            (
                "ul",
                [
                    [("link", finding["key"], ("findings", finding["key"])), f" {finding['kind']}: {finding['summary']}"]
                    for finding in about
                ],
            )
        )
    return entry["shown"], blocks


def findings_page(reader: Reader) -> tuple[str, list[Block]]:
    blocks: list[Block] = [
        ("h", 1, ["Findings"]),
        (
            "p",
            [
                "Places where two layers of the blueprint disagree, by token overlap. Every finding is a heuristic: "
                "read the code before acting on one. ",
                ("link", "Back to the index", ("index",)),
                ".",
            ],
        ),
    ]
    cap = Grove._cap_info(reader.row)
    if cap["note"]:
        blocks.append(("p", [cap["note"]]))
    for kind in FINDING_KINDS:
        mine = [finding for finding in reader.findings if finding["kind"] == kind]
        if not mine:
            continue
        blocks.append(("h", 2, [f"{kind} ({len(mine)})"]))
        lines: list[Inline] = []
        for finding in mine:
            line: Inline = [("anchor", anchor_id(finding["key"])), ("code", finding["key"]), " " + finding["summary"]]
            source = finding_source(finding)
            if source and source in reader.file_by_stored:
                line += [" — ", ("link", reader.shown(source), ("file", source))]
            lines.append(line)
        blocks.append(("ul", lines))
    if not reader.findings:
        blocks.append(("p", ["No findings are stored."]))
    return "Findings", blocks


def knowledge_page(
    document: dict[str, Any], body: str, latest_revision: int, back: Any | None = ("index",)
) -> tuple[str, list[Block]]:
    """One revision of a document. ``document`` has key, title, revision, created_at, author."""
    facts: list[Inline] = [
        ["Key: ", ("code", document["key"])],
        [f"Revision: {document['revision']} of {latest_revision}"],
        [f"Author: {document['author'] or 'not recorded'}"],
        [f"Written: {document['created_at']}"],
    ]
    blocks: list[Block] = [("h", 1, [document["title"]])]
    if back is not None:
        blocks.append(("p", [("link", "Back to the index", back), "."]))
    blocks += [("ul", facts), ("hr",), ("md", body)]
    return document["title"], blocks


def work_index_page(reader: Reader) -> tuple[str, list[Block]]:
    blocks: list[Block] = [("h", 1, ["Work items"]), ("p", [("link", "Back to the index", ("index",)), "."])]
    for status in STATUSES:
        mine = [item for item in reader.work if item["status"] == status]
        if not mine:
            continue
        blocks.append(("h", 2, [f"{status} ({len(mine)})"]))
        blocks.append(("ul", [[("link", f"#{item['id']} {item['title']}", ("work", item["id"]))] for item in mine]))
    if not reader.work:
        blocks.append(("p", ["No work items."]))
    return "Work items", blocks


def work_page(reader: Reader, item: dict[str, Any]) -> tuple[str, list[Block]]:
    title = f"#{item['id']} {item['title']}"
    facts: list[Inline] = [
        [f"Status: {item['status']}"],
        [f"Author: {item['author'] or 'not recorded'}"],
        [f"Created: {item['created_at']}"],
        [f"Updated: {item['updated_at']}"],
    ]
    if item["issue_url"]:
        url = item["issue_url"]
        facts.append(["Issue: ", ("link", url, ("url", url)) if is_web_url(url) else ("code", url)])
    blocks: list[Block] = [
        ("h", 1, [title]),
        ("p", [("link", "All work items", ("work", None)), " · ", ("link", "Index", ("index",))]),
        ("ul", facts),
    ]
    if item["refs"]:
        blocks.append(("h", 2, ["References"]))
        blocks.append(("ul", [_ref_line(reader, ref) for ref in item["refs"]]))
        if item.get("refs_omitted"):
            blocks.append(("p", [f"{item['refs_omitted']} more reference(s) are not listed (the list holds 50)."]))
    for heading, text in (("Plan", item["plan"]), ("Notes", item["notes"])):
        if text.strip():
            blocks += [("h", 2, [heading]), ("md", text)]
    events = reader.events(item["id"])
    blocks.append(("h", 2, [f"History ({len(events)})"]))
    lines: list[Inline] = []
    for event in events:
        change = (
            event["new_status"]
            if event["old_status"] == event["new_status"]
            else f"{event['old_status']} → {event['new_status']}"
        )
        text = f"{event['created_at']}, {event['author'] or 'no author'}, {change}"
        if event["note"]:
            text += ": " + " ".join(event["note"].split())
        lines.append([text])
    if lines:
        blocks.append(("ul", lines))
    return title, blocks


# --------------------------------------------------------------------------
# Markdown


def _md_text(text: str) -> str:
    return _MD_SPECIAL.sub(r"\\\1", _SPACES.sub(" ", text))


def _md_code(text: str) -> str:
    text = " ".join(text.split())
    longest = max((len(run) for run in _BACKTICKS.findall(text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def _md_inline(parts: Inline, href: Callable[[Any], str | None]) -> str:
    out: list[str] = []
    for part in parts:
        if isinstance(part, str):
            out.append(_md_text(part))
        elif part[0] == "code":
            out.append(_md_code(part[1]))
        elif part[0] == "anchor":
            out.append(f'<a id="{part[1]}"></a>')
        else:
            target = href(part[2])
            label = _md_text(part[1])
            # A target that cannot be written as a link (no page, or characters a link cannot hold) stays text.
            out.append(f"[{label}]({target})" if target and not re.search(r"[\s()<>]", target) else label)
    return "".join(out)


def to_markdown(blocks: list[Block], href: Callable[[Any], str | None]) -> str:
    """The page as Markdown: LF line ends, one trailing newline, nothing that changes between two runs."""
    out: list[str] = []
    for block in blocks:
        kind = block[0]
        if kind == "h":
            out.append("#" * block[1] + " " + _md_inline(block[2], href))
        elif kind == "p":
            out.append(_md_inline(block[1], href))
        elif kind == "ul":
            out.append("\n".join("- " + _md_inline(line, href) for line in block[1]))
        elif kind == "hr":
            out.append("---")
        elif kind == "md":
            text = "\n".join(line.rstrip() for line in block[1].replace("\r\n", "\n").replace("\r", "\n").split("\n"))
            out.append(text.strip("\n"))
    return "\n\n".join(part for part in out if part) + "\n"


def redact(text: str, literals: Iterable[str] = ()) -> tuple[str, int]:
    """Replace what must not leave the machine by ``[redacted]``; return the text and the number of replacements.

    ``literals`` are exact strings (the data directory, the project root).
    The patterns are those of the publish check: service tokens, database
    URLs with a password, agent session ids, and the user part of a
    home-directory path.
    """
    count = 0
    for literal in sorted({value for value in literals if len(value) > 1}, key=len, reverse=True):
        found = text.count(literal)
        if found:
            text = text.replace(literal, REDACTED)
            count += found
    text, found = _SECRET.subn(REDACTED, text)
    count += found

    def database_url(match: re.Match[str]) -> str:
        nonlocal count
        rest = match.group(1)
        colon = rest.find(":")
        if colon < 0 or rest.find("@", colon + 1) < 0:  # no "user:password@": two finds, so a long run is read twice at most
            return match.group()
        count += 1
        return REDACTED

    return _DATABASE_URL.sub(database_url, text), count


def export_pages(reader: Reader) -> dict[str, str]:
    """Every page of the project as Markdown, by its path inside the export directory (``/`` separated)."""
    paths: dict[Any, str] = {
        ("index",): "index.md",
        ("requirements",): "requirements.md",
        ("findings",): "findings.md",
        ("work", None): "work/index.md",
    }
    for entry in reader.files:
        paths[("file", entry["stored"])] = f"blueprint/{entry['slug']}.md"
    for document in reader.knowledge:
        paths[("knowledge", document["key"])] = f"knowledge/{document['slug']}.md"
    for item in reader.work:
        paths[("work", item["id"])] = f"work/{item['id']}.md"

    def linker(page_path: str) -> Callable[[Any], str | None]:
        up = "../" * page_path.count("/")

        def href(target: Any) -> str | None:
            if target[0] == "url":
                return target[1] if is_web_url(target[1]) else None
            fragment = ""
            if target[0] in ("requirements", "findings"):
                if target[1]:
                    fragment = "#" + (anchor_id(target[1]) if target[0] == "findings" else target[1])
                target = (target[0],)
            path = paths.get(target)
            return up + path + fragment if path else None

        return href

    built: list[tuple[str, list[Block]]] = [
        ("index.md", index_page(reader)[1]),
        ("requirements.md", requirements_page(reader)[1]),
        ("findings.md", findings_page(reader)[1]),
        ("work/index.md", work_index_page(reader)[1]),
    ]
    built += [(paths[("file", entry["stored"])], file_page(reader, entry)[1]) for entry in reader.files]
    for document in reader.knowledge:
        page = knowledge_page(document, reader.body(document["id"]), document["revision"])
        built.append((paths[("knowledge", document["key"])], page[1]))
    built += [(paths[("work", item["id"])], work_page(reader, item)[1]) for item in reader.work]
    return {path: to_markdown(blocks, linker(path)) for path, blocks in built}


# --------------------------------------------------------------------------
# Writing


def default_out(grove: Grove, reader: Reader) -> Path:
    """``<data dir>/exports/<project slug>``: outside every project root, because the data directory is."""
    names = [row["name"] for row in grove.conn.execute("SELECT name FROM projects")]
    return grove.home / "exports" / assign_slugs((name, name) for name in names)[reader.name]


def _refuse(message: str) -> GroveError:
    return GroveError("invalid", message + " Nothing was written.")


def _lstat(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None


def _check_directory(grove: Grove, reader: Reader, target: Path) -> None:
    """Every reason not to write into ``target``. Reads only."""
    status = _lstat(target)
    if status is not None and stat.S_ISLNK(status.st_mode):
        raise _refuse(f"the export directory {str(target)!r} is a symbolic link, and an export follows none.")
    real = Path(os.path.realpath(target))
    for project in grove.conn.execute("SELECT name, root_path FROM projects ORDER BY name"):
        root = Path(os.path.realpath(project["root_path"]))
        if real == root or root in real.parents:
            raise _refuse(
                f"the export directory {str(real)!r} is inside the root of project {project['name']!r} "
                f"({str(root)!r}), and Grove never writes inside a project it scans (R-INV-4). Choose a directory "
                "outside every registered project, or omit --out for the default inside the data directory."
            )
    if real == grove.home:
        raise _refuse(f"the export directory {str(real)!r} is the Grove data directory itself; name a directory of its own.")
    if _lstat(real / DB_FILENAME) is not None:
        raise _refuse(f"the export directory {str(real)!r} holds a {DB_FILENAME}: it is a Grove data directory.")
    source = _source_root()
    if source is not None and (real == source or source in real.parents):
        if Path(os.path.realpath(reader.root)) != source:
            raise _refuse(
                f"the export directory {str(real)!r} is inside Grove's own source tree, and project "
                f"{reader.name!r} is not that tree."
            )
    if status is None:
        return
    if not stat.S_ISDIR(status.st_mode):
        raise _refuse(f"the export path {str(target)!r} exists and is not a directory.")
    marker = _lstat(target / EXPORT_MARKER)
    if marker is None:
        with os.scandir(target) as entries:
            if next(entries, None) is not None:
                raise _refuse(
                    f"the directory {str(target)!r} is not empty and holds no {EXPORT_MARKER} file, so it is not an "
                    "earlier export and its files are not Grove's to replace. Name an empty or a new directory."
                )
        return
    if not stat.S_ISREG(marker.st_mode):
        raise _refuse(f"{EXPORT_MARKER} in {str(target)!r} is not a regular file.")
    owner = _marker_project(_read(target / EXPORT_MARKER))
    if owner is not None and owner != reader.name:
        raise _refuse(
            f"the directory {str(target)!r} holds the export of project {owner!r}, not of {reader.name!r}; "
            "each project is exported to a directory of its own."
        )


def _marker_text(project: str) -> str:
    return f"{MARKER_HEAD}\n{json.dumps({'project': project})}\n"


def _marker_project(data: bytes | None) -> str | None:
    lines = (data or b"").decode("utf-8", errors="replace").splitlines()
    try:
        value = json.loads(lines[1])["project"]
    except (IndexError, ValueError, KeyError, TypeError):
        return None
    return value if isinstance(value, str) else None


_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _read(path: Path) -> bytes | None:
    """The bytes of a regular file, or None when there is no such file. Never through a symbolic link."""
    try:
        handle = os.open(path, os.O_RDONLY | _NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(handle, "rb") as stream:
        return stream.read()


def _write(path: Path, data: bytes) -> None:
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _NOFOLLOW, 0o644)
    with os.fdopen(handle, "wb") as stream:
        stream.write(data)


def _listed(entries: list[str]) -> dict[str, Any]:
    shown = entries[:LISTED_PAGES]
    return {"total": len(entries), "items": shown, "omitted": len(entries) - len(shown)}


def export_project(grove: Grove, project: Any, out: Any = None) -> dict[str, Any]:
    """Write the project's pages as Markdown files into ``out`` (default: inside the data directory).

    Every refusal is decided before the first byte is written. A page whose
    bytes are already on disk is left alone; a page of an earlier export that
    this one no longer produces is reported as stale and is not removed.
    """
    reader = Reader(grove, project)
    if out is None or out == "":
        target = default_out(grove, reader)
    elif isinstance(out, (str, os.PathLike)):
        target = Path(os.path.abspath(Path(out).expanduser()))
    else:
        raise GroveError("invalid", "out must be a directory path")
    try:
        _check_directory(grove, reader, target)
        literals = [str(grove.home), reader.root]
        pages: dict[str, bytes] = {}
        redactions = 0
        for path, text in export_pages(reader).items():
            text, found = redact(text, literals)
            redactions += found
            pages[path] = text.encode("utf-8", errors="replace")
        # Every path this export will touch, looked at before any is written.
        for name in PAGE_DIRS:
            status = _lstat(target / name)
            if status is not None and not stat.S_ISDIR(status.st_mode):
                raise _refuse(f"{str(target / name)!r} is not a directory (a symbolic link is not followed).")
        for path in pages:
            status = _lstat(target / path)
            if status is not None and not stat.S_ISREG(status.st_mode):
                raise _refuse(f"{str(target / path)!r} is not a regular file (a symbolic link is not followed).")

        target.mkdir(parents=True, exist_ok=True)
        for name in PAGE_DIRS:
            (target / name).mkdir(exist_ok=True)
        marker = _marker_text(reader.name).encode("utf-8")
        if _read(target / EXPORT_MARKER) != marker:
            _write(target / EXPORT_MARKER, marker)
        written: list[str] = []
        for path in sorted(pages):
            if _read(target / path) != pages[path]:
                _write(target / path, pages[path])
                written.append(path)
        stale: list[str] = []
        for folder in ("", *PAGE_DIRS):
            with os.scandir(target / folder) as entries:
                for entry in entries:
                    path = f"{folder}/{entry.name}" if folder else entry.name
                    if entry.name.endswith(".md") and path not in pages and not entry.is_dir(follow_symlinks=False):
                        stale.append(path)
    except OSError as exc:
        raise GroveError("io", f"export to {str(target)!r} failed: {exc}") from exc
    return {
        "project": reader.name,
        "out": str(target),
        "pages": len(pages),
        "written": _listed(written),
        "unchanged": len(pages) - len(written),
        "stale": _listed(sorted(stale)),
        "redactions": redactions,
        "note": (
            "Stale pages are from an earlier export and are no longer produced; Grove deletes nothing, remove them "
            "yourself. " if stale else ""
        )
        + "The pages are a read-only copy: change the project through Grove and export again.",
    }
