"""FastAPI backend — LangGraph agent over BazaarLink (OpenAI-compatible).

    POST /chat   {"session_id", "message", "model"?} -> SSE  data: {"delta"|"tool"|"status"|"error"} … [DONE]
    POST /reset  {"session_id"}
    GET  /health
    GET  /models

Run:  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from graph import build_graph  # noqa: E402

DEFAULT_MODEL = os.getenv("MODEL", "qwen/qwen3.7-flash:free")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.bazaarlink.ai/v1")

app = FastAPI(title="LangGraph backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# One compiled graph per model (each owns its MemorySaver). Conversation
# memory lives inside the checkpointer keyed by thread_id == session_id.
graphs: dict[str, object] = {}
# session_id -> model it was started on, so /reset can find the right graph
session_models: dict[str, str] = {}


def graph_for(model: str):
    if model not in graphs:
        graphs[model] = build_graph(model)
    return graphs[model]


class ChatRequest(BaseModel):
    session_id: str
    message: str
    model: str | None = None


class ResetRequest(BaseModel):
    session_id: str


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/health")
def health():
    return {"status": "ok", "framework": "langgraph", "provider": "bazaarlink", "model": DEFAULT_MODEL}


@app.get("/models")
async def models():
    """Proxy BazaarLink's model list so the UI can offer a picker without the key."""
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{BASE_URL}/models",
                        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    r.raise_for_status()
    ids = sorted(m["id"] for m in r.json()["data"])
    return {"default": DEFAULT_MODEL, "models": ids}


@app.post("/reset")
def reset(req: ResetRequest):
    model = session_models.pop(req.session_id, None)
    if model and model in graphs:
        # MemorySaver has no public delete; drop the thread's checkpoints directly.
        saver = graphs[model].checkpointer
        saver.storage.pop(req.session_id, None)
        for k in [k for k in saver.writes if k[0] == req.session_id]:
            saver.writes.pop(k, None)
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest):
    model = req.model or DEFAULT_MODEL
    session_models[req.session_id] = model
    graph = graph_for(model)
    config = {"configurable": {"thread_id": req.session_id}}

    async def gen():
        try:
            # astream_events yields fine-grained events from every node; we only
            # forward model token deltas and tool start/end.
            async for ev in graph.astream_events(
                {"messages": [HumanMessage(req.message)]}, config=config, version="v2"
            ):
                kind = ev["event"]
                if kind == "on_chat_model_stream":
                    text = ev["data"]["chunk"].content
                    if isinstance(text, list):   # some providers send content blocks
                        text = "".join(b.get("text", "") for b in text if isinstance(b, dict))
                    if text:
                        yield sse({"delta": text})
                elif kind == "on_tool_start":
                    yield sse({"tool": f"{ev['name']}({json.dumps(ev['data'].get('input'))})"})
                elif kind == "on_tool_end":
                    out = ev["data"].get("output")
                    out = getattr(out, "content", out)
                    yield sse({"status": f"{ev['name']} → {out}"})
        except Exception as e:  # noqa: BLE001
            yield sse({"error": f"{type(e).__name__}: {e}"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", port=int(os.getenv("PORT", "8000")), reload=True)
