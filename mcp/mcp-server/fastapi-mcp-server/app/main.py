"""FastAPI host: REST routes and the MCP endpoint share one process and one domain module.

    POST /mcp            MCP over Streamable HTTP (what agent frameworks connect to)
    GET  /api/...        the same functions as plain REST (what browsers / curl use)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import domain
from app.mcp_server import mcp

# Build the MCP ASGI app once; this also creates mcp.session_manager.
# stateless_http=True: no server-side session state, so any replica can serve any request.
mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A mounted sub-app's own lifespan never runs, so start the MCP session manager here.
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="fastapi-mcp-server", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mcp": "/mcp"}


@app.get("/api/add")
def rest_add(a: int, b: int) -> dict:
    return {"result": domain.add(a, b)}


@app.get("/api/weather/{city}")
def rest_weather(city: str) -> domain.Weather:
    return domain.get_weather(city)


@app.get("/api/notes")
def rest_notes(q: str = "") -> list[str]:
    return domain.search_notes(q)


# Mount last: FastAPI routes above match first; everything else (i.e. /mcp) falls through.
app.mount("/", mcp_app)
