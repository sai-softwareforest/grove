"""Requirement 5: MCP stdio smoke. Spawns the real `grove mcp` process."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conftest import TINY
from sf_grove.mcp_server import INSTRUCTIONS
from sf_grove.tools import TOOLS

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

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        message: dict = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        while True:
            reply = self._messages.get(timeout=20)
            assert reply is not None, "server closed stdout before answering " + method
            if reply.get("id") == self._next_id:
                assert "error" not in reply, reply
                return reply["result"]

    def call(self, name: str, arguments: dict) -> tuple[dict, bool]:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        assert len(result["content"]) == 1 and result["content"][0]["type"] == "text"
        return json.loads(result["content"][0]["text"]), bool(result.get("isError"))

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


@pytest.fixture
def server(home: Path, tmp_path: Path):
    process = McpProcess(home, tmp_path)
    try:
        yield process
    finally:
        if process.process.poll() is None:
            process.process.kill()
            process.process.wait()


def test_mcp_stdio_smoke(server: McpProcess, home: Path) -> None:
    initialized = server.request(
        "initialize",
        {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "grove-tests", "version": "0"}},
    )
    assert initialized["serverInfo"]["name"] == "grove"
    assert initialized["serverInfo"]["version"]
    assert "tools" in initialized["capabilities"]
    # The client receives the server instructions as written, once per session (R-SEC-4).
    assert initialized["instructions"] == INSTRUCTIONS
    server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    listed = server.request("tools/list")
    names = [tool["name"] for tool in listed["tools"]]
    assert len(names) == 16
    assert set(names) == EXPECTED_TOOLS
    for tool in listed["tools"]:
        assert tool["inputSchema"]["type"] == "object"
        description = tool["description"]
        assert "read-only" in description and "GitHub" in description, tool["name"]

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

    assert server.close() == 0

    # stdout is MCP JSON-RPC and nothing else.
    assert server.stdout_lines
    for line in server.stdout_lines:
        message = json.loads(line)
        assert message["jsonrpc"] == "2.0", line
        assert "id" in message or "method" in message, line
        assert "result" in message or "error" in message or "method" in message, line
    assert "grove INFO" not in "".join(server.stdout_lines)

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
