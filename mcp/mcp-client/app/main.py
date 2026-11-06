"""One FastAPI app, one MCP server, many frameworks.

    GET  /frameworks         what each adapter does differently
    GET  /mcp/inspect        raw MCP SDK: tools, resources, prompts (no LLM, no keys)
    POST /mcp/call           raw MCP SDK: call one tool directly
    POST /ask/{framework}    same prompt through one framework
    POST /compare            same prompt through several frameworks concurrently
"""

import asyncio
import time

from fastapi import FastAPI, HTTPException

from app.config import settings
from app.contract import AskRequest, AskResponse, CompareRequest, ToolCall
from app.frameworks import FRAMEWORKS, ask, raw_mcp

app = FastAPI(title="mcp-client: one MCP server, many agent frameworks")


@app.get("/frameworks")
def list_frameworks() -> dict:
    return {
        "mcp_server_url": settings.mcp_server_url,
        "frameworks": [
            {"name": f.name, "mcp_side": f.mcp_side, "how": f.how} for f in FRAMEWORKS.values()
        ],
    }


@app.get("/mcp/inspect")
async def inspect_mcp() -> dict:
    return await raw_mcp.inspect_server()


@app.post("/mcp/call")
async def call_mcp_tool(body: ToolCall) -> dict:
    return await raw_mcp.call_tool(body.tool, body.arguments)


async def _run(name: str, prompt: str) -> AskResponse:
    start = time.perf_counter()
    try:
        answer = await ask(name, prompt)
        return AskResponse(framework=name, answer=answer, seconds=round(time.perf_counter() - start, 2))
    except Exception as exc:  # report per-framework failures (missing keys, SDK errors) as data
        return AskResponse(framework=name, error=f"{type(exc).__name__}: {exc}",
                           seconds=round(time.perf_counter() - start, 2))


@app.post("/ask/{framework}")
async def ask_one(framework: str, body: AskRequest) -> AskResponse:
    if framework not in FRAMEWORKS:
        raise HTTPException(404, f"Unknown framework. Choose one of: {sorted(FRAMEWORKS)}")
    return await _run(framework, body.prompt)


@app.post("/compare")
async def compare(body: CompareRequest) -> list[AskResponse]:
    names = body.frameworks or list(FRAMEWORKS)
    unknown = sorted(set(names) - set(FRAMEWORKS))
    if unknown:
        raise HTTPException(404, f"Unknown frameworks: {unknown}")
    return list(await asyncio.gather(*(_run(n, body.prompt) for n in names)))
