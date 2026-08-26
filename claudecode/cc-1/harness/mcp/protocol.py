"""JSON-RPC 2.0 framing for MCP's stdio transport.

The transport rules are simple: each message is a single line of JSON,
messages must not contain literal newlines, requests carry an id, responses
echo it. This file is shared by the client and both servers, which is itself
the lesson — the protocol is small enough to own.
"""

from __future__ import annotations

import json
import sys
from typing import Any, IO

JSONRPC = "2.0"
PROTOCOL_VERSION = "2025-06-18"


def write_message(stream: IO[str], message: dict[str, Any]) -> None:
    stream.write(json.dumps(message, ensure_ascii=False) + "\n")
    stream.flush()


def read_message(stream: IO[str]) -> dict[str, Any] | None:
    line = stream.readline()
    if not line:
        return None  # EOF: the peer went away
    line = line.strip()
    if not line:
        return {}
    return json.loads(line)


def request(id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": JSONRPC, "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"jsonrpc": JSONRPC, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def result(id: int, payload: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": id, "result": payload}


def error(id: int | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": id, "error": {"code": code, "message": message}}


class StdioServer:
    """Base class for the two demo servers: a blocking read-dispatch-respond
    loop over this process's own stdin/stdout. Subclasses supply a name and
    a tool table; everything protocol-shaped lives here."""

    name = "server"
    version = "0.1.0"

    def tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        raise NotImplementedError

    def serve_forever(self) -> None:
        while True:
            try:
                msg = read_message(sys.stdin)
            except json.JSONDecodeError:
                write_message(sys.stdout, error(None, -32700, "parse error"))
                continue
            if msg is None:
                return  # client closed our stdin: shut down
            if not msg or "method" not in msg:
                continue

            method, msg_id = msg["method"], msg.get("id")
            params = msg.get("params", {}) or {}

            if method == "initialize":
                write_message(sys.stdout, result(msg_id, {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                }))
            elif method == "notifications/initialized":
                pass  # notification, no response
            elif method == "tools/list":
                write_message(sys.stdout, result(msg_id, {"tools": self.tools()}))
            elif method == "tools/call":
                try:
                    text = self.call_tool(params.get("name", ""), params.get("arguments", {}) or {})
                    write_message(sys.stdout, result(msg_id, {
                        "content": [{"type": "text", "text": text}],
                        "isError": False,
                    }))
                except Exception as exc:
                    write_message(sys.stdout, result(msg_id, {
                        "content": [{"type": "text", "text": f"tool error: {exc}"}],
                        "isError": True,
                    }))
            elif msg_id is not None:
                write_message(sys.stdout, error(msg_id, -32601, f"method not found: {method}"))
