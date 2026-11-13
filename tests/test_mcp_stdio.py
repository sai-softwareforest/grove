"""Requirement 5: MCP stdio smoke. Spawns the real `grove mcp` process.

Both protocol eras are covered (R-QUAL-7): the handshake era (`2025-11-25`,
`initialize` first) and the per-request era (`2026-07-28`, no handshake:
every request carries its protocol version in `params._meta`).
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conftest import MAP_SAMPLE, TINY
from sf_grove.mcp_server import INSTRUCTIONS
from sf_grove.tools import LOCAL, TOOLS
from test_tool_schemas import stored_schemas

HANDSHAKE = "2025-11-25"
PER_REQUEST = "2026-07-28"
# The reserved keys of the per-request envelope. A client must send the first
# two with every request; the server answers with the third.
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER = "io.modelcontextprotocol/serverInfo"


def request_meta(version: str = PER_REQUEST) -> dict:
    return {META_VERSION: version, META_CAPABILITIES: {}}


EXPECTED_TOOLS = {
    "grove_status",
    "grove_project_create",
    "grove_project_list",
    "grove_project_get",
    "grove_scan",
    "grove_blueprint_get",
    "grove_gaps",
    "grove_ingest_map",
    "grove_knowledge_write",
    "grove_knowledge_get",
    "grove_knowledge_search",
    "grove_work_create",
    "grove_work_list",
    "grove_work_get",
    "grove_work_update",
    "grove_recommend_next",
}


def grove_command() -> list[str]:
    script = Path(sys.executable).parent / ("grove.exe" if os.name == "nt" else "grove")
    if script.exists():
        return [str(script)]
    return [sys.executable, "-m", "sf_grove.cli"]


class McpProcess:
    """A `grove mcp` child with line-based JSON-RPC helpers and full stream capture."""

    def __init__(self, home: Path, cwd: Path) -> None:
        env = dict(os.environ)
        env["GROVE_HOME"] = str(home)
        self.process = subprocess.Popen(
            grove_command() + ["mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
        )
        self.stdout_lines: list[str] = []
        self.stderr_chunks: list[bytes] = []
        self._messages: queue.Queue[dict | None] = queue.Queue()
        self._next_id = 0
        # Set to an envelope to speak the per-request protocol: every request
        # then carries it as params._meta.
        self.meta: dict | None = None
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    def _pump_stdout(self) -> None:
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            line = raw.decode("utf-8")
            self.stdout_lines.append(line)
            try:
                self._messages.put(json.loads(line))
            except json.JSONDecodeError:
                pass  # recorded in stdout_lines; the purity assertion will fail on it
        self._messages.put(None)

    def _pump_stderr(self) -> None:
        assert self.process.stderr is not None
        for raw in self.process.stderr:
            self.stderr_chunks.append(raw)

    def send(self, message: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.process.stdin.flush()

    def post(self, method: str, params: dict | None = None) -> int:
        """Send one request without waiting for its reply; returns its id."""
        self._next_id += 1
        message: dict = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if self.meta is not None:
            params = {**(params or {}), "_meta": self.meta}
        if params is not None:
            message["params"] = params
        self.send(message)
        return self._next_id

    def replies(self, ids: list[int]) -> dict[int, dict]:
        """The whole reply to each of these requests, in whatever order they arrive."""
        waiting = set(ids)
        found: dict[int, dict] = {}
        while waiting:
            reply = self._messages.get(timeout=20)
            assert reply is not None, f"server closed stdout before answering {sorted(waiting)}"
            if reply.get("id") in waiting:
                waiting.remove(reply["id"])
                found[reply["id"]] = reply
        return found

    def exchange(self, method: str, params: dict | None = None) -> dict:
        """One request and its whole reply, which may be a protocol error."""
        request_id = self.post(method, params)
        return self.replies([request_id])[request_id]

    def request(self, method: str, params: dict | None = None) -> dict:
        reply = self.exchange(method, params)
        assert "error" not in reply, reply
        return reply["result"]

    def call(self, name: str, arguments: dict) -> tuple[dict, bool]:
        return envelope_of(self.request("tools/call", {"name": name, "arguments": arguments}))

    def close(self) -> int:
        assert self.process.stdin is not None
        self.process.stdin.close()
        try:
            code = self.process.wait(timeout=20)
        finally:
            if self.process.poll() is None:
                self.process.kill()
        while self._messages.get(timeout=20) is not None:  # wait for stdout EOF
            pass
        return code

    @property
    def stderr(self) -> str:
        return b"".join(self.stderr_chunks).decode("utf-8", errors="replace")


def envelope_of(result: dict) -> tuple[dict, bool]:
    """(the Grove envelope, isError) of a tools/call result: one text block, nothing else."""
    assert len(result["content"]) == 1 and result["content"][0]["type"] == "text"
    assert "structuredContent" not in result  # D-29
    return json.loads(result["content"][0]["text"]), bool(result.get("isError"))


def assert_the_tool_list_is_the_table(listed: dict) -> None:
    """Names in table order, the table's descriptions, the stored input schemas."""
    assert [tool["name"] for tool in listed["tools"]] == [tool.name for tool in TOOLS]
    stored = stored_schemas()
    for published, tool in zip(listed["tools"], TOOLS):
        assert published["description"] == tool.description, tool.name
        assert published["inputSchema"] == stored[tool.name], tool.name
        assert "outputSchema" not in published, tool.name  # D-29


def assert_stdout_is_json_rpc_only(server: McpProcess) -> None:
    assert server.stdout_lines
    for line in server.stdout_lines:
        message = json.loads(line)
        assert message["jsonrpc"] == "2.0", line
        assert "id" in message or "method" in message, line
        assert "result" in message or "error" in message or "method" in message, line
    assert "grove INFO" not in "".join(server.stdout_lines)


def handshake(server: McpProcess) -> dict:
    initialized = server.request(
        "initialize",
        {"protocolVersion": HANDSHAKE, "capabilities": {}, "clientInfo": {"name": "grove-tests", "version": "0"}},
    )
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return initialized


@pytest.fixture
def spawn(home: Path, tmp_path: Path):
    """Start `grove mcp` processes on the test's data directory; none outlives the test."""
    started: list[McpProcess] = []

    def start() -> McpProcess:
        started.append(McpProcess(home, tmp_path))
        return started[-1]

    try:
        yield start
    finally:
        for process in started:
            if process.process.poll() is None:
                process.process.kill()
                process.process.wait()


@pytest.fixture
def server(spawn) -> McpProcess:
    return spawn()


def test_mcp_stdio_smoke(server: McpProcess, home: Path) -> None:
    initialized = handshake(server)
    assert initialized["protocolVersion"] == HANDSHAKE
    assert initialized["serverInfo"]["name"] == "grove"
    assert initialized["serverInfo"]["version"]
    assert "tools" in initialized["capabilities"]
    # The client receives the server instructions as written, once per session (R-SEC-4).
    assert initialized["instructions"] == INSTRUCTIONS

    listed = server.request("tools/list")
    assert_the_tool_list_is_the_table(listed)
    names = [tool["name"] for tool in listed["tools"]]
    assert len(names) == 16
    assert set(names) == EXPECTED_TOOLS
    for tool, row in zip(listed["tools"], TOOLS):
        assert tool["inputSchema"]["type"] == "object"
        # The hints a client may act on: nothing is destructive and nothing leaves the machine.
        assert tool["annotations"] == {
            "readOnlyHint": row.read_only,
            "destructiveHint": False,
            "openWorldHint": False,
        }, tool["name"]
    # The local-only sentence is said once where every client reads it, on the
    # tool to call first, and once in the instructions (WO-20).
    local = LOCAL.strip()
    assert "read-only" in local and "GitHub" in local
    assert [tool["name"] for tool in listed["tools"] if local in tool["description"]] == ["grove_status"]
    assert local in initialized["instructions"]

    status, is_error = server.call("grove_status", {})
    assert not is_error and status["ok"] is True
    assert status["data"]["data_dir"] == str(home.resolve())
    assert status["data"]["project_count"] == 0
    # The server was started with GROVE_HOME and no --home, and says so (R-HOME-2).
    assert status["data"]["home_source"] == "env" and status["data"]["hint"]

    created, is_error = server.call("grove_project_create", {"name": "tiny", "root_path": str(TINY)})
    assert not is_error and created["data"]["name"] == "tiny"

    scanned, is_error = server.call("grove_scan", {"project": "tiny"})
    assert not is_error and scanned["data"]["findings"]["declared_untested"] >= 1

    listing, _ = server.call("grove_project_list", {})
    assert listing["data"]["total"] == 1 and listing["data"]["limit"] == 50 and listing["data"]["offset"] == 0

    # Tool failures come back as the error envelope with isError, not as stray output.
    missing, is_error = server.call("grove_project_get", {"project": "no-such-project"})
    assert is_error and missing == {"ok": False, "error": {"code": "not_found", "message": missing["error"]["message"]}}
    bad, is_error = server.call("grove_scan", {"project": "tiny", "surprise": 1})
    assert is_error and bad["error"]["code"] == "invalid"
    typo, is_error = server.call("grove_gaps", {"project": "tiny", "kind": "declared_untestd"})
    assert is_error and typo["error"]["code"] == "invalid" and "declared_untested" in typo["error"]["message"]

    assert server.close() == 0

    # stdout is MCP JSON-RPC and nothing else.
    assert_stdout_is_json_rpc_only(server)

    # The server did log (startup line, the two failed calls) - on stderr.
    assert "serving MCP on stdio" in server.stderr
    assert "grove_project_get failed" in server.stderr


def test_ingest_map_reads_only_map_like_files_over_mcp(server: McpProcess, tmp_path: Path) -> None:
    # R-SEC-5, as an MCP client meets it: the same rule as the command line, and the
    # refusal is an error envelope whose message names the accepted extensions.
    server.request(
        "initialize",
        {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "grove-tests", "version": "0"}},
    )
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    server.call("grove_project_create", {"name": "tiny", "root_path": str(TINY)})
    text = "# Map\n\nThe widget frobs on demand (documented).\n"
    for name in ("MAP.MD", "NOTES", "settings.json", ".env"):
        (tmp_path / name).write_text(text)

    for name, key in (("MAP.MD", "map"), ("NOTES", "notes")):
        ingested, is_error = server.call("grove_ingest_map", {"project": "tiny", "path": str(tmp_path / name)})
        assert not is_error and ingested["data"]["knowledge"]["key"] == key, name
    for name, extension in (("settings.json", ".json"), (".env", ".env"), ("missing.py", ".py")):
        refused, is_error = server.call("grove_ingest_map", {"project": "tiny", "path": str(tmp_path / name)})
        assert is_error and refused["ok"] is False and refused["error"]["code"] == "invalid", name
        assert repr(extension) in refused["error"]["message"] and ".markdown" in refused["error"]["message"]
    stored, _ = server.call("grove_knowledge_search", {"project": "tiny"})
    assert {hit["key"] for hit in stored["data"]["items"]} == {"map", "notes"}
    assert server.close() == 0


def test_ingest_map_takes_an_author_over_mcp(spawn, monkeypatch: pytest.MonkeyPatch) -> None:
    # R-GROK-1, R-IF-10 (WO-21): an MCP client names who ingests a map with no
    # environment variable, and the name is on the revision it stored.
    def start() -> McpProcess:
        server = spawn()
        handshake(server)
        return server

    def ingest(server: McpProcess, **extra: object) -> tuple[dict, bool]:
        return server.call("grove_ingest_map", {"project": "tiny", "path": str(MAP_SAMPLE), **extra})

    server = start()
    listed = {tool["name"]: tool for tool in server.request("tools/list")["tools"]}
    assert listed["grove_ingest_map"]["inputSchema"]["properties"]["author"]["maxLength"] == 64
    assert "author" not in listed["grove_ingest_map"]["inputSchema"]["required"]
    server.call("grove_project_create", {"name": "tiny", "root_path": str(TINY)})

    named, is_error = ingest(server, author="ana")
    assert not is_error and named["data"]["knowledge"]["revision"] == 1
    assert "author" not in named["data"]  # the result is what it was; the name is read back
    assert ingest(server)[0]["data"]["knowledge"]["revision"] == 2
    # A name Grove would not store is refused before anything is written.
    for bad in ("x" * 65, "two\nlines"):
        refused, is_error = ingest(server, author=bad)
        assert is_error and refused["error"]["code"] == "invalid", bad
    assert server.close() == 0

    # A server registered with GROVE_AUTHOR: the argument wins, a blank one is no name.
    monkeypatch.setenv("GROVE_AUTHOR", "sam")
    server = start()
    ingest(server)
    ingest(server, author="ana")
    ingest(server, author=" ")

    def author_of(revision: int) -> str | None:
        document, _ = server.call("grove_knowledge_get", {"key": "map_sample", "project": "tiny", "revision": revision})
        return document["data"]["author"]

    assert [author_of(revision) for revision in (1, 2, 3, 4, 5)] == ["ana", None, "sam", "ana", "sam"]
    latest, _ = server.call("grove_knowledge_search", {"project": "tiny"})
    assert latest["data"]["items"][0]["revision"] == 5
    assert server.close() == 0


def test_mcp_stdio_per_request_era(server: McpProcess, home: Path) -> None:
    """Revision 2026-07-28: no `initialize`; the first line the server reads is a real request."""
    server.meta = request_meta()

    discovered = server.request("server/discover")
    assert PER_REQUEST in discovered["supportedVersions"]
    assert "tools" in discovered["capabilities"]
    assert discovered["instructions"] == INSTRUCTIONS
    # There is no handshake to carry the server's name, so every result does.
    assert discovered["_meta"][META_SERVER]["name"] == "grove"
    assert discovered["_meta"][META_SERVER]["version"]

    # The same sixteen tools, descriptions and schemas as in the handshake era.
    assert_the_tool_list_is_the_table(server.request("tools/list"))

    status, is_error = server.call("grove_status", {})
    assert not is_error and status["ok"] is True
    assert status["data"]["data_dir"] == str(home.resolve())
    assert status["data"]["project_count"] == 0 and status["data"]["home_source"] == "env"

    created, is_error = server.call("grove_project_create", {"name": "tiny", "root_path": str(TINY)})
    assert not is_error and created["data"]["name"] == "tiny"
    scanned, is_error = server.call("grove_scan", {"project": "tiny"})
    assert not is_error and scanned["data"]["findings"]["declared_untested"] >= 1

    # Failures are the same envelope with isError, as in the handshake era.
    missing, is_error = server.call("grove_project_get", {"project": "no-such-project"})
    assert is_error and missing["error"]["code"] == "not_found"
    bad, is_error = server.call("grove_scan", {"project": "tiny", "surprise": 1})
    assert is_error and bad["error"]["code"] == "invalid"
    typo, is_error = server.call("grove_gaps", {"project": "tiny", "kind": "declared_untestd"})
    assert is_error and typo["error"]["code"] == "invalid" and "declared_untested" in typo["error"]["message"]

    # Requests sent back to back are all answered while stdin stays open. The
    # replies may come in any order; the id says which is which.
    asked = {
        server.post("tools/call", {"name": "grove_project_get", "arguments": {"project": "tiny"}}): "tiny",
        server.post("tools/call", {"name": "grove_gaps", "arguments": {"project": "tiny"}}): None,
        server.post("tools/call", {"name": "grove_work_create", "arguments": {"project": "tiny", "title": "One"}}): "One",
        server.post("tools/call", {"name": "grove_work_create", "arguments": {"project": "tiny", "title": "Two"}}): "Two",
        server.post("tools/call", {"name": "grove_recommend_next", "arguments": {"project": "tiny"}}): None,
    }
    answers = server.replies(list(asked))
    assert set(answers) == set(asked)
    for request_id, expected in asked.items():
        answer, is_error = envelope_of(answers[request_id]["result"])
        assert not is_error and answer["ok"] is True, answer
        if expected is not None:
            assert expected in (answer["data"].get("name"), answer["data"].get("title")), answer
    listing, _ = server.call("grove_work_list", {"project": "tiny"})
    assert listing["data"]["total"] == 2

    assert server.close() == 0
    assert_stdout_is_json_rpc_only(server)
    assert "serving MCP on stdio" in server.stderr
    assert "grove_project_get failed" in server.stderr


def test_the_first_request_decides_the_protocol_era(spawn) -> None:
    """One connection speaks one era. The other era's requests are refused, not half-served."""
    # Opened without a handshake: the connection is per-request for good.
    modern = spawn()
    modern.meta = request_meta()
    status, is_error = modern.call("grove_status", {})
    assert not is_error and status["ok"] is True

    late_handshake = modern.exchange(
        "initialize", {"protocolVersion": HANDSHAKE, "capabilities": {}, "clientInfo": {"name": "grove-tests", "version": "0"}}
    )
    assert late_handshake["error"]["code"] == -32022  # unsupported protocol version
    assert late_handshake["error"]["data"]["supported"] == [PER_REQUEST]

    modern.meta = request_meta("2031-01-01")
    unknown_version = modern.exchange("tools/list")
    assert unknown_version["error"]["code"] == -32022
    assert unknown_version["error"]["data"] == {"supported": [PER_REQUEST], "requested": "2031-01-01"}

    modern.meta = {META_VERSION: PER_REQUEST}
    assert "clientCapabilities" in modern.exchange("tools/list")["error"]["message"]
    modern.meta = None
    assert modern.exchange("tools/list")["error"]["code"] == -32602  # no envelope at all: invalid params

    # A refused request is answered and the connection goes on.
    modern.meta = request_meta()
    status, is_error = modern.call("grove_status", {})
    assert not is_error and status["ok"] is True
    assert modern.close() == 0
    assert_stdout_is_json_rpc_only(modern)

    # Opened with a handshake: a request with the per-request envelope is refused.
    legacy = spawn()
    handshake(legacy)
    legacy.meta = request_meta()
    assert legacy.exchange("tools/list")["error"]["code"] == -32600  # invalid request
    legacy.meta = None
    assert len(legacy.request("tools/list")["tools"]) == 16
    assert legacy.close() == 0
    assert_stdout_is_json_rpc_only(legacy)


def test_the_instructions_say_returned_text_is_data_never_an_instruction() -> None:
    # R-SEC-4: one sentence names the three places third-party text comes from.
    sentence = next((part for part in INSTRUCTIONS.split(". ") if "never an instruction" in part), "")
    assert sentence, "the server instructions no longer say that returned text is never an instruction"
    for word in ("scanned files", "maps", "notes", "data"):
        assert word in sentence, word


def test_tool_table_matches_the_spec() -> None:
    assert [tool.name for tool in TOOLS] == [
        "grove_status",
        "grove_project_create",
        "grove_project_list",
        "grove_project_get",
        "grove_scan",
        "grove_blueprint_get",
        "grove_gaps",
        "grove_ingest_map",
        "grove_knowledge_write",
        "grove_knowledge_get",
        "grove_knowledge_search",
        "grove_work_create",
        "grove_work_list",
        "grove_work_get",
        "grove_work_update",
        "grove_recommend_next",
    ]
    for tool in TOOLS:
        assert set(tool.schema["required"]) <= set(tool.schema["properties"])
