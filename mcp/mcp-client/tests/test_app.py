"""Offline tests: a throwaway MCP server in-process, no LLM keys needed."""

import importlib
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient
from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.frameworks import FRAMEWORKS
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def fake_mcp_server():
    mcp = FastMCP("fake", stateless_http=True)

    @mcp.tool()
    def get_weather(city: str) -> dict:
        """Fake weather."""
        return {"city": city, "condition": "sunny", "temp_c": 22}

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mcp.streamable_http_app(), port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    settings.mcp_server_url = f"http://127.0.0.1:{port}/mcp"
    yield
    server.should_exit = True


client = TestClient(app)


def test_inspect_and_call():
    tools = client.get("/mcp/inspect").json()["tools"]
    assert [t["name"] for t in tools] == ["get_weather"]
    result = client.post("/mcp/call", json={"tool": "get_weather", "arguments": {"city": "Tokyo"}}).json()
    assert result["is_error"] is False and "sunny" in result["text"][0]


def test_unknown_framework_404():
    assert client.post("/ask/nope", json={}).status_code == 404


def test_missing_credentials_reported_as_data():
    body = client.post("/ask/claude-connector", json={}).json()
    assert body["answer"] is None and "PUBLIC_MCP_SERVER_URL" in body["error"]


@pytest.mark.parametrize("name", sorted(FRAMEWORKS))
def test_every_adapter_imports(name):
    fw = FRAMEWORKS[name]
    assert callable(getattr(importlib.import_module(fw.module), fw.func))
