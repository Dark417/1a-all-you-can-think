"""FastAPI chat server on Amazon Bedrock (Converse API).

Same contract as the ADK projects:
    POST /chat   {"session_id", "message"} -> SSE  data: {"delta"|"error"} … [DONE]
    POST /reset  {"session_id"}
    GET  /health
    GET  /       chat UI

Run:  uvicorn app.main:app --reload --port 8030
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.llm import build_backend  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "static"
HISTORY_MAX_TURNS = 20   # keep the context window bounded

app = FastAPI(title="AWS Bedrock chat")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

backend = build_backend()

# Bedrock is stateless — unlike ADK there is no session service, so the
# server keeps the transcript per session id and resends it each turn.
histories: dict[str, list[dict]] = defaultdict(list)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ResetRequest(BaseModel):
    session_id: str


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok", "framework": "boto3-converse", "provider": backend.name,
            "model": backend.model}


@app.post("/reset")
async def reset(req: ResetRequest):
    histories.pop(req.session_id, None)
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest):
    history = histories[req.session_id]

    def generate():   # sync generator → Starlette streams it from a threadpool
        reply: list[str] = []
        try:
            for delta in backend.stream(history[-HISTORY_MAX_TURNS * 2:], req.message):
                reply.append(delta)
                yield sse({"delta": delta})
        except Exception as e:
            yield sse({"error": f"{type(e).__name__}: {e}"})
        if reply:   # only remember turns that produced an answer
            history.append({"role": "user", "content": req.message})
            history.append({"role": "assistant", "content": "".join(reply)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
