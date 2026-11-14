"""`grove view`: the pages of ``export`` as a read-only web page on this machine.

This is the one module that starts a listener (R-INV-1 names the exception,
R-VIEW-2 and R-VIEW-5 bound it):

* it binds 127.0.0.1 and nothing else, and there is no option to change that;
* it answers only when the ``Host`` header names that address and port, so a
  page of another site cannot reach it through a DNS name of its own;
* it answers GET and HEAD, on a fixed list of routes; no request names a file,
  and none is ever opened;
* every request opens the database read-only (``mode=ro``) and closes it;
* every stored text is escaped before anything else is done with it, no page
  carries a script, and the response headers forbid one.

It makes no outgoing connection. There is no login: whoever can reach
127.0.0.1 on this machine can read the pages while the command runs.
"""

from __future__ import annotations

import html
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

from .db import resolve_home_source
from .errors import GroveError, fail, ok
from .export import (
    Block,
    Inline,
    Reader,
    anchor_id,
    file_page,
    findings_page,
    index_page,
    is_web_url,
    knowledge_page,
    requirements_page,
    slug,
    work_page,
)
from .scan import _FENCE, _LIST_MARKER, atx_heading  # stored Markdown is read by the scanner's line patterns
from .service import Grove

BIND = "127.0.0.1"
DEFAULT_PORT = 8765
SIDEBAR_LISTED = 100  # entries per sidebar list; the project page lists every one
SEARCH_LISTED = 20  # hits shown per kind and project; the true total is shown beside them
SEARCH_PROJECTS = 20  # projects searched when none is named
REQUEST_SECONDS = 15.0

HEADERS = (
    ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'"),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Frame-Options", "DENY"),
    ("Cache-Control", "no-store"),
)

_ROUTE = re.compile(
    r"/(?:p/(?P<project>[0-9]{1,15})(?:/(?P<page>requirements|findings)|/blueprint/(?P<slug>[a-z0-9-]{1,80}))?"
    r"|k/(?P<knowledge>[0-9]{1,15})|w/(?P<work>[0-9]{1,15})|(?P<search>search))?"
)
_PERCENT = re.compile(r"%([0-9A-Fa-f]{2})")
_LIST_ITEM = re.compile(_LIST_MARKER + r"(.*)$")
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\[\]\n]*)\]\(([^()\s]*)\)")
_STRONG = re.compile(r"\*\*([^*\n]+)\*\*")
_EMPHASIS = re.compile(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])|(?<!\w)_([^_\n]+)_(?!\w)")
# A link inside stored text is followed only to the web or to a plain relative
# address. Both are judged on the escaped text; anything else stays text.
_HREF_WEB = re.compile(r"https?://[^\s\"'<>`\\]+")
_HREF_RELATIVE = re.compile(r"(?!//)[A-Za-z0-9._~/#?=&;%+@,!-]+")

_STYLE = """
:root { color-scheme: light dark; --fg: #1d2420; --bg: #fbfbf8; --soft: #5d6a62; --line: #d9ded8; --link: #1f6b45; --code: #eef1ec; }
@media (prefers-color-scheme: dark) { :root { --fg: #e4e9e4; --bg: #151916; --soft: #9aa69e; --line: #2c342f; --link: #7fcf9f; --code: #1f2622; } }
* { box-sizing: border-box; }
body { margin: 0; font: 16px/1.55 system-ui, sans-serif; color: var(--fg); background: var(--bg); display: flex; flex-wrap: wrap; min-height: 100vh; }
nav { flex: 0 0 18rem; max-width: 100%; padding: 1rem; border-right: 1px solid var(--line); font-size: .9rem; overflow-wrap: anywhere; }
main { flex: 1 1 28rem; min-width: 0; max-width: 60rem; padding: 1rem 1.5rem 4rem; overflow-wrap: anywhere; }
a { color: var(--link); }
nav h2 { font-size: .8rem; text-transform: uppercase; letter-spacing: .05em; color: var(--soft); margin: 1.2rem 0 .3rem; }
nav ul { list-style: none; margin: 0; padding: 0; }
nav li { margin: .15rem 0; }
h1 { font-size: 1.6rem; line-height: 1.25; } h2 { font-size: 1.2rem; margin-top: 2rem; } h3, h4, h5, h6 { font-size: 1rem; }
code, pre { font: .9em/1.45 ui-monospace, monospace; background: var(--code); border-radius: 3px; }
code { padding: .1em .3em; } pre { padding: .8rem; overflow-x: auto; } pre code { padding: 0; background: none; }
hr { border: 0; border-top: 1px solid var(--line); margin: 1.5rem 0; }
form { display: flex; gap: .3rem; margin: .6rem 0; } input { font: inherit; min-width: 0; flex: 1; } button { font: inherit; }
.note { color: var(--soft); font-size: .85rem; }
"""


# --------------------------------------------------------------------------
# HTML


def _escape(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _emphasis(escaped: str) -> str:
    escaped = _STRONG.sub(r"<strong>\1</strong>", escaped)
    return _EMPHASIS.sub(lambda match: f"<em>{match.group(1) or match.group(2)}</em>", escaped)


def _inline_markdown(escaped: str) -> str:
    """Code, links and emphasis in one piece of text that is escaped already."""
    out: list[str] = []
    for index, piece in enumerate(_CODE_SPAN.split(escaped)):
        if index % 2:
            out.append(f"<code>{piece}</code>")
            continue
        position = 0
        for match in _LINK.finditer(piece):
            target = match.group(2)
            if not (_HREF_WEB.fullmatch(target) or _HREF_RELATIVE.fullmatch(target)):
                continue  # javascript:, data:, anything unusual: the text stays as it was written
            out.append(_emphasis(piece[position : match.start()]))
            out.append(f'<a href="{target}" rel="noreferrer noopener">{_emphasis(match.group(1))}</a>')
            position = match.end()
        out.append(_emphasis(piece[position:]))
    return "".join(out)


def render_markdown(text: str) -> str:
    """Stored text as HTML: everything is escaped first, then a small Markdown subset is applied.

    Headings, lists, emphasis, code and links; nothing else. A tag written in
    the text arrives as the characters of that tag. Headings start at level 3,
    under the page's own.
    """
    out: list[str] = []
    paragraph: list[str] = []
    code: list[str] | None = None
    list_tag: str | None = None

    def close() -> None:
        nonlocal list_tag
        if paragraph:
            out.append("<p>" + _inline_markdown("\n".join(paragraph)) + "</p>")
            paragraph.clear()
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    for line in _escape(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _FENCE.match(line):
            if code is None:
                close()
                code = []
            else:
                out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
                code = None
            continue
        if code is not None:
            code.append(line)
            continue
        if not line.strip():
            close()
            continue
        heading = atx_heading(line)
        if heading and heading[1]:
            close()
            level = min(heading[0] + 2, 6)
            out.append(f"<h{level}>{_inline_markdown(heading[1])}</h{level}>")
            continue
        item = _LIST_ITEM.match(line)
        if item:
            tag = "ol" if line.lstrip()[0].isdigit() else "ul"
            if paragraph or list_tag != tag:
                close()
                out.append(f"<{tag}>")
                list_tag = tag
            out.append(f"<li>{_inline_markdown(item.group(1))}</li>")
            continue
        if list_tag:
            close()
        paragraph.append(line)
    if code is not None:
        out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
    close()
    return "\n".join(out)


def _inline_html(parts: Inline, href: Callable[[Any], str | None]) -> str:
    out: list[str] = []
    for part in parts:
        if isinstance(part, str):
            out.append(_escape(part))
        elif part[0] == "code":
            out.append(f"<code>{_escape(part[1])}</code>")
        elif part[0] == "anchor":
            out.append(f'<a id="{_escape(part[1])}"></a>')
        else:
            target = href(part[2])
            if target is None:
                out.append(_escape(part[1]))
            else:
                outside = ' rel="noreferrer noopener"' if part[2][0] == "url" else ""
                out.append(f'<a href="{_escape(target)}"{outside}>{_escape(part[1])}</a>')
    return "".join(out)


def _plain(parts: Inline) -> str:
    return "".join(part if isinstance(part, str) else part[1] for part in parts if isinstance(part, str) or part[0] != "anchor")


def to_html(blocks: list[Block], href: Callable[[Any], str | None], *, ids: bool = True) -> str:
    """The blocks as HTML. A heading gets an id from its text unless ``ids`` is false (the sidebar)."""
    out: list[str] = []
    for block in blocks:
        kind = block[0]
        if kind == "h":
            name = f' id="{slug(_plain(block[2]))}"' if ids else ""
            out.append(f"<h{block[1]}{name}>{_inline_html(block[2], href)}</h{block[1]}>")
        elif kind == "p":
            out.append(f"<p>{_inline_html(block[1], href)}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{_inline_html(line, href)}</li>" for line in block[1]) + "</ul>")
        elif kind == "hr":
            out.append("<hr>")
        elif kind == "md":
            out.append(render_markdown(block[1]))
    return "\n".join(out)


def _route_href(target: Any) -> str | None:
    if target[0] == "route":
        return target[1]
    if target[0] == "url":
        return target[1] if is_web_url(target[1]) else None
    return None


def project_href(reader: Reader) -> Callable[[Any], str | None]:
    """Page targets of one project as routes of the view."""
    base = f"/p/{reader.id}"

    def href(target: Any) -> str | None:
        kind = target[0]
        if kind == "index":
            return base
        if kind == "requirements":
            return f"{base}/requirements" + (f"#{target[1]}" if target[1] else "")
        if kind == "findings":
            return f"{base}/findings" + (f"#{anchor_id(target[1])}" if target[1] else "")
        if kind == "file":
            entry = reader.file_by_stored.get(target[1])
            return f"{base}/blueprint/{entry['slug']}" if entry else None
        if kind == "knowledge":
            document = reader.knowledge_by_key.get(target[1])
            return f"/k/{document['id']}" if document else None
        if kind == "work":
            return f"/w/{target[1]}" if target[1] is not None else f"{base}#work-items"
        return _route_href(target)

    return href


def _capped(lines: list[Inline], total_note: str) -> list[Block]:
    blocks: list[Block] = [("ul", lines[:SIDEBAR_LISTED])] if lines else []
    if len(lines) > SIDEBAR_LISTED:
        blocks.append(("p", [f"{len(lines) - SIDEBAR_LISTED} more: {total_note}"]))
    return blocks


def _sidebar(reader: Reader | None, query: str = "") -> str:
    scope = f'<input type="hidden" name="p" value="{reader.id}">' if reader else ""
    out = [
        '<p><a href="/"><strong>Grove</strong></a> <span class="note">read-only view</span></p>',
        f'<form action="/search" method="get"><input name="q" value="{_escape(query)}" aria-label="Search">'
        f"{scope}<button>Search</button></form>",
    ]
    if reader is None:
        return "\n".join(out)
    href = project_href(reader)
    blocks: list[Block] = [
        ("h", 2, [("link", reader.name, ("index",))]),
        ("ul", [[("link", "Requirements", ("requirements", None))], [("link", "Findings", ("findings", None))]]),
        ("h", 2, ["Blueprint files"]),
        *_capped([[("link", entry["shown"], ("file", entry["stored"]))] for entry in reader.files], "see the project page"),
        ("h", 2, ["Knowledge"]),
        *_capped(
            [[("link", document["title"], ("knowledge", document["key"]))] for document in reader.knowledge],
            "see the project page",
        ),
        ("h", 2, ["Work items"]),
        *_capped(
            [[("link", f"#{item['id']} {item['title']}", ("work", item["id"])), f" ({item['status']})"] for item in reader.work],
            "see the project page",
        ),
    ]
    out.append(to_html(blocks, href, ids=False))  # the ids belong to the main column
    return "\n".join(out)


def _shell(title: str, sidebar: str, main: str) -> str:
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_escape(title)} · Grove</title><style>{_STYLE}</style></head>\n"
        f"<body><nav>{sidebar}</nav>\n<main>{main}</main></body></html>\n"
    )


def _message(status: int, text: str) -> str:
    blocks: list[Block] = [("h", 1, [str(status)]), ("p", [text]), ("p", [("link", "Start page", ("route", "/"))])]
    return _shell(str(status), _sidebar(None), to_html(blocks, _route_href))


# --------------------------------------------------------------------------
# Routes


def _query(raw: str) -> dict[str, str]:
    """The first value of each field of a query string. Form encoding, read as UTF-8."""
    fields: dict[str, str] = {}
    for pair in raw.split("&"):
        name, _, value = pair.partition("=")
        if name and name not in fields:
            data = _PERCENT.sub(lambda match: chr(int(match.group(1), 16)), value.replace("+", " "))
            fields[name] = data.encode("latin-1", errors="replace").decode("utf-8", errors="replace")
    return fields


def _start_page(grove: Grove) -> tuple[str, str, str]:
    projects = grove.conn.execute("SELECT id, name, last_scanned_at FROM projects ORDER BY name").fetchall()
    notes = grove.conn.execute(
        "SELECT k.id, k.key, k.title FROM knowledge k WHERE k.project_id IS NULL AND k.revision = "
        "(SELECT MAX(k2.revision) FROM knowledge k2 WHERE k2.key = k.key AND k2.project_id IS NULL) ORDER BY k.key"
    ).fetchall()
    blocks: list[Block] = [
        ("h", 1, ["Grove"]),
        ("p", ["A read-only view of this machine's Grove workshop. Nothing can be changed from here."]),
        ("h", 2, [f"Projects ({len(projects)})"]),
    ]
    if projects:
        blocks.append(
            (
                "ul",
                [
                    [
                        ("link", row["name"], ("route", f"/p/{row['id']}")),
                        f" (last scanned: {row['last_scanned_at'] or 'never'})",
                    ]
                    for row in projects
                ],
            )
        )
    else:
        blocks.append(("p", ["No projects are registered in this data directory."]))
    blocks.append(("h", 2, [f"Workspace notes ({len(notes)})"]))
    if notes:
        blocks.append(
            ("ul", [[("link", row["title"], ("route", f"/k/{row['id']}")), " (", ("code", row["key"]), ")"] for row in notes])
        )
    return "Grove", _sidebar(None), to_html(blocks, _route_href)


def _knowledge(grove: Grove, knowledge_id: int) -> tuple[str, str, str]:
    row = grove.conn.execute(
        "SELECT id, project_id, key, title, body, revision, created_at, author FROM knowledge WHERE id = ?", (knowledge_id,)
    ).fetchone()
    if row is None:
        raise GroveError("not_found", "no such knowledge document")
    latest = grove.conn.execute(
        "SELECT id, revision FROM knowledge WHERE key = ? AND COALESCE(project_id, 0) = ? ORDER BY revision DESC LIMIT 1",
        (row["key"], row["project_id"] or 0),
    ).fetchone()
    reader = Reader(grove, row["project_id"]) if row["project_id"] else None
    back = ("index",) if reader else ("route", "/")
    title, blocks = knowledge_page(dict(row), row["body"], latest["revision"], back)
    if latest["id"] != row["id"]:
        blocks.insert(2, ("p", ["This is an earlier revision. ", ("link", "Read the latest", ("route", f"/k/{latest['id']}")), "."]))
    return title, _sidebar(reader), to_html(blocks, project_href(reader) if reader else _route_href)


def _hits(shown: int, total: int) -> str:
    return f"{total} hit(s)" + (f", the first {shown} shown" if total > shown else "")


def _search(grove: Grove, fields: dict[str, str]) -> tuple[str, str, str]:
    query = fields.get("q", "").strip()
    scope = fields.get("p", "")
    reader = Reader(grove, int(scope)) if re.fullmatch(r"[0-9]{1,15}", scope) else None
    blocks: list[Block] = [("h", 1, ["Search"])]
    if not query:
        blocks.append(("p", ["Type words into the search field. Knowledge is searched by word; the blueprint and the findings by text."]))
        return "Search", _sidebar(reader), to_html(blocks, _route_href)
    blocks.append(("p", ["Results for ", ("code", query), f" in {'project ' + reader.name if reader else 'every project'}."]))

    def section(title: str, read: Callable[[], dict[str, Any]], line: Callable[[dict[str, Any]], Inline]) -> None:
        try:
            page = read()
        except GroveError as exc:
            if exc.code != "invalid":
                raise
            blocks.extend([("h", 2, [title]), ("p", [f"Not searched: {exc.message}."])])
            return
        if page["total"]:
            blocks.append(("h", 2, [f"{title}: {_hits(len(page['items']), page['total'])}"]))
            blocks.append(("ul", [line(item) for item in page["items"]]))

    before = len(blocks)
    section(
        "Knowledge",
        lambda: grove.knowledge_search(query, reader.id if reader else None, SEARCH_LISTED),
        lambda hit: [
            ("link", hit["title"], ("route", f"/k/{hit['id']}")),
            f" ({hit['project'] or 'workspace'}, ",
            ("code", hit["key"]),
            f") {hit['snippet']}",
        ],
    )
    if reader:
        readers = [reader]
    else:
        ids = [row["id"] for row in grove.conn.execute("SELECT id FROM projects ORDER BY name")]
        readers = [Reader(grove, project_id) for project_id in ids[:SEARCH_PROJECTS]]
        if len(ids) > SEARCH_PROJECTS:
            blocks.append(("p", [f"Only the first {SEARCH_PROJECTS} of {len(ids)} projects are searched; open a project to search it."]))
    for each in readers:
        href = project_href(each)

        def route(target: Any, label: str, href: Callable[[Any], str | None] = href) -> Any:
            found = href(target)
            return ("link", label, ("route", found)) if found else label

        section(
            f"Blueprint of {each.name}",
            lambda each=each: grove.blueprint_get(each.id, None, query, SEARCH_LISTED),
            lambda item, each=each, route=route: [
                route(("file", item["source_path"] or ""), each.shown(item["source_path"])),
                f" {item['layer']}: {item['title']}",
            ],
        )
        section(
            f"Findings of {each.name}",
            lambda each=each: grove.gaps(each.id, None, SEARCH_LISTED, None, query),
            lambda finding, route=route: [route(("findings", finding["key"]), finding["key"]), f" {finding['summary']}"],
        )
    if len(blocks) == before:
        blocks.append(("p", ["Nothing was found."]))
    return "Search", _sidebar(reader, query), to_html(blocks, _route_href)


def respond(home: Any, target: str) -> tuple[int, str]:
    """The status and the HTML for one request target (path and query). Opens the database read-only, once."""
    path, _, raw_query = target.partition("?")
    match = _ROUTE.fullmatch(path)
    if match is None:
        return 404, _message(404, "There is no such page.")
    try:
        with Grove(home, read_only=True) as grove:
            try:
                grove.conn  # opened here, so a database that cannot be read is not mistaken for a missing page
            except GroveError as exc:
                return 500, _message(500, exc.message)
            if match["search"]:
                title, sidebar, main = _search(grove, _query(raw_query))
            elif match["knowledge"]:
                title, sidebar, main = _knowledge(grove, int(match["knowledge"]))
            elif match["work"]:
                row = grove._work(int(match["work"]))
                reader = Reader(grove, row["project_id"])
                title, blocks = work_page(reader, Grove._work_row(row))
                sidebar, main = _sidebar(reader), to_html(blocks, project_href(reader))
            elif match["project"]:
                reader = Reader(grove, int(match["project"]))
                if match["slug"]:
                    entry = reader.file_by_slug(match["slug"])
                    if entry is None:
                        raise GroveError("not_found", "no such file page")
                    title, blocks = file_page(reader, entry)
                elif match["page"] == "requirements":
                    title, blocks = requirements_page(reader)
                elif match["page"] == "findings":
                    title, blocks = findings_page(reader)
                else:
                    title, blocks = index_page(reader)
                sidebar, main = _sidebar(reader), to_html(blocks, project_href(reader))
            else:
                title, sidebar, main = _start_page(grove)
    except GroveError as exc:
        if exc.code == "not_found":
            return 404, _message(404, "There is no such page.")
        return 500, _message(500, exc.message)
    return 200, _shell(title, sidebar, main)


# --------------------------------------------------------------------------
# The server


class _Handler(BaseHTTPRequestHandler):
    server_version = "grove"
    sys_version = ""
    timeout = REQUEST_SECONDS  # one request at a time: a client that sends nothing is dropped
    command = ""  # the standard library refuses an overlong request line before it sets this

    def _send(self, status: int, page: str, extra: tuple[tuple[str, str], ...] = ()) -> None:
        body = page.encode("utf-8", errors="replace")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in HEADERS + extra:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _host_ok(self) -> bool:
        hosts = self.headers.get_all("Host") or []
        port = self.server.server_address[1]
        return len(hosts) == 1 and hosts[0].strip().lower() in (f"{BIND}:{port}", f"localhost:{port}")

    def _answer(self) -> None:
        if not self._host_ok():
            # A page of another site that reaches this port through its own DNS name sends that name here.
            self._send(403, _message(403, "This view answers only to its own address on this machine."))
        elif self.command not in ("GET", "HEAD"):
            self._send(405, _message(405, "This view is read-only: GET and HEAD are the only methods."), (("Allow", "GET, HEAD"),))
        else:
            try:
                status, page = respond(self.server.grove_home, self.path)
            except Exception as exc:  # a bug must not end the server, and its details stay on this side
                sys.stderr.write(f"grove view: {type(exc).__name__}: {exc}\n")
                status, page = 500, _message(500, "Grove could not build this page.")
            self._send(status, page)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("do_"):  # every method is answered here, so an unknown one gets 405, not 501
            return self._answer
        raise AttributeError(name)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        # Requests the standard library refuses by itself (a malformed request line) get the same headers.
        self._send(code, _message(code, message or "The request could not be read."))

    def log_message(self, format: str, *args: Any) -> None:
        pass


class _Server(HTTPServer):
    grove_home: Any = None

    def handle_error(self, request: Any, client_address: Any) -> None:
        # A browser that closes the connection early, or stays silent until the timeout, is not an event.
        if not isinstance(sys.exception(), (ConnectionError, TimeoutError)):
            super().handle_error(request, client_address)


def open_server(home: Any, port: Any = DEFAULT_PORT) -> HTTPServer:
    """Bind 127.0.0.1 on ``port`` (0: any free port). Nothing is served until ``serve_forever``."""
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise GroveError("invalid", "port must be a number from 0 to 65535")
    try:
        server = _Server((BIND, port), _Handler)
    except OSError as exc:
        raise GroveError("io", f"cannot listen on {BIND}:{port}: {exc}; pass another --port") from exc
    server.grove_home = home
    return server


def serve(home: Any, project: Any, port: Any, announce: Callable[[dict[str, Any]], int]) -> int:
    """Run ``grove view`` until interrupted. ``announce`` prints one envelope: the URL, or the error."""
    if port is None:
        port = DEFAULT_PORT
    try:
        home = resolve_home_source(home)[0]
        path = "/"
        with Grove(home, read_only=True) as grove:  # a wrong data directory or name is said now, not in the browser
            grove.conn
            if project not in (None, ""):
                path = f"/p/{grove._project(project)['id']}"
        server = open_server(home, port)
    except GroveError as exc:
        return announce(fail(exc.code, exc.message))
    with server:
        announce(
            ok(
                {
                    "url": f"http://{BIND}:{server.server_address[1]}{path}",
                    "bound": BIND,
                    "port": server.server_address[1],
                    "read_only": True,
                    "stop": "Ctrl-C",
                    "note": "No login: any user of this machine can read these pages while this command runs.",
                }
            )
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0
