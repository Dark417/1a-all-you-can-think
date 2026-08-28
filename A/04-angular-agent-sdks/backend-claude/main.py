"""FastAPI backend #1 — Claude Agent SDK (Python).

The SDK spawns the Claude Code CLI as a subprocess and streams its messages
back as typed objects. This backend exposes one chat turn per request and
keeps the CLI session id so follow-ups resume the same conversation.

    POST /chat   {"session_id", "message"} -> SSE  data: {"delta"|"tool"|"status"|"error"} … [DONE]
    POST /reset  {"session_id"}
    GET  /health

Run:  uvicorn main:app --reload --port 8001
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from claude_agent_sdk import (  # noqa: E402
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

SANDBOX = Path(__file__).resolve().parent / "sandbox"   # cwd the CLI sees — keep it empty
SANDBOX.mkdir(exist_ok=True)

SYSTEM_PROMPT = (
    "You are a concise, friendly chat assistant. You have no tools; answer "
    "from your own knowledge and say so when you're unsure."
)

app = FastAPI(title="Claude Agent SDK backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# our session id -> Claude Code session id (from ResultMessage.session_id)
claude_sessions: dict[str, str] = {}


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ResetRequest(BaseModel):
    session_id: str


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def provider_env() -> dict[str, str]:
    """Env passed to the CLI subprocess. Native Anthropic needs nothing extra;
    OpenRouter re-points the CLI's Anthropic client at OpenRouter's
    Anthropic-compatible endpoint."""
    if os.getenv("CLAUDE_USE_OPENROUTER", "false").lower() != "true":
        return {}
    return {
        "ANTHROPIC_BASE_URL": "https://openrouter.ai/api",
        "ANTHROPIC_AUTH_TOKEN": os.environ["OPENROUTER_API_KEY"],
        "ANTHROPIC_API_KEY": "",          # make sure a stale key doesn't win
    }


def build_options(session_id: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        model=os.getenv("CLAUDE_MODEL"),
        cwd=str(SANDBOX),
        allowed_tools=[],                 # pure chat: no Bash/Edit/Write
        max_turns=2,
        setting_sources=[],               # ignore ~/.claude and project CLAUDE.md files
        resume=claude_sessions.get(session_id),
        include_partial_messages=True,    # token-level stream events
        env=provider_env(),
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "framework": "claude-agent-sdk",
        "provider": "openrouter" if os.getenv("CLAUDE_USE_OPENROUTER") == "true" else "anthropic",
        "model": os.getenv("CLAUDE_MODEL") or "default",
    }


@app.post("/reset")
async def reset(req: ResetRequest):
    claude_sessions.pop(req.session_id, None)
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest):
    async def generate():
        streamed = False   # did partial events already deliver the text?
        try:
            async for msg in query(prompt=req.message, options=build_options(req.session_id)):
                kind = type(msg).__name__

                if kind == "StreamEvent":                       # raw API events
                    ev = getattr(msg, "event", {}) or {}
                    if ev.get("type") == "content_block_delta":
                        delta = ev.get("delta", {})
                        if delta.get("type") == "text_delta" and delta.get("text"):
                            streamed = True
                            yield sse({"delta": delta["text"]})

                elif isinstance(msg, AssistantMessage):          # complete blocks
                    for block in msg.content:
                        if isinstance(block, TextBlock) and not streamed:
                            yield sse({"delta": block.text})
                        elif isinstance(block, ToolUseBlock):
                            yield sse({"tool": block.name})

                elif isinstance(msg, ResultMessage):
                    claude_sessions[req.session_id] = msg.session_id
                    if msg.is_error:
                        yield sse({"error": msg.result or "agent error"})
                    cost = getattr(msg, "total_cost_usd", None)
                    if cost:
                        yield sse({"status": f"turn cost ${cost:.4f}"})
        except Exception as e:
            yield sse({"error": f"{type(e).__name__}: {e}"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
