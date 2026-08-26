"""The MCP client side: spawn a server, shake hands, aggregate its tools.

MCPManager is what the agent actually sees: it connects to any number of
servers, prefixes each discovered tool as mcp__<server>__<tool> (the same
convention Claude Code uses), and exposes them as ordinary Tool objects —
the agent loop cannot tell an MCP tool from a built-in one. That opacity is
the point of MCP.
"""

from __future__ import annotations

import itertools
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from . import protocol
from ..events import EventBus
from ..tools import Tool


class MCPConnection:
    """One live server subprocess + the JSON-RPC conversation with it."""

    def __init__(self, name: str, argv: list[str], cwd: Path | None = None) -> None:
        self.name = name
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, cwd=cwd,
        )
        self._ids = itertools.count(1)
        self._lock = threading.Lock()  # one request/response in flight at a time
        self.server_info: dict[str, Any] = {}
        self.tools: list[dict[str, Any]] = []

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            msg_id = next(self._ids)
            protocol.write_message(self.proc.stdin, protocol.request(msg_id, method, params))
            while True:
                reply = protocol.read_message(self.proc.stdout)
                if reply is None:
                    raise ConnectionError(f"MCP server {self.name!r} closed its stdout")
                if reply.get("id") == msg_id:
                    if "error" in reply:
                        raise RuntimeError(f"MCP {self.name}.{method}: {reply['error']['message']}")
                    return reply.get("result", {})

    def initialize(self) -> None:
        result = self._rpc("initialize", {
            "protocolVersion": protocol.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "cc-1", "version": "0.1.0"},
        })
        self.server_info = result.get("serverInfo", {})
        protocol.write_message(self.proc.stdin, protocol.notification("notifications/initialized"))
        self.tools = self._rpc("tools/list").get("tools", [])

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        result = self._rpc("tools/call", {"name": tool_name, "arguments": arguments})
        text = "\n".join(
            block.get("text", "") for block in result.get("content", []) if block.get("type") == "text"
        )
        return text, bool(result.get("isError"))

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


class MCPManager:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.connections: dict[str, MCPConnection] = {}

    def connect(self, name: str, argv: list[str]) -> MCPConnection:
        conn = MCPConnection(name, argv)
        conn.initialize()
        self.connections[name] = conn
        self.bus.emit("mcp.connected", server=name,
                      server_info=conn.server_info,
                      tools=[t["name"] for t in conn.tools])
        return conn

    def connect_default_servers(self) -> None:
        """The two bundled demo servers, launched as real subprocesses."""
        servers_dir = Path(__file__).parent / "servers"
        self.connect("docs", [sys.executable, str(servers_dir / "docs_server.py")])
        self.connect("tickets", [sys.executable, str(servers_dir / "ticket_server.py")])

    def as_tools(self) -> list[Tool]:
        """Wrap every discovered MCP tool as a plain harness Tool."""
        tools: list[Tool] = []
        for server_name, conn in self.connections.items():
            for spec in conn.tools:
                tools.append(self._wrap(server_name, conn, spec))
        return tools

    def _wrap(self, server_name: str, conn: MCPConnection, spec: dict[str, Any]) -> Tool:
        prefixed = f"mcp__{server_name}__{spec['name']}"

        def handler(_conn=conn, _name=spec["name"], _server=server_name, **arguments: Any) -> str:
            text, is_error = _conn.call_tool(_name, arguments)
            self.bus.emit("mcp.call", server=_server, tool=_name,
                          ok=not is_error, result_preview=text[:200])
            if is_error:
                raise RuntimeError(text)
            return text

        return Tool(
            name=prefixed,
            description=f"[MCP:{server_name}] {spec.get('description', '')}",
            input_schema=spec.get("inputSchema", {"type": "object", "properties": {}}),
            handler=handler,
            capability="read",
        )

    def close_all(self) -> None:
        for conn in self.connections.values():
            conn.close()
        self.connections.clear()
