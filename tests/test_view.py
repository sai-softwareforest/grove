"""`grove view` (WO-39, R-VIEW-2, R-VIEW-5, R-VIEW-6): a read-only web page on 127.0.0.1.

Each test talks to a real server in this process, on a port the system picks.
"""

from __future__ import annotations

import http.client
import json
import re
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Iterator

import pytest

from conftest import REPO, tree_snapshot
from sf_grove import view
from sf_grove.cli import main
from sf_grove.db import connect_read_only
from sf_grove.errors import GroveError
from sf_grove.service import Grove

SCRIPT = "<script>alert(1)</script>"
IMAGE = '<img src=x onerror="alert(2)">'
BAD_LINK = "[x](javascript:alert(1))"
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'"


@pytest.fixture
def workshop(tiny: Grove, tmp_path: Path) -> Grove:
    """A project whose stored text is hostile wherever text can be stored."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / "README.md").write_text(f"# Proj {SCRIPT}\n\nR-DEMO-1: the parser accepts {IMAGE} input.\n")
    (root / "evil.py").write_text("def parse():\n    return 1\n")
    tiny.project_create("proj", str(root))
    tiny.scan("proj")
    tiny.scan("tiny")
    body = f"# Notes {SCRIPT}\n\n{SCRIPT}\n\n{IMAGE}\n\n{BAD_LINK} and [fine](https://example.org/a?b=1&c=2)\n\n- item *one*\n- `code {SCRIPT}`\n"
    tiny.knowledge_write("proj", "hostile", f"Hostile {SCRIPT}", body)
    tiny.knowledge_write("proj", "hostile", f"Hostile {SCRIPT}", body + "\nSecond revision.\n")
    tiny.knowledge_write(None, "shared", "Shared note", "For every project.\n")
    key = tiny.gaps("proj")["items"][0]["key"]
    item = tiny.work_create(
        "proj",
        f"Fix {IMAGE}",
        issue_url="javascript:alert(3)",
        plan=f"{SCRIPT} finding:{key} knowledge:hostile R-DEMO-1 https://example.org/pr/1 {BAD_LINK}",
    )
    tiny.work_update(item["id"], status="review", note=f"note {SCRIPT}", author="tester")
    tiny.close()
    return tiny


@pytest.fixture
def server(workshop: Grove, home: Path) -> Iterator[tuple[str, int]]:
    httpd = view.open_server(home, 0)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[0], httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(5)


def _request(server: tuple[str, int], path: str, method: str = "GET", host: str | None = None) -> tuple[int, dict[str, str], str]:
    connection = http.client.HTTPConnection(server[0], server[1], timeout=10)
    try:
        connection.putrequest(method, path, skip_host=True)
        connection.putheader("Host", host if host is not None else f"127.0.0.1:{server[1]}")
        connection.endheaders()
        response = connection.getresponse()
        return response.status, {name.lower(): value for name, value in response.getheaders()}, response.read().decode("utf-8")
    finally:
        connection.close()


def _ids(grove: Grove, home: Path) -> dict[str, int]:
    with Grove(home) as reopened:
        proj = reopened.project_get("proj")["id"]
        note = reopened.knowledge_get("hostile", "proj")["id"]
        work = reopened.work_list("proj")["items"][0]["id"]
    return {"proj": proj, "note": note, "work": work}


def _pages(grove: Grove, home: Path) -> list[str]:
    ids = _ids(grove, home)
    return [
        "/",
        f"/p/{ids['proj']}",
        f"/p/{ids['proj']}/requirements",
        f"/p/{ids['proj']}/findings",
        f"/p/{ids['proj']}/blueprint/readme-md",
        f"/k/{ids['note']}",
        f"/w/{ids['work']}",
        "/search?q=parser",
        f"/search?q=hostile&p={ids['proj']}",
    ]


# -- the listener ----------------------------------------------------------------


def test_the_server_binds_the_loopback_address_only(server: tuple[str, int]) -> None:
    assert server[0] == "127.0.0.1" == view.BIND
    source = (REPO / "src" / "sf_grove" / "view.py").read_text(encoding="utf-8")
    assert "0.0.0.0" not in source and '"::"' not in source and "--host" not in source
    # No other address of this machine answers on that port.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # no packet is sent; this only asks which address would be used
        address = probe.getsockname()[0]
    except OSError:
        address = "127.0.0.1"
    finally:
        probe.close()
    if not address.startswith("127."):
        with pytest.raises(OSError):
            socket.create_connection((address, server[1]), timeout=2).close()


def test_the_command_has_no_host_option_and_checks_the_port(home: Path, workshop: Grove, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--home", str(home), "view", "--host", "0.0.0.0"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid"
    assert main(["--home", str(home), "view", "--port", "70000"]) == 1
    assert "port must be a number from 0 to 65535" in json.loads(capsys.readouterr().out)["error"]["message"]
    assert main(["--home", str(home), "view", "nobody", "--port", "0"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "not_found"
    with pytest.raises(GroveError):
        view.open_server(home, True)


def test_the_command_prints_the_url_and_stops_on_an_interrupt(
    home: Path, workshop: Grove, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupted(self: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(view._Server, "serve_forever", interrupted)
    assert main(["--home", str(home), "view", "proj", "--port", "0"]) == 0
    data = json.loads(capsys.readouterr().out)["data"]
    assert re.fullmatch(r"http://127\.0\.0\.1:[0-9]+/p/[0-9]+", data["url"]) and data["url"].split(":")[2].startswith(str(data["port"]))
    assert data["bound"] == "127.0.0.1" and data["read_only"] is True and "No login" in data["note"]
    assert main(["--home", str(home), "view", "--port", "0"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["url"].endswith("/")


def test_a_port_in_use_is_an_error_envelope(server: tuple[str, int], home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--home", str(home), "view", "--port", str(server[1])]) == 1
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "io" and "--port" in error["message"]


# -- what it answers ----------------------------------------------------------------


def test_every_route_answers_with_the_security_headers(server: tuple[str, int], workshop: Grove, home: Path) -> None:
    for path in _pages(workshop, home):
        status, headers, body = _request(server, path)
        assert status == 200, path
        assert headers["content-security-policy"] == CSP, path
        assert headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "no-referrer"
        assert headers["x-frame-options"] == "DENY" and headers["content-type"] == "text/html; charset=utf-8"
        assert int(headers["content-length"]) == len(body.encode("utf-8")) and body.startswith("<!doctype html>")
        assert "python" not in headers.get("server", "").lower()
    for path, status in (("/nothing", 404), ("/", 403), ("/", 405)):
        got, headers, _ = _request(server, path, "POST" if status == 405 else "GET", "evil.example" if status == 403 else None)
        assert got == status and headers["content-security-policy"] == CSP and headers["x-frame-options"] == "DENY"


@pytest.mark.parametrize(
    "host", ["evil.example", "evil.example:{port}", "127.0.0.1", "127.0.0.1:1", "localhost.evil.example:{port}", "", "[::1]:{port}"]
)
def test_a_foreign_host_header_is_refused(server: tuple[str, int], host: str) -> None:
    status, _, body = _request(server, "/", host=host.format(port=server[1]))
    assert status == 403 and "Projects" not in body


def test_both_names_of_the_loopback_address_are_accepted(server: tuple[str, int]) -> None:
    for host in (f"127.0.0.1:{server[1]}", f"localhost:{server[1]}", f"LOCALHOST:{server[1]}"):
        assert _request(server, "/", host=host)[0] == 200
    # A request without any Host header, or with two, is refused like a foreign one.
    for lines in ("", f"Host: 127.0.0.1:{server[1]}\r\nHost: evil.example\r\n"):
        with socket.create_connection(server, timeout=10) as raw:
            raw.sendall(f"GET / HTTP/1.1\r\n{lines}\r\n".encode())
            assert raw.makefile("rb").readline().split()[1] == b"403"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE", "CONNECT", "BREW"])
def test_only_get_and_head_are_answered(server: tuple[str, int], method: str) -> None:
    status, headers, _ = _request(server, "/", method)
    assert status == 405 and headers["allow"] == "GET, HEAD"


def test_head_sends_the_headers_without_a_body(server: tuple[str, int]) -> None:
    status, headers, body = _request(server, "/", "HEAD")
    assert status == 200 and body == "" and int(headers["content-length"]) > 0


@pytest.mark.parametrize(
    "path",
    [
        "/k/../../etc/passwd",
        "/k/..%2f..%2fetc%2fpasswd",
        "/../../etc/passwd",
        "/etc/passwd",
        "/grove.db",
        "/static/style.css",
        "/k/abc",
        "/k/1e3",
        "/k/-1",
        "/k/",
        "/k/99999999999999999999999",
        "/w/abc",
        "/w/1/",
        "/p/abc",
        "/p/999999",
        "/p/1/blueprint/..",
        "/p/1/blueprint/README.md",
        "/p/1/blueprint/no-such-file",
        "/p/1/nothing",
        "/search/",
        "/k/999999",
        "/w/999999",
    ],
)
def test_unknown_and_path_like_requests_are_not_found(server: tuple[str, int], path: str) -> None:
    status, _, body = _request(server, path)
    assert status == 404 and "root:" not in body and "There is no such page." in body


def test_a_malformed_request_line_gets_an_error_with_the_headers(server: tuple[str, int]) -> None:
    with socket.create_connection(server, timeout=10) as raw:
        raw.sendall(b"GET\r\n\r\n")
        reply = raw.makefile("rb").read().decode()
    assert reply.split()[1] == "400" and CSP in reply
    with socket.create_connection(server, timeout=10) as raw:
        raw.sendall(b"GET /" + b"a" * 70000 + b" HTTP/1.1\r\n\r\n")
        reply = raw.makefile("rb").read().decode()
    assert reply.split()[1] == "414" and CSP in reply
    assert _request(server, "/")[0] == 200, "the server is still there"


# -- stored text is inert ---------------------------------------------------------------


def test_stored_text_is_rendered_inert_on_every_page(server: tuple[str, int], workshop: Grove, home: Path) -> None:
    seen_escaped = 0
    for path in _pages(workshop, home):
        _, _, body = _request(server, path)
        lowered = body.lower()
        assert "<script" not in lowered and "<img" not in lowered and "onerror=\"" not in lowered, path
        assert 'href="javascript' not in lowered and "href='javascript" not in lowered, path
        hrefs = re.findall(r'href="([^"]*)"', body)
        assert all(href.startswith(("/", "https://", "http://")) for href in hrefs), (path, hrefs)
        seen_escaped += body.count("&lt;script&gt;alert(1)&lt;/script&gt;")
    assert seen_escaped >= 6, "the hostile text is shown, as text"


def test_a_note_is_rendered_with_the_markdown_subset_and_nothing_else(server: tuple[str, int], workshop: Grove, home: Path) -> None:
    _, _, body = _request(server, f"/k/{_ids(workshop, home)['note']}")
    main_column = body.split("<main>", 1)[1]
    assert "<h3>Notes &lt;script&gt;alert(1)&lt;/script&gt;</h3>" in main_column
    assert "[x](javascript:alert(1))" in main_column, "a link that is neither web nor relative stays text"
    assert '<a href="https://example.org/a?b=1&amp;c=2" rel="noreferrer noopener">fine</a>' in main_column
    assert "<li>item <em>one</em></li>" in main_column
    assert "<li><code>code &lt;script&gt;alert(1)&lt;/script&gt;</code></li>" in main_column
    assert "Revision: 2 of 2" in main_column


def test_the_markdown_subset() -> None:
    render = view.render_markdown
    assert render("# T\n\ntext **bold** and _em_ and `a*b*`") == "<h3>T</h3>\n<p>text <strong>bold</strong> and <em>em</em> and <code>a*b*</code></p>"
    assert render("1. one\n2. two\n\n- x") == "<ol>\n<li>one</li>\n<li>two</li>\n</ol>\n<ul>\n<li>x</li>\n</ul>"
    assert render("```\n<b>&\n# not a heading\n```") == "<pre><code>&lt;b&gt;&amp;\n# not a heading</code></pre>"
    assert render("snake_case_name and 2*3*4") == "<p>snake_case_name and 2*3*4</p>"
    assert render("[rel](docs/a.md#x) [abs](/p/1)") == (
        '<p><a href="docs/a.md#x" rel="noreferrer noopener">rel</a> <a href="/p/1" rel="noreferrer noopener">abs</a></p>'
    )
    for target in (
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        "data:text/html,x",
        "vbscript:x",
        "//evil.example/x",
        "/\\evil.example",
        "\x01javascript:alert(1)",
        "java\tscript:alert(1)",
        "file:///etc/passwd",
        "mailto:a@b.example",
        'https://a.example/"onmouseover="x',
    ):
        html = render(f"[x]({target})")
        assert "<a " not in html or ('href="https://a.example/&quot;' in html), target
    assert "<img" not in render("![x](https://example.org/a.png)")
    hostile = render('<a href="javascript:x">y</a><iframe src=x></iframe><!-- c --><svg/onload=alert(1)>')
    assert "<a" not in hostile and "<iframe" not in hostile and "<svg" not in hostile and "<!--" not in hostile


def test_search_results_and_the_query_are_escaped(server: tuple[str, int], workshop: Grove, home: Path) -> None:
    status, _, body = _request(server, "/search?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E")
    assert status == 200 and "<script" not in body.lower()
    assert 'value="&lt;script&gt;alert(1)&lt;/script&gt;"' in body and "<code>&lt;script&gt;alert(1)&lt;/script&gt;</code>" in body
    status, _, body = _request(server, "/search?q=%22%3E%3Cimg+src%3Dx+onerror%3Dalert(1)%3E")
    assert status == 200 and "<img" not in body.lower() and 'value="&quot;&gt;&lt;img src=x onerror=alert(1)&gt;"' in body

    ids = _ids(workshop, home)
    _, _, body = _request(server, "/search?q=hostile")
    assert f'<a href="/k/{ids["note"]}">Hostile &lt;script&gt;alert(1)&lt;/script&gt;</a>' in body
    _, _, body = _request(server, f"/search?q=parser&p={ids['proj']}")
    assert f'<a href="/p/{ids["proj"]}/blueprint/readme-md">README.md</a>' in body
    assert f'href="/p/{ids["proj"]}/findings#' in body and "Blueprint of tiny" not in body
    _, _, body = _request(server, "/search?q=zzzznothing")
    assert "Nothing was found." in body
    _, _, body = _request(server, "/search?q=" + "x" * 300)
    assert "Not searched:" in body, "a query the search refuses is said, not an error page"
    assert _request(server, "/search")[0] == 200 and _request(server, "/search?q=%ZZ%")[0] == 200


# -- links between the pages --------------------------------------------------------------


def test_the_sidebar_and_the_cross_links(server: tuple[str, int], workshop: Grove, home: Path) -> None:
    ids = _ids(workshop, home)
    base = f"/p/{ids['proj']}"
    _, _, body = _request(server, base)
    sidebar = body.split("<nav>", 1)[1].split("</nav>", 1)[0]
    for link in (f"{base}/requirements", f"{base}/findings", f"{base}/blueprint/readme-md", f"/k/{ids['note']}", f"/w/{ids['work']}"):
        assert f'href="{link}"' in sidebar, link
    assert 'action="/search"' in sidebar and f'name="p" value="{ids["proj"]}"' in sidebar and " id=" not in sidebar

    _, _, work = _request(server, f"/w/{ids['work']}")
    assert f'<a href="{base}/requirements#R-DEMO-1">R-DEMO-1</a>' in work
    assert f'<a href="/k/{ids["note"]}">knowledge:hostile</a>' in work
    assert re.search(rf'<a href="{base}/findings#[0-9a-f]{{12}}">finding:[0-9a-f]{{12}}</a>', work)
    assert '<a href="https://example.org/pr/1" rel="noreferrer noopener">' in work
    assert "<code>javascript:alert(3)</code>" in work, "an issue URL that is not a web address is shown, not linked"
    assert "tester, ready → review: note &lt;script&gt;" in work

    _, _, findings = _request(server, f"{base}/findings")
    assert re.search(r'<a id="[0-9a-f]{12}"></a>', findings) and f'href="{base}/blueprint/' in findings
    _, _, requirements = _request(server, f"{base}/requirements")
    assert '<a id="R-DEMO-1"></a>' in requirements

    _, _, start = _request(server, "/")
    assert f'<a href="{base}">proj</a>' in start and "Shared note" in start
    assert str(home) not in start and "root_path" not in start
    for path in _pages(workshop, home):
        assert str(home) not in _request(server, path)[2], path


def test_an_earlier_revision_points_to_the_latest(server: tuple[str, int], workshop: Grove, home: Path) -> None:
    latest = _ids(workshop, home)["note"]
    with Grove(home) as grove:
        first = grove.knowledge_get("hostile", "proj", revision=1)["id"]
    _, _, body = _request(server, f"/k/{first}")
    assert "Revision: 1 of 2" in body and f'<a href="/k/{latest}">Read the latest</a>' in body


# -- read-only ---------------------------------------------------------------------------


def test_viewing_changes_nothing(server: tuple[str, int], workshop: Grove, home: Path, tmp_path: Path) -> None:
    with Grove(home) as grove:
        counts = [grove.project_get(name)["counts"] for name in ("tiny", "proj")]
        notes = grove.knowledge_search()["total"]
    database = (home / "grove.db").read_bytes()
    project = tree_snapshot(tmp_path / "proj")
    for path in _pages(workshop, home):
        assert _request(server, path)[0] == 200
    assert (home / "grove.db").read_bytes() == database and tree_snapshot(tmp_path / "proj") == project
    with Grove(home) as grove:
        assert [grove.project_get(name)["counts"] for name in ("tiny", "proj")] == counts
        assert grove.knowledge_search()["total"] == notes


def test_the_read_only_connection_cannot_write_and_creates_nothing(workshop: Grove, home: Path, tmp_path: Path) -> None:
    with Grove(home, read_only=True) as grove:
        assert grove.status()["project_count"] == 2
        with pytest.raises(GroveError) as caught:
            grove.work_create("tiny", "must not be stored")
        assert caught.value.code == "invalid" and "read-only" in caught.value.message
    conn = connect_read_only(home)
    try:
        with pytest.raises(Exception, match="readonly|read-only"):
            conn.execute("DELETE FROM work_items")
    finally:
        conn.close()
    with Grove(home) as grove:
        assert grove.work_list("tiny")["total"] == 0

    empty = tmp_path / "no-home-here"
    with pytest.raises(GroveError) as caught:
        connect_read_only(empty)
    assert caught.value.code == "not_found" and not empty.exists()
    status, page = view.respond(empty, "/")
    assert status == 500 and "no Grove database" in page
    assert not empty.exists()


def test_view_on_a_data_directory_without_a_database_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    empty = tmp_path / "nothing"
    assert main(["--home", str(empty), "view", "--port", "0"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "not_found" and not empty.exists()


def test_a_database_of_another_schema_version_is_not_read(workshop: Grove, home: Path) -> None:
    import sqlite3

    conn = sqlite3.connect(home / "grove.db")
    conn.execute("PRAGMA user_version = 1")
    conn.commit()
    conn.close()
    with pytest.raises(GroveError) as caught:
        connect_read_only(home)
    assert caught.value.code == "io" and "grove status" in caught.value.message
    status, page = view.respond(home, "/")
    assert status == 500 and "schema version" in page


# -- the rest of Grove does not listen ------------------------------------------------------


def test_only_the_view_command_loads_the_listener(tmp_path: Path) -> None:
    code = (
        "import sys\n"
        "from sf_grove.cli import main\n"
        f"home = {str(tmp_path / 'home')!r}\n"
        f"assert main(['--home', home, 'project', 'create', 'tiny', '--root', {str(REPO / 'fixtures' / 'tiny')!r}]) == 0\n"
        f"assert main(['--home', home, 'export', 'tiny']) == 0\n"
        "loaded = sorted(name for name in sys.modules if name in ('http.server', 'socketserver', 'sf_grove.view'))\n"
        "assert not loaded, loaded\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
