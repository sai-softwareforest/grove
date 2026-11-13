"""Grove's operations. The CLI and the MCP server are thin layers over this.

Every public method returns plain JSON-serialisable data or raises
:class:`GroveError`. Nothing here touches the network, and nothing here
writes outside the Grove data directory.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from . import __version__
from .db import connect, db_path, now_iso, resolve_home_source
from .errors import GroveError, page, page_args
from .gaps import compute_findings
from .mapdoc import map_title, parse_map
from .scan import DEFAULT_MAX_FILES, DEFAULT_MAX_SECONDS, MAX_LINE_CHARS, long_line_count, scan_tree

LAYERS = ("declared", "actual", "tests")
STATUSES = ("ready", "in_progress", "review", "done", "blocked")
SCAN_FINDING_KINDS = ("declared_untested", "declared_unseen", "actual_undocumented")
FINDING_KINDS = SCAN_FINDING_KINDS + ("map_untested",)
# Every action recommend_next can return, in priority order. The MCP tool
# description must name each one (tests/test_docs_contract.py).
RECOMMEND_ACTIONS = (
    "cover_untested_behaviour",
    "check_declared_claim",
    "start_work_item",
    "check_documented_limit",
    "document_module",
    "scan",
    "none",
)
_HOME_CHOSEN_BY = {
    "flag": "the --home flag",
    "env": "the GROVE_HOME environment variable",
    "default": "default, because neither --home nor GROVE_HOME was set",
}

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_TITLE_CHARS = 300
SAMPLE_SIZE = 5
EXCERPT_CHARS = 4000  # knowledge_get returns at most this much body unless full=True
MAX_OUTLINE_HEADINGS = 60
MAX_AUTHOR_CHARS = 64
AUTHOR_ENV = "GROVE_AUTHOR"

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_KEY = re.compile(r"^[a-z0-9][a-z0-9._-]{0,119}$")
_SLUG_JUNK = re.compile(r"[^a-z0-9._-]+")
_SEARCH_TERM = re.compile(r"\w+\*?", re.UNICODE)
_MD_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_MD_FENCE = re.compile(r"^\s*(```|~~~)")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _text(value: Any, name: str, *, required: bool = True, max_chars: int | None = None, strip: bool = True) -> str | None:
    if value is None:
        if required:
            raise GroveError("invalid", f"{name} is required")
        return None
    if not isinstance(value, str):
        raise GroveError("invalid", f"{name} must be a string")
    if strip:
        value = value.strip()
    if required and not value:
        raise GroveError("invalid", f"{name} must not be empty")
    if max_chars is not None and len(value) > max_chars:
        raise GroveError("invalid", f"{name} is longer than {max_chars} characters")
    if len(value.encode("utf-8", errors="replace")) > MAX_TEXT_BYTES:
        raise GroveError("invalid", f"{name} is larger than {MAX_TEXT_BYTES} bytes")
    return value


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        raise GroveError("invalid", f"{name} must be an integer")
    return value


def _author(value: Any) -> str | None:
    """The explicit author if given, else $GROVE_AUTHOR, else None. Never invented."""
    source = "author"
    if value is None or (isinstance(value, str) and not value.strip()):
        value = os.environ.get(AUTHOR_ENV)
        source = AUTHOR_ENV
        if value is None or not value.strip():
            return None
    author = _text(value, source, max_chars=MAX_AUTHOR_CHARS)
    if _CONTROL.search(author):
        raise GroveError("invalid", f"{source} must be a short name on one line")
    return author


def _excerpt(body: str, limit: int) -> str:
    """The first ``limit`` characters, cut back to a line break when one is near."""
    if len(body) <= limit:
        return body
    cut = body.rfind("\n", 0, limit)
    return body[:cut] if cut >= limit // 2 else body[:limit]


def _outline(body: str) -> tuple[list[dict[str, Any]], int]:
    """Markdown headings outside code fences: ([{level, title, line}], total count)."""
    headings: list[dict[str, Any]] = []
    total = 0
    in_fence = False
    for index, line in enumerate(body.splitlines()):
        if _MD_FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _MD_HEADING.match(line)
        if match and match.group(2):
            total += 1
            if len(headings) < MAX_OUTLINE_HEADINGS:
                headings.append({"level": len(match.group(1)), "title": match.group(2)[:200], "line": index + 1})
    return headings, total


def slugify(text: str) -> str:
    slug = _SLUG_JUNK.sub("-", text.lower()).strip("-._")
    return slug[:120] or "document"


class Grove:
    """One Grove data directory. Not thread-safe: use one instance per thread."""

    def __init__(self, home: str | os.PathLike[str] | None = None) -> None:
        self.home, self.home_source = resolve_home_source(home)
        self._conn: sqlite3.Connection | None = None

    # -- plumbing ---------------------------------------------------------

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = connect(self.home)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Grove":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _write(self):
        return _Transaction(self.conn)

    # -- rows -------------------------------------------------------------

    @staticmethod
    def _project_row(row: sqlite3.Row) -> dict[str, Any]:
        last_scan = json.loads(row["last_scan"]) if row["last_scan"] else None
        return {
            "id": row["id"],
            "name": row["name"],
            "root_path": row["root_path"],
            "created_at": row["created_at"],
            "last_scanned_at": row["last_scanned_at"],
            "caps_hit": (last_scan or {}).get("caps", {}).get("hit", []),
            "cap_warnings": (last_scan or {}).get("warnings", []),
            "last_scan": last_scan,
            "findings_cap": Grove._cap_info(row),
        }

    @staticmethod
    def _cap_info(row: sqlite3.Row) -> dict[str, Any]:
        """What the findings caps left out at the last gap pass, from a projects row.

        ``applied`` is true when at least one finding was dropped by a cap; then the
        stored findings are not the full set, and ``omitted`` says how many are missing.
        """
        kinds: dict[str, Any] = json.loads(row["findings_cap"]) if row["findings_cap"] else {}
        omitted = sum(entry.get("omitted", 0) for entry in kinds.values())
        capped = [
            f"{kind}: {entry['stored']} of {entry['candidates']} stored (cap {entry['cap']}, {entry['omitted']} omitted)"
            for kind, entry in sorted(kinds.items())
            if entry.get("omitted")
        ]
        return {
            "applied": omitted > 0,
            "omitted": omitted,
            "kinds": kinds,
            "note": (
                "A findings cap was applied; stored counts and totals do not include the omitted candidates. "
                + "; ".join(capped)
            )
            if capped
            else None,
        }

    @staticmethod
    def _item_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "layer": row["layer"],
            "title": row["title"],
            "body": row["body"],
            "source_path": row["source_path"],
            "source_line": row["source_line"],
            "origin": row["origin"],
            "extra": json.loads(row["extra"]) if row["extra"] else {},
        }

    @staticmethod
    def _finding_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "summary": row["summary"],
            "evidence": json.loads(row["evidence"]) if row["evidence"] else {},
            "confidence": row["confidence"],
            "origin": row["origin"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _knowledge_row(row: sqlite3.Row, *, with_body: bool = True) -> dict[str, Any]:
        data = {
            "id": row["id"],
            "project": row["project"],
            "project_id": row["project_id"],
            "key": row["key"],
            "title": row["title"],
            "revision": row["revision"],
            "created_at": row["created_at"],
            "author": row["author"],
        }
        if with_body:
            data["body"] = row["body"]
        return data

    @staticmethod
    def _work_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "project": row["project"],
            "project_id": row["project_id"],
            "title": row["title"],
            "issue_url": row["issue_url"],
            "status": row["status"],
            "plan": row["plan"],
            "notes": row["notes"],
            "author": row["author"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _project(self, ref: Any) -> sqlite3.Row:
        """Resolve a project by name, or by numeric id."""
        if isinstance(ref, bool) or ref is None or ref == "":
            raise GroveError("invalid", "project is required (a project name or id)")
        row = None
        if isinstance(ref, int):
            row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (ref,)).fetchone()
        elif isinstance(ref, str):
            ref = ref.strip()
            row = self.conn.execute("SELECT * FROM projects WHERE name = ?", (ref,)).fetchone()
            if row is None and ref.isdigit():
                row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (int(ref),)).fetchone()
        else:
            raise GroveError("invalid", "project must be a project name or id")
        if row is None:
            raise GroveError("not_found", f"no project named or numbered {ref!r}; see the project list")
        return row

    # -- status and projects ----------------------------------------------

    def status(self) -> dict[str, Any]:
        count = self.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        hint = None
        if count == 0:
            hint = (
                "No projects are registered in this data directory. If you expected existing work, this is "
                f"probably the wrong directory: it was chosen by {_HOME_CHOSEN_BY[self.home_source]}. "
                "Set GROVE_HOME (or pass --home) to the directory that holds your grove.db, "
                "the same one for every agent on this machine."
            )
        return {
            "name": "grove",
            "version": __version__,
            "data_dir": str(self.home),
            "db_path": str(db_path(self.home)),
            "home_source": self.home_source,
            "project_count": count,
            "hint": hint,
        }

    def project_create(self, name: Any, root_path: Any) -> dict[str, Any]:
        name = _text(name, "name")
        root_text = _text(root_path, "root_path")
        if not _NAME.match(name) or name.isdigit():
            raise GroveError(
                "invalid",
                "name must be 1-100 characters of letters, digits, '.', '_' or '-', "
                "start with a letter or digit, and not be only digits",
            )
        root = Path(root_text).expanduser()
        try:
            root = root.resolve()
            is_dir = root.is_dir()
        except OSError as exc:
            raise GroveError("io", f"cannot inspect root_path {root_text!r}: {exc}") from exc
        if not is_dir:
            raise GroveError("invalid", f"root_path {str(root)!r} is not an existing directory")
        with self._write():
            if self.conn.execute("SELECT 1 FROM projects WHERE name = ?", (name,)).fetchone():
                raise GroveError("invalid", f"a project named {name!r} already exists")
            cursor = self.conn.execute(
                "INSERT INTO projects (name, root_path, created_at) VALUES (?, ?, ?)",
                (name, str(root), now_iso()),
            )
            project_id = cursor.lastrowid
        return self._project_row(self._project(project_id))

    def project_list(self, limit: Any = None, offset: Any = None) -> dict[str, Any]:
        limit, offset = page_args(limit, offset)
        total = self.conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        rows = self.conn.execute("SELECT * FROM projects ORDER BY name LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return page([self._project_row(row) for row in rows], total, offset, limit)

    def project_get(self, project: Any) -> dict[str, Any]:
        row = self._project(project)
        data = self._project_row(row)
        data["counts"] = self._counts(row["id"])
        data["counts"]["findings_omitted"] = {
            kind: entry.get("omitted", 0) for kind, entry in data["findings_cap"]["kinds"].items()
        }
        return data

    def _counts(self, project_id: int) -> dict[str, Any]:
        items = {layer: 0 for layer in LAYERS}
        for row in self.conn.execute(
            "SELECT layer, COUNT(*) AS n FROM blueprint_items WHERE project_id = ? GROUP BY layer", (project_id,)
        ):
            items[row["layer"]] = row["n"]
        work = {status: 0 for status in STATUSES}
        for row in self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM work_items WHERE project_id = ? GROUP BY status", (project_id,)
        ):
            work[row["status"]] = row["n"]
        return {"items": items, "findings": self._finding_counts(project_id), "work_items": work}

    def _finding_counts(self, project_id: int) -> dict[str, int]:
        counts = {kind: 0 for kind in FINDING_KINDS}
        for row in self.conn.execute(
            "SELECT kind, COUNT(*) AS n FROM findings WHERE project_id = ? GROUP BY kind", (project_id,)
        ):
            counts[row["kind"]] = row["n"]
        return counts

    # -- scan and gaps ----------------------------------------------------

    def scan(self, project: Any, max_files: Any = None, max_seconds: Any = None) -> dict[str, Any]:
        row = self._project(project)
        if max_files is None:
            max_files = DEFAULT_MAX_FILES
        max_files = _integer(max_files, "max_files")
        if max_files < 1:
            raise GroveError("invalid", "max_files must be at least 1")
        if max_seconds is None:
            max_seconds = DEFAULT_MAX_SECONDS
        if isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or not max_seconds > 0:
            raise GroveError("invalid", "max_seconds must be a number greater than 0")
        root = row["root_path"]
        if not os.path.isdir(root):
            raise GroveError("io", f"project root {root!r} is not a readable directory any more")

        try:
            result = scan_tree(root, max_files=max_files, max_seconds=float(max_seconds))
        except OSError as exc:
            raise GroveError("io", f"scan of {root!r} failed: {exc}") from exc

        scanned_at = now_iso()
        summary = result.summary()
        with self._write():
            self.conn.execute("DELETE FROM blueprint_items WHERE project_id = ? AND origin = 'scan'", (row["id"],))
            self.conn.executemany(
                "INSERT INTO blueprint_items (project_id, layer, title, body, source_path, source_line, origin, extra) "
                "VALUES (?, ?, ?, ?, ?, ?, 'scan', ?)",
                (
                    (
                        row["id"],
                        item.layer,
                        item.title,
                        item.body,
                        item.source_path,
                        item.source_line,
                        json.dumps(item.extra, sort_keys=True),
                    )
                    for item in result.items
                ),
            )
            result.items.clear()  # the rows are stored; free them before the gap pass
            self.conn.execute(
                "UPDATE projects SET last_scanned_at = ?, last_scan = ? WHERE id = ?",
                (scanned_at, json.dumps(summary, sort_keys=True), row["id"]),
            )
            notes = self._recompute_findings(row["id"])

        counts = self._counts(row["id"])
        return {
            "project": row["name"],
            "root_path": root,
            "scanned_at": scanned_at,
            "items": counts["items"],
            "findings": counts["findings"],
            "findings_cap": self._cap_info(self._project(row["id"])),
            "caps": summary["caps"],
            "warnings": summary["warnings"],
            "skipped_files": summary["skipped_files"],
            "long_lines": summary["long_lines"],
            "changelog_files": summary["changelog_files"],
            "files_seen": summary["files_seen"],
            "files_read": summary["files_read"],
            "elapsed_seconds": summary["elapsed_seconds"],
            "gap_notes": notes,
            "sample_findings": self._sample_findings(row["id"]),
            "more": "page every finding with the gaps operation (grove_gaps / `grove gaps NAME`)",
        }

    def _recompute_findings(self, project_id: int) -> dict[str, Any]:
        """Replace the project's scan-derived findings. Call inside a write transaction."""
        self.conn.execute("DELETE FROM findings WHERE project_id = ? AND origin = 'scan'", (project_id,))
        scanned = self.conn.execute("SELECT last_scanned_at FROM projects WHERE id = ?", (project_id,)).fetchone()[0]
        if not scanned:
            # Without a scan there are no tests or actual layers to compare with,
            # and every map statement would be reported as a gap.
            self.conn.execute("UPDATE projects SET findings_cap = NULL WHERE id = ?", (project_id,))
            return {"skipped": "project has not been scanned yet, so gap findings were not computed"}

        def read_items(layer: str | None) -> Iterator[dict[str, Any]]:
            sql = "SELECT * FROM blueprint_items WHERE project_id = ?"
            params: list[Any] = [project_id]
            if layer is not None:
                sql += " AND layer = ?"
                params.append(layer)
            for item in self.conn.execute(sql + " ORDER BY id", params):
                yield self._item_row(item)

        findings, notes = compute_findings(read_items)
        created = now_iso()
        self.conn.executemany(
            "INSERT INTO findings (project_id, kind, summary, evidence, confidence, origin, created_at) "
            "VALUES (?, ?, ?, ?, 'heuristic', 'scan', ?)",
            (
                (project_id, finding["kind"], finding["summary"], json.dumps(finding["evidence"], sort_keys=True), created)
                for finding in findings
            ),
        )
        self.conn.execute(
            "UPDATE projects SET findings_cap = ? WHERE id = ?",
            (json.dumps(notes.get("caps", {}), sort_keys=True), project_id),
        )
        return notes

    def _sample_findings(self, project_id: int) -> list[dict[str, Any]]:
        """Up to SAMPLE_SIZE findings, spread across kinds in priority order."""
        sample: list[dict[str, Any]] = []
        per_kind = {
            kind: self.conn.execute(
                "SELECT * FROM findings WHERE project_id = ? AND kind = ? ORDER BY id LIMIT ?",
                (project_id, kind, SAMPLE_SIZE),
            ).fetchall()
            for kind in ("map_untested",) + SCAN_FINDING_KINDS
        }
        depth = 0
        while len(sample) < SAMPLE_SIZE and any(len(rows) > depth for rows in per_kind.values()):
            for rows in per_kind.values():
                if len(rows) > depth and len(sample) < SAMPLE_SIZE:
                    sample.append(self._finding_row(rows[depth]))
            depth += 1
        return sample

    def blueprint_get(
        self, project: Any, layer: Any = None, query: Any = None, limit: Any = None, offset: Any = None
    ) -> dict[str, Any]:
        row = self._project(project)
        limit, offset = page_args(limit, offset)
        where = ["project_id = ?"]
        params: list[Any] = [row["id"]]
        if layer is not None:
            if layer not in LAYERS:
                raise GroveError("invalid", f"layer must be one of {', '.join(LAYERS)}")
            where.append("layer = ?")
            params.append(layer)
        query = _text(query, "query", required=False, max_chars=200)
        if query:
            like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where.append("(title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\' OR source_path LIKE ? ESCAPE '\\')")
            params.extend([like, like, like])
        clause = " AND ".join(where)
        total = self.conn.execute(f"SELECT COUNT(*) FROM blueprint_items WHERE {clause}", params).fetchone()[0]
        rows = self.conn.execute(
            f"SELECT * FROM blueprint_items WHERE {clause} ORDER BY id LIMIT ? OFFSET ?", [*params, limit, offset]
        ).fetchall()
        return page(
            [self._item_row(item) for item in rows],
            total,
            offset,
            limit,
            project=row["name"],
            last_scanned_at=row["last_scanned_at"],
        )

    def gaps(self, project: Any, kind: Any = None, limit: Any = None, offset: Any = None) -> dict[str, Any]:
        row = self._project(project)
        limit, offset = page_args(limit, offset)
        where = ["project_id = ?"]
        params: list[Any] = [row["id"]]
        kind = _text(kind, "kind", required=False, max_chars=60)
        if kind:
            where.append("kind = ?")
            params.append(kind)
        clause = " AND ".join(where)
        total = self.conn.execute(f"SELECT COUNT(*) FROM findings WHERE {clause}", params).fetchone()[0]
        rows = self.conn.execute(
            f"SELECT * FROM findings WHERE {clause} ORDER BY id LIMIT ? OFFSET ?", [*params, limit, offset]
        ).fetchall()
        cap = self._cap_info(row)
        if kind:
            omitted = cap["kinds"].get(kind, {}).get("omitted", 0)
        else:
            omitted = cap["omitted"]
        return page(
            [self._finding_row(finding) for finding in rows],
            total,
            offset,
            limit,
            project=row["name"],
            counts=self._finding_counts(row["id"]),
            confidence="heuristic",
            last_scanned_at=row["last_scanned_at"],
            # ``total`` counts stored findings (what can be paged). When a cap
            # dropped candidates, true_total includes them and complete is false.
            complete=omitted == 0,
            omitted=omitted,
            true_total=total + omitted,
            findings_cap=cap,
        )

    # -- map ingest -------------------------------------------------------

    def ingest_map(self, project: Any, path: Any) -> dict[str, Any]:
        row = self._project(project)
        path_text = _text(path, "path")
        map_path = Path(path_text).expanduser()
        try:
            map_path = map_path.resolve()
            if not map_path.exists():
                raise GroveError("not_found", f"map file {str(map_path)!r} does not exist")
            if not map_path.is_file():
                raise GroveError("invalid", f"map path {str(map_path)!r} is not a file")
            if map_path.stat().st_size > MAX_TEXT_BYTES:
                raise GroveError("invalid", f"map file is larger than {MAX_TEXT_BYTES} bytes")
            text = map_path.read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            raise GroveError("io", f"cannot read map file {str(map_path)!r}: {exc}") from exc
        if not text.strip():
            raise GroveError("invalid", f"map file {str(map_path)!r} is empty")

        key = slugify(map_path.stem)
        readable = text.lstrip("\ufeff")  # a byte order mark would hide the first heading from the parser
        title = map_title(readable, fallback=map_path.name)
        blocks = parse_map(readable)
        long_lines = long_line_count(readable)
        author = _author(None)  # $GROVE_AUTHOR, if set
        source = str(map_path)
        seeded = {"declared": 0, "actual": 0, "map_untested": 0}

        with self._write():
            document = self._knowledge_insert(row["id"], key, title, text, author)
            self.conn.execute(
                "DELETE FROM blueprint_items WHERE project_id = ? AND origin = 'map' AND origin_ref = ?", (row["id"], key)
            )
            self.conn.execute(
                "DELETE FROM findings WHERE project_id = ? AND origin = 'map' AND origin_ref = ?", (row["id"], key)
            )
            created = now_iso()
            for block in blocks:
                extra = json.dumps(
                    {"kind": "map_block", "heading": block.heading, "labels": block.labels, "knowledge_key": key},
                    sort_keys=True,
                )
                item_ids: list[int] = []
                for label, layer in (("documented", "declared"), ("observed-in-code", "actual")):
                    if label not in block.labels:
                        continue
                    cursor = self.conn.execute(
                        "INSERT INTO blueprint_items "
                        "(project_id, layer, title, body, source_path, source_line, origin, origin_ref, extra) "
                        "VALUES (?, ?, ?, ?, ?, ?, 'map', ?, ?)",
                        (row["id"], layer, block.title, block.body, source, block.line, key, extra),
                    )
                    item_ids.append(cursor.lastrowid)
                    seeded[layer] += 1
                if "untested" in block.labels:
                    evidence = {
                        "item_ids": item_ids,
                        "source_path": source,
                        "source_line": block.line,
                        "heading": block.heading,
                        "labels": block.labels,
                        "text": block.body,
                        "knowledge_key": key,
                    }
                    self.conn.execute(
                        "INSERT INTO findings (project_id, kind, summary, evidence, confidence, origin, origin_ref, created_at) "
                        "VALUES (?, 'map_untested', ?, ?, 'heuristic', 'map', ?, ?)",
                        (
                            row["id"],
                            f"Map marks this as untested: \"{block.title}\"",
                            json.dumps(evidence, sort_keys=True),
                            key,
                            created,
                        ),
                    )
                    seeded["map_untested"] += 1
            notes = self._recompute_findings(row["id"])

        return {
            "project": row["name"],
            "path": source,
            "knowledge": {"key": key, "title": title, "revision": document["revision"], "id": document["id"]},
            "labelled_blocks": len(blocks),
            "long_lines": {"max_line_chars": MAX_LINE_CHARS, "lines": long_lines},
            "seeded": seeded,
            "findings": self._finding_counts(row["id"]),
            "gap_notes": notes,
            "sample_findings": self._sample_findings(row["id"]),
        }

    # -- knowledge --------------------------------------------------------

    def _knowledge_insert(
        self, project_id: int | None, key: str, title: str, body: str, author: str | None = None
    ) -> dict[str, Any]:
        """Insert the next revision. Call inside a write transaction."""
        current = self.conn.execute(
            "SELECT COALESCE(MAX(revision), 0) FROM knowledge WHERE key = ? AND COALESCE(project_id, 0) = ?",
            (key, project_id or 0),
        ).fetchone()[0]
        cursor = self.conn.execute(
            "INSERT INTO knowledge (project_id, key, title, body, revision, created_at, author) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, key, title, body, current + 1, now_iso(), author),
        )
        return {"id": cursor.lastrowid, "revision": current + 1}

    def _knowledge_fetch(self, knowledge_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            "SELECT k.*, p.name AS project FROM knowledge k LEFT JOIN projects p ON p.id = k.project_id WHERE k.id = ?",
            (knowledge_id,),
        ).fetchone()
        return self._knowledge_row(row)

    def knowledge_write(self, project: Any, key: Any, title: Any, body: Any, author: Any = None) -> dict[str, Any]:
        project_id = self._project(project)["id"] if project not in (None, "") else None
        key = _text(key, "key")
        if not _KEY.match(key):
            raise GroveError(
                "invalid",
                "key must be a slug: lower-case letters, digits, '.', '_' or '-', "
                "starting with a letter or digit, at most 120 characters",
            )
        title = _text(title, "title", max_chars=MAX_TITLE_CHARS)
        body = _text(body, "body", strip=False)
        if not body.strip():
            raise GroveError("invalid", "body must not be empty")
        author = _author(author)
        with self._write():
            document = self._knowledge_insert(project_id, key, title, body, author)
        return self._knowledge_fetch(document["id"])

    def knowledge_get(self, key: Any, project: Any = None, revision: Any = None, full: Any = False) -> dict[str, Any]:
        """A knowledge document. The body is an excerpt of at most EXCERPT_CHARS
        characters (with a heading outline) unless ``full`` is true."""
        key = _text(key, "key")
        if full is None:
            full = False
        if not isinstance(full, bool):
            raise GroveError("invalid", "full must be true or false")
        if project not in (None, ""):
            scope: int | None = self._project(project)["id"]
        else:
            scopes = [
                row[0]
                for row in self.conn.execute(
                    "SELECT DISTINCT COALESCE(project_id, 0) FROM knowledge WHERE key = ? ORDER BY 1", (key,)
                )
            ]
            if not scopes:
                raise GroveError("not_found", f"no knowledge document with key {key!r}")
            if 0 in scopes:
                scope = None  # a workspace-level document wins when no project is named
            elif len(scopes) == 1:
                scope = scopes[0]
            else:
                names = [
                    row[0]
                    for row in self.conn.execute(
                        f"SELECT name FROM projects WHERE id IN ({','.join('?' * len(scopes))}) ORDER BY name", scopes
                    )
                ]
                raise GroveError(
                    "invalid", f"key {key!r} exists in several projects ({', '.join(names)}); pass a project to choose one"
                )
        params: list[Any] = [key, scope or 0]
        sql = (
            "SELECT k.*, p.name AS project FROM knowledge k LEFT JOIN projects p ON p.id = k.project_id "
            "WHERE k.key = ? AND COALESCE(k.project_id, 0) = ?"
        )
        if revision is not None:
            revision = _integer(revision, "revision")
            sql += " AND k.revision = ?"
            params.append(revision)
        row = self.conn.execute(sql + " ORDER BY k.revision DESC LIMIT 1", params).fetchone()
        if row is None:
            suffix = f" at revision {revision}" if revision is not None else ""
            raise GroveError("not_found", f"no knowledge document with key {key!r}{suffix}")
        data = self._knowledge_row(row)
        data["latest_revision"] = self.conn.execute(
            "SELECT MAX(revision) FROM knowledge WHERE key = ? AND COALESCE(project_id, 0) = ?", (key, scope or 0)
        ).fetchone()[0]
        body = row["body"]
        data["body_chars"] = len(body)
        if full or len(body) <= EXCERPT_CHARS:
            data["excerpted"] = False
        else:
            data["body"] = _excerpt(body, EXCERPT_CHARS)
            headings, heading_count = _outline(body)
            data["excerpted"] = True
            data["excerpt_chars"] = len(data["body"])
            data["outline"] = headings
            data["outline_total"] = heading_count
            data["more"] = (
                f"body is the first {len(data['body'])} of {len(body)} characters; "
                "call again with full=true (CLI: --full) for the whole document"
            )
        return data

    def knowledge_search(
        self, query: Any = None, project: Any = None, limit: Any = None, offset: Any = None
    ) -> dict[str, Any]:
        """Search the latest revision of every document, or list them when no query is given."""
        limit, offset = page_args(limit, offset)
        if query is None:
            return self._knowledge_list(project, limit, offset)
        query = _text(query, "query", max_chars=500)
        terms = _SEARCH_TERM.findall(query)
        if not terms:
            raise GroveError("invalid", "query needs at least one word")
        # Each word is quoted, so FTS5 operators in user text cannot cause a syntax error.
        # Words are ANDed; a trailing * asks for a prefix match.
        match = " ".join(f'"{term[:-1]}"*' if term.endswith("*") else f'"{term}"' for term in terms)
        where = [
            "knowledge_fts MATCH ?",
            "k.revision = (SELECT MAX(k2.revision) FROM knowledge k2 "
            "WHERE k2.key = k.key AND COALESCE(k2.project_id, 0) = COALESCE(k.project_id, 0))",
        ]
        params: list[Any] = [match]
        if project not in (None, ""):
            where.append("k.project_id = ?")
            params.append(self._project(project)["id"])
        clause = " AND ".join(where)
        source = "knowledge_fts JOIN knowledge k ON k.id = knowledge_fts.rowid LEFT JOIN projects p ON p.id = k.project_id"
        try:
            total = self.conn.execute(f"SELECT COUNT(*) FROM {source} WHERE {clause}", params).fetchone()[0]
            rows = self.conn.execute(
                f"SELECT k.*, p.name AS project, snippet(knowledge_fts, -1, '[', ']', ' … ', 24) AS snippet "
                f"FROM {source} WHERE {clause} ORDER BY bm25(knowledge_fts), k.id LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise GroveError("invalid", f"search query could not be run: {exc}") from exc
        items = []
        for row in rows:
            item = self._knowledge_row(row, with_body=False)
            item["snippet"] = row["snippet"]
            items.append(item)
        return page(items, total, offset, limit, query=query)

    def _knowledge_list(self, project: Any, limit: int, offset: int) -> dict[str, Any]:
        """The latest revision of every document, newest first, without bodies."""
        where = [
            "k.revision = (SELECT MAX(k2.revision) FROM knowledge k2 "
            "WHERE k2.key = k.key AND COALESCE(k2.project_id, 0) = COALESCE(k.project_id, 0))"
        ]
        params: list[Any] = []
        if project not in (None, ""):
            where.append("k.project_id = ?")
            params.append(self._project(project)["id"])
        clause = " AND ".join(where)
        total = self.conn.execute(f"SELECT COUNT(*) FROM knowledge k WHERE {clause}", params).fetchone()[0]
        # length() counts characters as knowledge_get's body_chars does (up to a NUL, which notes do not contain).
        rows = self.conn.execute(
            "SELECT k.id, k.project_id, k.key, k.title, k.revision, k.created_at, k.author, "
            "length(k.body) AS body_chars, p.name AS project "
            f"FROM knowledge k LEFT JOIN projects p ON p.id = k.project_id WHERE {clause} "
            "ORDER BY k.created_at DESC, k.id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        items = []
        for row in rows:
            item = self._knowledge_row(row, with_body=False)
            item["body_chars"] = row["body_chars"]
            items.append(item)
        return page(items, total, offset, limit, query=None)

    # -- work items -------------------------------------------------------

    def _work(self, work_id: Any) -> sqlite3.Row:
        work_id = _integer(work_id, "id")
        row = self.conn.execute(
            "SELECT w.*, p.name AS project FROM work_items w JOIN projects p ON p.id = w.project_id WHERE w.id = ?",
            (work_id,),
        ).fetchone()
        if row is None:
            raise GroveError("not_found", f"no work item with id {work_id}")
        return row

    def work_create(
        self, project: Any, title: Any, issue_url: Any = None, plan: Any = None, author: Any = None
    ) -> dict[str, Any]:
        row = self._project(project)
        title = _text(title, "title", max_chars=MAX_TITLE_CHARS)
        issue_url = _text(issue_url, "issue_url", required=False, max_chars=2000) or None
        if issue_url and re.search(r"\s", issue_url):
            raise GroveError("invalid", "issue_url must not contain whitespace")
        plan = _text(plan, "plan", required=False, strip=False) or ""
        author = _author(author)
        stamp = now_iso()
        with self._write():
            cursor = self.conn.execute(
                "INSERT INTO work_items (project_id, title, issue_url, status, plan, notes, created_at, updated_at, author) "
                "VALUES (?, ?, ?, 'ready', ?, '', ?, ?, ?)",
                (row["id"], title, issue_url, plan, stamp, stamp, author),
            )
            work_id = cursor.lastrowid
        return self._work_row(self._work(work_id))

    def work_list(self, project: Any, status: Any = None, limit: Any = None, offset: Any = None) -> dict[str, Any]:
        row = self._project(project)
        limit, offset = page_args(limit, offset)
        where = ["w.project_id = ?"]
        params: list[Any] = [row["id"]]
        if status is not None:
            if status not in STATUSES:
                raise GroveError("invalid", f"status must be one of {', '.join(STATUSES)}")
            where.append("w.status = ?")
            params.append(status)
        clause = " AND ".join(where)
        total = self.conn.execute(f"SELECT COUNT(*) FROM work_items w WHERE {clause}", params).fetchone()[0]
        rows = self.conn.execute(
            f"SELECT w.*, p.name AS project FROM work_items w JOIN projects p ON p.id = w.project_id "
            f"WHERE {clause} ORDER BY w.id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return page([self._work_row(item) for item in rows], total, offset, limit, project=row["name"])

    def work_get(self, work_id: Any) -> dict[str, Any]:
        return self._work_row(self._work(work_id))

    def work_update(
        self, work_id: Any, status: Any = None, plan: Any = None, notes: Any = None, title: Any = None
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if status is not None:
            if status not in STATUSES:
                raise GroveError("invalid", f"status must be one of {', '.join(STATUSES)}")
            updates["status"] = status
        if plan is not None:
            updates["plan"] = _text(plan, "plan", required=False, strip=False)
        if notes is not None:
            updates["notes"] = _text(notes, "notes", required=False, strip=False)
        if title is not None:
            updates["title"] = _text(title, "title", max_chars=MAX_TITLE_CHARS)
        if not updates:
            raise GroveError("invalid", "nothing to update: pass at least one of status, plan, notes, title")
        with self._write():
            row = self._work(work_id)
            updates["updated_at"] = now_iso()
            assignments = ", ".join(f"{column} = ?" for column in updates)
            self.conn.execute(f"UPDATE work_items SET {assignments} WHERE id = ?", [*updates.values(), row["id"]])
        return self._work_row(self._work(work_id))

    # -- recommend --------------------------------------------------------

    def recommend_next(self, project: Any) -> dict[str, Any]:
        """One next step, chosen by fixed priority. No model is involved."""
        row = self._project(project)
        project_id = row["id"]

        def first_finding(kind: str, extra_sql: str = "") -> dict[str, Any] | None:
            found = self.conn.execute(
                f"SELECT * FROM findings WHERE project_id = ? AND kind = ? {extra_sql} ORDER BY id LIMIT 1",
                (project_id, kind),
            ).fetchone()
            return self._finding_row(found) if found else None

        def count(kind: str) -> int:
            return self.conn.execute(
                "SELECT COUNT(*) FROM findings WHERE project_id = ? AND kind = ?", (project_id, kind)
            ).fetchone()[0]

        def result(action: str, rationale: str, finding: dict | None = None, work: dict | None = None) -> dict[str, Any]:
            return {
                "project": row["name"],
                "action": action,
                "rationale": rationale,
                "finding_ids": [finding["id"]] if finding else [],
                "work_item_ids": [work["id"]] if work else [],
                "finding": finding,
                "work_item": work,
                "confidence": "heuristic",
            }

        finding = first_finding("map_untested")
        if finding:
            return result(
                "cover_untested_behaviour",
                f"An ingested map marks this behaviour as untested ({count('map_untested')} such finding(s)). "
                "A map entry is an explicit statement, so it ranks above token-overlap guesses.",
                finding,
            )

        behaviour = "AND COALESCE(json_extract(evidence, '$.class'), 'behaviour') = 'behaviour'"
        finding = first_finding("declared_untested", behaviour + " AND json_extract(evidence, '$.seen_in_actual') = 1")
        if finding:
            return result(
                "cover_untested_behaviour",
                "The docs declare this behaviour and matching names exist in the code, but no test name overlaps it. "
                f"There are {count('declared_untested')} declared_untested finding(s) in total.",
                finding,
            )

        finding = first_finding("declared_untested", behaviour)
        if finding:
            return result(
                "check_declared_claim",
                "The docs declare this, but no test name overlaps it and no code name does either; "
                "confirm whether it is a real behaviour before writing a test.",
                finding,
            )

        work = self.conn.execute(
            "SELECT w.*, p.name AS project FROM work_items w JOIN projects p ON p.id = w.project_id "
            "WHERE w.project_id = ? AND w.status = 'ready' ORDER BY w.id LIMIT 1",
            (project_id,),
        ).fetchone()
        if work:
            return result(
                "start_work_item",
                "No untested-behaviour findings are open, and this is the oldest work item in status ready.",
                work=self._work_row(work),
            )

        finding = first_finding("declared_untested", "AND json_extract(evidence, '$.class') = 'limit'")
        if finding:
            return result(
                "check_documented_limit",
                "No untested behaviour is left; this sentence documents a limit of the project and no test name "
                "overlaps it. Limits rank below behaviour because they describe what is not done.",
                finding,
            )

        finding = first_finding("actual_undocumented")
        if finding:
            return result(
                "document_module",
                "Nothing untested was found and no work item is ready; this module is not mentioned in the docs.",
                finding,
            )

        if not row["last_scanned_at"]:
            return result("scan", "The project has not been scanned yet; run a scan so there is something to weigh.")
        return result("none", "No findings and no ready work items. Nothing to recommend.")


class _Transaction:
    """BEGIN IMMEDIATE ... COMMIT, rolling back on any exception."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def __enter__(self) -> None:
        self.conn.execute("BEGIN IMMEDIATE")

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            self.conn.execute("ROLLBACK")
