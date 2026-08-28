"""FastAPI transport around the ADK Runner.

    POST /chat   {"session_id": "...", "message": "..."}  -> text/event-stream
                 data: {"delta": "..."} | {"tool": "name"} | {"error": "..."}
                 data: [DONE]
    POST /reset  {"session_id": "..."}
    GET  /health
    GET  /        the chat UI (static/index.html)

Run:  uvicorn app.main:app --reload --port 8010
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402
from google.adk.agents.run_config import RunConfig, StreamingMode  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.agent import root_agent  # noqa: E402

APP_NAME = "adk_chat"
USER_ID = "local-user"          # single local user; sessions are the unit of memory
STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Google ADK chat")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# InMemorySessionService keeps the conversation (events + state) per session id.
# Swap for DatabaseSessionService("sqlite:///sessions.db") to survive restarts.
session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ResetRequest(BaseModel):
    session_id: str


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def ensure_session(session_id: str) -> None:
    existing = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=session_id
    )
    if existing is None:
        await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )


def event_text(event) -> str:
    if not (event.content and event.content.parts):
        return ""
    return "".join(p.text for p in event.content.parts if getattr(p, "text", None))


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    model = root_agent.model
    return {
        "status": "ok",
        "framework": "google-adk",
        "provider": os.getenv("MODEL_PROVIDER", "openrouter"),
        "model": getattr(model, "model", model),
    }


@app.post("/reset")
async def reset(req: ResetRequest):
    try:
        await session_service.delete_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=req.session_id
        )
    except Exception:
        pass
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest):
    await ensure_session(req.session_id)

    async def generate():
        content = types.Content(role="user", parts=[types.Part(text=req.message)])
        streamed = ""   # text already sent as partial deltas
        try:
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=req.session_id,
                new_message=content,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            ):
                for call in event.get_function_calls() or []:
                    yield sse({"tool": call.name})

                text = event_text(event)
                if not text:
                    continue
                if event.partial:
                    streamed += text
                    yield sse({"delta": text})
                elif event.is_final_response():
                    # Final event carries the full text; only send what the
                    # partial stream didn't already deliver.
                    if not streamed:
                        yield sse({"delta": text})
                    elif text.startswith(streamed) and len(text) > len(streamed):
                        yield sse({"delta": text[len(streamed):]})
                    streamed = ""
        except Exception as e:  # surface provider errors (429s etc.) in the UI
            yield sse({"error": f"{type(e).__name__}: {e}"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
