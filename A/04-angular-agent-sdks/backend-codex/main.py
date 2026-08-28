"""FastAPI backend #2 — OpenAI Codex.

OpenAI's Codex SDK is TypeScript (`@openai/codex-sdk`); it works by spawning
`codex exec --json` and parsing the JSONL event stream. This backend does the
same thing from Python with asyncio subprocesses — the SDK's mechanism,
without the SDK's language.

    POST /chat   {"session_id", "message"} -> SSE  data: {"delta"|"tool"|"status"|"error"} … [DONE]
    POST /reset  {"session_id"}
    GET  /health

Run:  uvicorn main:app --reload --port 8002
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

HERE = Path(__file__).resolve().parent
# The cwd Codex runs in. Its AGENTS.md is the chat persona (Codex reads it
# automatically), and sessions are recorded per cwd — `resume` only finds a
# thread when launched from the same directory, so every turn runs from here.
SANDBOX = HERE / "sandbox"
CODEX_HOME = HERE / "codex-home"    # holds config.toml for the OpenRouter provider

app = FastAPI(title="Codex backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# our session id -> codex thread id (from the thread.started event)
threads: dict[str, str] = {}


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ResetRequest(BaseModel):
    session_id: str


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def use_openrouter() -> bool:
    return os.getenv("CODEX_USE_OPENROUTER", "false").lower() == "true"


def codex_env() -> dict[str, str]:
    env = dict(os.environ)
    if use_openrouter():
        env["CODEX_HOME"] = str(CODEX_HOME)   # isolates config + auth from ~/.codex
    return env


def codex_args(session_id: str, prompt: str) -> list[str]:
    exe = shutil.which("codex")
    if not exe:
        raise RuntimeError("codex CLI not found on PATH (npm i -g @openai/codex)")
    common = ["--json", "--skip-git-repo-check"]
    model = os.getenv("CODEX_MODEL")
    if model:
        common += ["-m", model]
    thread = threads.get(session_id)
    if thread:
        # `resume` re-uses the session's recorded sandbox; it rejects --sandbox / -C
        return [exe, "exec", "resume", *common, thread, prompt]
    return [exe, "exec", *common, "--sandbox", "read-only", prompt]


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "framework": "codex-cli (exec --json)",
        "provider": "openrouter" if use_openrouter() else "openai",
        "model": os.getenv("CODEX_MODEL") or "default",
        "codex": shutil.which("codex") is not None,
    }


@app.post("/reset")
async def reset(req: ResetRequest):
    threads.pop(req.session_id, None)
    return {"ok": True}


@app.post("/chat")
async def chat(req: ChatRequest):
    async def generate():
        try:
            args = codex_args(req.session_id, req.message)
        except RuntimeError as e:
            yield sse({"error": str(e)})
            yield "data: [DONE]\n\n"
            return

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,   # codex reads stdin when it isn't a TTY — give it EOF
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(SANDBOX),
            env=codex_env(),
        )
        got_message = False
        try:
            assert proc.stdout is not None
            async for raw in proc.stdout:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("{"):
                    continue
                ev = json.loads(line)
                kind = ev.get("type", "")

                if kind == "thread.started":
                    threads[req.session_id] = ev.get("thread_id", "")
                elif kind == "item.completed":
                    item = ev.get("item", {})
                    itype = item.get("type")
                    if itype == "agent_message":
                        got_message = True
                        yield sse({"delta": item.get("text", "")})   # no token deltas in exec --json
                    elif itype == "command_execution":
                        yield sse({"tool": f"command: {item.get('command', '')[:80]}"})
                    elif itype == "reasoning":
                        yield sse({"status": "💭 reasoning…"})
                elif kind == "turn.completed":
                    usage = ev.get("usage", {})
                    if usage:
                        yield sse({"status": f"tokens in/out: {usage.get('input_tokens')}/{usage.get('output_tokens')}"})
                elif kind in ("error", "turn.failed"):
                    yield sse({"error": ev.get("message") or json.dumps(ev.get("error", ev))})

            await proc.wait()
            if proc.returncode != 0 and not got_message:
                err = (await proc.stderr.read()).decode("utf-8", "replace").strip()
                yield sse({"error": f"codex exited {proc.returncode}: {err[-800:]}"})
        except Exception as e:
            yield sse({"error": f"{type(e).__name__}: {e}"})
        finally:
            if proc.returncode is None:
                proc.kill()
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
