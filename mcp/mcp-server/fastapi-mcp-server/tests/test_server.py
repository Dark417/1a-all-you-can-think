"""End-to-end: start the real server on a free port, then talk MCP to it."""

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.main import app


@pytest.fixture(scope="module")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


def test_rest(base_url):
    assert httpx.get(f"{base_url}/api/add", params={"a": 2, "b": 3}).json() == {"result": 5}


@pytest.mark.anyio
async def test_mcp_contract(base_url):
    async with streamable_http_client(f"{base_url}/mcp") as (read, write, *_):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            assert tools == {"add", "get_weather", "search_notes"}
            result = await session.call_tool("add", {"a": 2, "b": 3})
            assert result.structured_content == {"result": 5}
            weather = await session.call_tool("get_weather", {"city": "Tokyo"})
            assert weather.structured_content == {"city": "Tokyo", "condition": "sunny", "temp_c": 22}
            res = await session.read_resource("notes://all")
            assert "Streamable HTTP" in res.contents[0].text
            prompts = {p.name for p in (await session.list_prompts()).prompts}
            assert prompts == {"summarize_notes"}


@pytest.fixture
def anyio_backend():
    return "asyncio"
