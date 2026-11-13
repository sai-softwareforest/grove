"""The ``grove`` command line.

Every command prints one JSON envelope on stdout and exits 0 on success or 1
on error. ``--text`` prints a plain-text rendering instead. ``grove mcp``
serves the same operations over MCP stdio.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, NoReturn

from . import __version__
from .errors import GroveError, fail
from .service import FINDING_KINDS, Grove
from .tools import run


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """argparse, but usage errors become an ``invalid`` envelope and exit code 1."""

    def error(self, message: str) -> NoReturn:
        raise _UsageError(f"{message} (try `{self.prog} --help`)")


def _add_common(parser: argparse.ArgumentParser) -> None:
    # SUPPRESS keeps a value given before the subcommand from being reset by the subparser's default.
    parser.add_argument("--home", metavar="DIR", default=argparse.SUPPRESS, help="Grove data directory (overrides $GROVE_HOME)")
    parser.add_argument("--text", action="store_true", default=argparse.SUPPRESS, help="print plain text instead of JSON")


def _add_paging(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=None, help="page size (default 50, max 200)")
    parser.add_argument("--offset", type=int, default=None, help="items to skip (default 0)")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="grove",
        description="Grove: map a codebase, record a three-layer blueprint, search knowledge, track work items. "
        "Local and deterministic; scans are read-only.",
    )
    parser.add_argument("--version", action="version", version=f"grove {__version__}")
    _add_common(parser)
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", parser_class=_Parser)

    def command(parent: Any, name: str, help_text: str, handler: Callable[..., Any] | None = None) -> argparse.ArgumentParser:
        sub = parent.add_parser(name, help=help_text, description=help_text)
        _add_common(sub)
        if handler is not None:
            sub.set_defaults(handler=handler)
        return sub

    command(commands, "status", "show version, data directory, database path and project count", lambda g, a: g.status())

    project = command(commands, "project", "create, list and inspect projects")
    project_commands = project.add_subparsers(dest="subcommand", metavar="ACTION", parser_class=_Parser)
    sub = command(project_commands, "create", "register a codebase", lambda g, a: g.project_create(a.name, a.root))
    sub.add_argument("name", metavar="NAME")
    sub.add_argument("--root", required=True, metavar="PATH", help="root directory of the codebase")
    sub = command(project_commands, "list", "list projects", lambda g, a: g.project_list(a.limit, a.offset))
    _add_paging(sub)
    sub = command(project_commands, "get", "show one project by name or id", lambda g, a: g.project_get(a.name))
    sub.add_argument("name", metavar="NAME")

    sub = command(
        commands,
        "scan",
        "read-only scan of the project root; rebuilds the blueprint and gap findings",
        lambda g, a: g.scan(a.name, a.max_files, a.max_seconds, a.exclude),
    )
    sub.add_argument("name", metavar="NAME")
    sub.add_argument("--max-files", type=int, default=None, help="file cap (default 4000)")
    sub.add_argument("--max-seconds", type=float, default=None, help="time cap in seconds (default 8)")
    sub.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="PATTERN",
        help="gitignore-style pattern to keep out of the blueprint; repeat for several. Given once or more, it "
        "replaces the project's stored list (--exclude '' clears it); left out, the stored list applies",
    )

    sub = command(
        commands,
        "blueprint",
        "list blueprint items",
        lambda g, a: g.blueprint_get(a.name, a.layer, a.query, a.limit, a.offset),
    )
    sub.add_argument("name", metavar="NAME")
    sub.add_argument("--layer", choices=["declared", "actual", "tests"], default=None)
    sub.add_argument("--query", default=None, help="substring of title, body or path")
    _add_paging(sub)

    sub = command(commands, "gaps", "list gap findings (heuristic)", lambda g, a: g.gaps(a.name, a.kind, a.limit, a.offset))
    sub.add_argument("name", metavar="NAME")
    # The service checks the value, so both surfaces refuse a misspelt kind with the same message;
    # the usage line shows the kinds as argparse shows choices.
    sub.add_argument("--kind", default=None, metavar="{" + ",".join(FINDING_KINDS) + "}", help="only findings of this kind")
    _add_paging(sub)

    sub = command(
        commands, "ingest-map", "ingest a markdown map (read, never modified)", lambda g, a: g.ingest_map(a.name, a.path)
    )
    sub.add_argument("name", metavar="NAME")
    sub.add_argument("path", metavar="PATH")

    knowledge = command(commands, "knowledge", "write and read knowledge documents")
    knowledge_commands = knowledge.add_subparsers(dest="subcommand", metavar="ACTION", parser_class=_Parser)
    sub = command(knowledge_commands, "write", "write a new revision of a knowledge document", _knowledge_write)
    sub.add_argument("name", metavar="NAME", help="project name, or - for a workspace-level note")
    sub.add_argument("--key", required=True, help="stable slug")
    sub.add_argument("--title", required=True)
    sub.add_argument("--file", required=True, metavar="PATH", help="file holding the body")
    sub.add_argument("--author", default=None, metavar="NAME", help="who is writing (default: $GROVE_AUTHOR)")
    sub = command(
        knowledge_commands,
        "get",
        "print a knowledge document (latest revision by default)",
        lambda g, a: g.knowledge_get(a.key, a.project, a.revision, a.full),
    )
    sub.add_argument("key", metavar="KEY")
    sub.add_argument("--project", default=None, metavar="NAME", help="pick this project's document")
    sub.add_argument("--revision", type=int, default=None)
    sub.add_argument("--full", action="store_true", help="print the whole body, not the default excerpt")

    sub = command(
        commands,
        "search",
        "full-text search over knowledge; without QUERY, list every document",
        lambda g, a: g.knowledge_search(a.query, a.project, a.limit, a.offset),
    )
    sub.add_argument("query", metavar="QUERY", nargs="?", default=None, help="words to search for; omit to list documents")
    sub.add_argument("--project", default=None, metavar="NAME")
    _add_paging(sub)

    work = command(commands, "work", "create, list and update work items")
    work_commands = work.add_subparsers(dest="subcommand", metavar="ACTION", parser_class=_Parser)
    sub = command(
        work_commands,
        "create",
        "create a work item (status ready)",
        lambda g, a: g.work_create(a.name, a.title, a.issue, a.plan, a.author),
    )
    sub.add_argument("name", metavar="NAME")
    sub.add_argument("--title", required=True)
    sub.add_argument("--issue", default=None, metavar="URL", help="reference URL; stored, never fetched")
    sub.add_argument("--plan", default=None)
    sub.add_argument("--author", default=None, metavar="NAME", help="who is filing it (default: $GROVE_AUTHOR)")
    sub = command(work_commands, "list", "list work items", lambda g, a: g.work_list(a.name, a.status, a.limit, a.offset))
    sub.add_argument("name", metavar="NAME")
    sub.add_argument("--status", default=None)
    _add_paging(sub)
    sub = command(work_commands, "get", "show one work item", lambda g, a: g.work_get(a.id))
    sub.add_argument("id", metavar="ID", type=int)
    sub = command(
        work_commands,
        "update",
        "update status, plan, notes or title; add a note to the history",
        lambda g, a: g.work_update(a.id, a.status, a.plan, a.notes, a.title, a.note, a.author),
    )
    sub.add_argument("id", metavar="ID", type=int)
    sub.add_argument("--status", default=None)
    sub.add_argument("--plan", default=None)
    sub.add_argument("--notes", default=None, help="replaces the stored notes")
    sub.add_argument("--title", default=None)
    sub.add_argument("--note", default=None, metavar="TEXT", help="progress note appended to the history; erases nothing")
    sub.add_argument("--author", default=None, metavar="NAME", help="who is updating (default: $GROVE_AUTHOR)")

    sub = command(commands, "recommend", "suggest one next step (heuristic)", lambda g, a: g.recommend_next(a.name))
    sub.add_argument("name", metavar="NAME")

    command(commands, "mcp", "serve the Grove tools over MCP stdio")
    return parser


def _knowledge_write(grove: Grove, args: argparse.Namespace) -> Any:
    try:
        body = Path(args.file).expanduser().read_bytes().decode("utf-8", errors="replace")
    except FileNotFoundError as exc:
        raise GroveError("not_found", f"file {args.file!r} does not exist") from exc
    except OSError as exc:
        raise GroveError("io", f"cannot read {args.file!r}: {exc}") from exc
    project = None if args.name == "-" else args.name
    return grove.knowledge_write(project, args.key, args.title, body, args.author)


def render_text(envelope: dict[str, Any]) -> str:
    """A plain rendering for people. JSON remains the stable interface."""
    if not envelope["ok"]:
        return f"error [{envelope['error']['code']}]: {envelope['error']['message']}"
    lines: list[str] = []

    def one_line(value: Any) -> str:
        if isinstance(value, dict):
            label = value.get("summary") or value.get("title") or value.get("name") or value.get("key")
            head = [str(value[key]) for key in ("id", "layer", "kind", "status") if value.get(key) is not None]
            if label is not None:
                where = f" ({value['source_path']}:{value.get('source_line')})" if value.get("source_path") else ""
                return " ".join(head + [str(label)]) + where
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)

    def emit(value: Any, indent: int) -> None:
        pad = "  " * indent
        if isinstance(value, dict):
            for key, inner in value.items():
                if isinstance(inner, dict) and inner:
                    lines.append(f"{pad}{key}:")
                    emit(inner, indent + 1)
                elif isinstance(inner, list) and inner:
                    lines.append(f"{pad}{key}:")
                    for entry in inner:
                        lines.append(f"{pad}  - {one_line(entry)}")
                else:
                    text = "" if inner is None else inner if isinstance(inner, str) else json.dumps(inner)
                    if "\n" in str(text):
                        lines.append(f"{pad}{key}:")
                        lines.extend(f"{pad}  {line}" for line in str(text).splitlines())
                    else:
                        lines.append(f"{pad}{key}: {text}")
        else:
            lines.append(f"{pad}{one_line(value)}")

    emit(envelope["data"], 0)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    as_text = "--text" in argv

    def finish(envelope: dict[str, Any]) -> int:
        output = render_text(envelope) if as_text else json.dumps(envelope)
        try:
            sys.stdout.write(output + "\n")
            sys.stdout.flush()
        except BrokenPipeError:
            pass
        return 0 if envelope["ok"] else 1

    try:
        args = parser.parse_args(argv)
    except _UsageError as exc:
        return finish(fail("invalid", str(exc)))

    home = getattr(args, "home", None)
    if args.command == "mcp":
        # Imported here so every other command starts without loading the MCP SDK.
        from .mcp_server import serve

        return serve(home)

    handler = getattr(args, "handler", None)
    if handler is None:
        return finish(fail("invalid", "a command is required (try `grove --help`)"))
    return finish(run(home, lambda grove: handler(grove, args)))


if __name__ == "__main__":
    sys.exit(main())
