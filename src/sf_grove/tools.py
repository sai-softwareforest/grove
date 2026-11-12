"""The sixteen Grove operations as a table: name, description, input schema, handler.

The MCP server publishes this table; the CLI calls the same handlers. This
module does not import the MCP SDK, so the CLI stays quick to start.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Callable

from .errors import GroveError, fail, ok
from .service import Grove

LOCAL = " Grove is local only: scans are read-only and nothing is sent to GitHub or any other service."

_PROJECT = {"type": ["string", "integer"], "description": "Project name, or its numeric id."}
_LIMIT = {"type": "integer", "minimum": 1, "maximum": 200, "default": 50, "description": "Page size (default 50, max 200)."}
_OFFSET = {"type": "integer", "minimum": 0, "default": 0, "description": "Number of items to skip."}
_STATUS = {"type": "string", "enum": ["ready", "in_progress", "review", "done", "blocked"]}
_AUTHOR = {
    "type": "string",
    "maxLength": 64,
    "description": "Optional short name of who is writing. Defaults to $GROVE_AUTHOR on the server; "
    "left empty when neither is set.",
}


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[..., Any]
    read_only: bool


TOOLS: tuple[Tool, ...] = (
    Tool(
        "grove_status",
        "Report Grove's version, data directory, database path and project count. "
        "Use it first to confirm which Grove home this session is using." + LOCAL,
        _schema({}),
        lambda grove: grove.status(),
        True,
    ),
    Tool(
        "grove_project_create",
        "Register a codebase as a Grove project: a unique name plus the root directory to map. "
        "Use once per codebase, before grove_scan. Only a row in Grove's own database is written; "
        "the directory itself is not touched." + LOCAL,
        _schema(
            {
                "name": {"type": "string", "description": "Unique project name: letters, digits, '.', '_' or '-'."},
                "root_path": {"type": "string", "description": "Existing directory holding the codebase."},
            },
            ["name", "root_path"],
        ),
        lambda grove, name, root_path: grove.project_create(name, root_path),
        False,
    ),
    Tool(
        "grove_project_list",
        "List registered projects, paginated. Use to find a project name or id." + LOCAL,
        _schema({"limit": _LIMIT, "offset": _OFFSET}),
        lambda grove, limit=None, offset=None: grove.project_list(limit, offset),
        True,
    ),
    Tool(
        "grove_project_get",
        "Get one project by name or id, with last_scanned_at, the last scan's cap warnings, and item, finding "
        "and work-item counts. Finding counts are stored findings; findings_cap (applied, omitted, per-kind cap) "
        "says when a cap left candidates out. Use to check whether a scan is recent or was cut short by a cap."
        + LOCAL,
        _schema({"project": _PROJECT}, ["project"]),
        lambda grove, project: grove.project_get(project),
        True,
    ),
    Tool(
        "grove_scan",
        "Scan a project's root directory and rebuild its blueprint (declared / actual / tests layers), then "
        "recompute gap findings. Use after creating a project and whenever the code or docs have changed. "
        "The scan is deterministic and read-only: it never writes inside the project, honours .gitignore, and "
        "stops at the file and time caps (reported in the result). Changelogs and release notes add no declared "
        "items. Returns counts per layer and per finding kind, the files it skipped (skipped_files), documents "
        "whose declared items were capped (caps.declared_capped), findings caps (findings_cap), "
        "plus a small sample; page the rest with grove_gaps and grove_blueprint_get. It replaces earlier "
        "scan-derived items and findings but keeps knowledge, work items and map-ingested items." + LOCAL,
        _schema(
            {
                "project": _PROJECT,
                "max_files": {"type": "integer", "minimum": 1, "description": "File cap for this scan (default 4000)."},
                "max_seconds": {"type": "number", "exclusiveMinimum": 0, "description": "Time cap in seconds (default 8)."},
            },
            ["project"],
        ),
        lambda grove, project, max_files=None, max_seconds=None: grove.scan(project, max_files, max_seconds),
        False,
    ),
    Tool(
        "grove_blueprint_get",
        "Read a project's blueprint items, paginated: what docs declare (declared), what the code appears to "
        "contain (actual: modules and symbol names) and what tests appear to prove (tests: test names). "
        "Optionally filter by layer and by a case-insensitive substring of title, body or path. "
        "Reads Grove's stored result of the last scan; it does not rescan." + LOCAL,
        _schema(
            {
                "project": _PROJECT,
                "layer": {"type": "string", "enum": ["declared", "actual", "tests"]},
                "query": {"type": "string", "description": "Substring to look for in title, body or source path."},
                "limit": _LIMIT,
                "offset": _OFFSET,
            },
            ["project"],
        ),
        lambda grove, project, layer=None, query=None, limit=None, offset=None: grove.blueprint_get(
            project, layer, query, limit, offset
        ),
        True,
    ),
    Tool(
        "grove_gaps",
        "List a project's gap findings, paginated, with counts per kind. Kinds: declared_untested (docs state it, "
        "no test name overlaps), declared_unseen (docs state it, no code name overlaps), actual_undocumented "
        "(module never mentioned in docs), map_untested (an ingested map marks it untested). Every finding is a "
        "token-overlap heuristic to be checked by reading the code, not a verdict. total counts stored findings; "
        "when a findings cap omitted candidates, complete is false and true_total / omitted / findings_cap say "
        "how many exist. Use after grove_scan or grove_ingest_map." + LOCAL,
        _schema(
            {
                "project": _PROJECT,
                "kind": {"type": "string", "description": "Only findings of this kind, e.g. declared_untested."},
                "limit": _LIMIT,
                "offset": _OFFSET,
            },
            ["project"],
        ),
        lambda grove, project, kind=None, limit=None, offset=None: grove.gaps(project, kind, limit, offset),
        True,
    ),
    Tool(
        "grove_ingest_map",
        "Ingest a markdown architecture map (for example a MAP.md) into a project. The file is only read, never "
        "modified. Its full text is stored as a knowledge document (key from the file name; a new revision each "
        "time), and blocks carrying the evidence labels documented / observed-in-code / untested seed declared "
        "items, actual items and map_untested findings. Use when a human or agent has written a map of the "
        "codebase. Re-ingesting replaces what the same map seeded before." + LOCAL,
        _schema(
            {"project": _PROJECT, "path": {"type": "string", "description": "Path to the markdown file on this machine."}},
            ["project", "path"],
        ),
        lambda grove, project, path: grove.ingest_map(project, path),
        False,
    ),
    Tool(
        "grove_knowledge_write",
        "Save a lasting note (a decision, a convention, a lesson) under a stable slug key. Writing an existing key "
        "adds a new revision; earlier revisions are kept and never overwritten. Give a project to scope the note "
        "to it, or omit project for a workspace-level note. Use for knowledge worth finding again in later "
        "sessions, not for scratch notes." + LOCAL,
        _schema(
            {
                "project": {**_PROJECT, "description": "Project name or id. Omit for a workspace-level note."},
                "key": {"type": "string", "description": "Stable slug: lower-case letters, digits, '.', '_' or '-'."},
                "title": {"type": "string"},
                "body": {"type": "string", "description": "The note itself, usually markdown."},
                "author": _AUTHOR,
            },
            ["key", "title", "body"],
        ),
        lambda grove, key, title, body, project=None, author=None: grove.knowledge_write(project, key, title, body, author),
        False,
    ),
    Tool(
        "grove_knowledge_get",
        "Fetch a knowledge document by key: the latest revision, or a given revision number. Keys are unique per "
        "project (and at workspace level); pass project when the same key exists in more than one project. "
        "Without project, a workspace-level document wins. By default a long body is cut to an excerpt of 4000 "
        "characters with a heading outline; excerpted, body_chars and more say so. Pass full=true for the whole "
        "body. Use after grove_knowledge_search to read a document." + LOCAL,
        _schema(
            {
                "key": {"type": "string"},
                "project": {**_PROJECT, "description": "Project name or id, to pick that project's document."},
                "revision": {"type": "integer", "minimum": 1, "description": "Revision number; latest if omitted."},
                "full": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return the whole body instead of an excerpt (default false).",
                },
            },
            ["key"],
        ),
        lambda grove, key, project=None, revision=None, full=False: grove.knowledge_get(key, project, revision, full),
        True,
    ),
    Tool(
        "grove_knowledge_search",
        "Full-text search (SQLite FTS5) over the titles and bodies of the latest revision of every knowledge "
        "document, including ingested maps. All words must match; end a word with * for a prefix match. Returns "
        "ranked hits with a snippet, paginated; fetch a full document with grove_knowledge_get. Use before "
        "starting work, to recall what is already known." + LOCAL,
        _schema(
            {
                "query": {"type": "string", "description": "Words to search for."},
                "project": {**_PROJECT, "description": "Only documents of this project."},
                "limit": _LIMIT,
                "offset": _OFFSET,
            },
            ["query"],
        ),
        lambda grove, query, project=None, limit=None, offset=None: grove.knowledge_search(query, project, limit, offset),
        True,
    ),
    Tool(
        "grove_work_create",
        "Create a local work item for a project, starting in status ready. issue_url is stored as plain text for "
        "reference and is never fetched or opened. Use to record a unit of work that should end in a reviewed "
        "change; Grove tracks it but does not implement it or open a pull request." + LOCAL,
        _schema(
            {
                "project": _PROJECT,
                "title": {"type": "string"},
                "issue_url": {"type": "string", "description": "Optional reference URL; stored, never fetched."},
                "plan": {"type": "string", "description": "Optional plan for the work."},
                "author": _AUTHOR,
            },
            ["project", "title"],
        ),
        lambda grove, project, title, issue_url=None, plan=None, author=None: grove.work_create(
            project, title, issue_url, plan, author
        ),
        False,
    ),
    Tool(
        "grove_work_list",
        "List a project's work items, paginated, optionally only those in one status "
        "(ready, in_progress, review, done, blocked). Use to see what is open." + LOCAL,
        _schema({"project": _PROJECT, "status": _STATUS, "limit": _LIMIT, "offset": _OFFSET}, ["project"]),
        lambda grove, project, status=None, limit=None, offset=None: grove.work_list(project, status, limit, offset),
        True,
    ),
    Tool(
        "grove_work_get",
        "Get one work item by id, with its plan and notes. Use before continuing a piece of work." + LOCAL,
        _schema({"id": {"type": "integer", "description": "Work item id."}}, ["id"]),
        lambda grove, id: grove.work_get(id),
        True,
    ),
    Tool(
        "grove_work_update",
        "Update a work item: any of status, plan, notes, title (at least one). Each given field replaces the "
        "stored value. Use to move work through ready -> in_progress -> review -> done (or blocked) and to keep "
        "the plan and notes current. This only updates Grove's local record." + LOCAL,
        _schema(
            {
                "id": {"type": "integer", "description": "Work item id."},
                "status": _STATUS,
                "plan": {"type": "string"},
                "notes": {"type": "string"},
                "title": {"type": "string"},
            },
            ["id"],
        ),
        lambda grove, id, status=None, plan=None, notes=None, title=None: grove.work_update(id, status, plan, notes, title),
        False,
    ),
    Tool(
        "grove_recommend_next",
        "Suggest one next step for a project by fixed priority, with a short rationale and the finding or work "
        "item ids behind it: map_untested findings first, then declared_untested findings whose words also appear "
        "in the code, then other declared_untested findings, then the oldest ready work item, then "
        "actual_undocumented findings. A deterministic heuristic; no model is called." + LOCAL,
        _schema({"project": _PROJECT}, ["project"]),
        lambda grove, project: grove.recommend_next(project),
        True,
    ),
)

TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}


def run(home: Any, operation: Callable[[Grove], Any]) -> dict[str, Any]:
    """Run one operation against a Grove home and wrap the outcome in the envelope."""
    try:
        with Grove(home) as grove:
            return ok(operation(grove))
    except GroveError as exc:
        return fail(exc.code, exc.message)
    except sqlite3.Error as exc:
        return fail("io", f"database error: {exc}")
    except OSError as exc:
        return fail("io", f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # the envelope is the contract; never let a traceback out instead
        return fail("internal", f"{type(exc).__name__}: {exc}")


def call_tool(home: Any, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Validate ``arguments`` against the tool's schema keys, run it, return the envelope."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return fail("not_found", f"unknown tool {name!r}")
    arguments = dict(arguments or {})
    properties = tool.schema["properties"]
    unknown = sorted(set(arguments) - set(properties))
    if unknown:
        return fail("invalid", f"{name}: unknown argument(s): {', '.join(unknown)}")
    missing = [key for key in tool.schema["required"] if arguments.get(key) is None]
    if missing:
        return fail("invalid", f"{name}: missing required argument(s): {', '.join(missing)}")
    arguments = {key: value for key, value in arguments.items() if value is not None}
    return run(home, lambda grove: tool.handler(grove, **arguments))
