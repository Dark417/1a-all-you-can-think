"""Minimal MCP (Model Context Protocol), from scratch.

MCP's stdio transport is JSON-RPC 2.0, one JSON message per line, over a
child process's stdin/stdout. No SDK here — protocol.py frames messages,
client.py drives the handshake (initialize -> tools/list -> tools/call), and
servers/ holds two independent servers the harness connects to.

Why two servers? Because the interesting part of MCP is that the harness
aggregates tools from *multiple* processes it does not own, namespaces them
(mcp__<server>__<tool>), and routes each call back to the right process.
One server would hide the routing.
"""
