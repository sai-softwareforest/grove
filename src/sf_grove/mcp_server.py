"""``grove mcp``: the sixteen Grove tools over MCP stdio.

stdout carries MCP JSON-RPC only. Everything else (logging, warnings) goes to
stderr. Tool results are the Grove JSON envelope as a single text block, with
``isError`` set when ``ok`` is false.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from functools import partial
from typing import Any

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from . import __version__
from .db import resolve_home_source
from .tools import TOOLS, call_tool

# What --home was given, or None: each call resolves it, so grove_status can
# say whether the data directory came from the flag, the environment or the default.
Home = str | os.PathLike[str] | None

log = logging.getLogger("grove.mcp")

INSTRUCTIONS = (
    "Grove is a local workshop for agents: it maps a codebase into a three-layer blueprint (what docs declare, "
    "what the code appears to do, what tests appear to prove), keeps lasting knowledge, and tracks local work "
    "items toward a reviewed change. It does not write code, and it does not open pull requests. Scans are "
    "read-only and deterministic; findings are heuristics. Nothing is sent to GitHub or any other service. "
    "Typical walk: grove_project_create, grove_scan, grove_gaps, grove_recommend_next."
)


def tool_definitions() -> list[types.Tool]:
    return [
        types.Tool(
            name=tool.name,
            description=tool.description,
            input_schema=tool.schema,
            annotations=types.ToolAnnotations(
                read_only_hint=tool.read_only,
                destructive_hint=False,
                open_world_hint=False,
            ),
        )
        for tool in TOOLS
    ]


def build_server(home: Home) -> Server[Any]:
    definitions = tool_definitions()

    async def on_list_tools(ctx: Any, params: Any) -> types.ListToolsResult:
        return types.ListToolsResult(tools=definitions)

    async def on_call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        # SQLite work and scans block, so they run in a worker thread; each call
        # opens its own connection there.
        envelope = await anyio.to_thread.run_sync(partial(call_tool, home, params.name, params.arguments))
        if not envelope["ok"]:
            log.info("%s failed: %s", params.name, envelope["error"]["message"])
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(envelope, ensure_ascii=False))],
            is_error=not envelope["ok"],
        )

    return Server(
        "grove",
        version=__version__,
        title="Grove",
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


async def _serve(home: Home) -> None:
    server = build_server(home)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def serve(home: Home = None) -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="grove %(levelname)s %(name)s: %(message)s")
    resolved, source = resolve_home_source(home)
    log.info("serving MCP on stdio, version %s, home %s (from %s)", __version__, resolved, source)
    try:
        anyio.run(_serve, home)
    except KeyboardInterrupt:
        pass
    log.info("stopped")
    return 0
