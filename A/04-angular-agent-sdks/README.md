# 04 — Angular chat with two switchable agent backends (Claude Agent SDK · Codex)

One Angular UI, two FastAPI backends. A dropdown in the header switches
which backend the chat talks to; each backend keeps its own conversation.
Local only.

```
frontend/         Angular 20 (standalone, signals) — dropdown = backend switch
backend-claude/   FastAPI + claude-agent-sdk (Python)         :8001
backend-codex/    FastAPI + codex CLI (`codex exec --json`)   :8002
```

Both backends implement the same contract, so the frontend only swaps a base URL:

```
POST /chat   {"session_id", "message"}  -> text/event-stream
             data: {"delta": "…"} | {"tool": "…"} | {"status": "…"} | {"error": "…"}
             data: [DONE]
POST /reset  {"session_id"}
GET  /health {framework, provider, model}
```

## Run (three terminals)

```bash
# 1. Claude backend
cd backend-claude
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt          # pulls the Claude Code CLI as a dependency
uvicorn main:app --reload --port 8001

# 2. Codex backend  (needs: npm i -g @openai/codex)
cd backend-codex
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8002

# 3. Frontend
cd frontend
npm install
npm start                                # http://localhost:4200
```

## Auth / model per backend

| Backend | Native path | OpenRouter path (what `.env` ships with) |
|---|---|---|
| Claude | `ANTHROPIC_API_KEY` + `CLAUDE_MODEL=claude-haiku-4-5` | `CLAUDE_USE_OPENROUTER=true` → the CLI gets `ANTHROPIC_BASE_URL=https://openrouter.ai/api` + `ANTHROPIC_AUTH_TOKEN`, model = any OpenRouter id. Verified working with `poolside/laguna-s-2.1:free`. |
| Codex | `codex login` (ChatGPT) or `OPENAI_API_KEY`, uses `~/.codex` | `CODEX_USE_OPENROUTER=true` → `CODEX_HOME=./codex-home`, whose `config.toml` declares OpenRouter as a custom `model_provider` with `wire_api = "responses"`. |

Free OpenRouter models rotate and rate-limit (429). Change the model id in
both `.env` files; `openrouter/free` auto-picks an available one.

## What to look at

- **Claude Agent SDK = a subprocess protocol.** `query()` spawns the Claude
  Code CLI and yields typed messages: `StreamEvent` (token deltas, enabled
  by `include_partial_messages=True`), `AssistantMessage` (complete blocks),
  `ResultMessage` (session id, cost). `main.py` de-duplicates deltas vs. the
  final block, and stores `session_id` so the next turn passes `resume=`.
- **Codex SDK = the same idea in TypeScript.** `@openai/codex-sdk` wraps
  `codex exec --json`; `backend-codex/main.py` does that directly with
  `asyncio.create_subprocess_exec` and parses the JSONL events
  (`thread.started` → thread id for `codex exec resume`, `item.completed` /
  `agent_message` → the reply, `turn.completed` → usage). No token deltas —
  the message arrives whole.
- **Both are locked to chat.** Claude: `allowed_tools=[]`,
  `setting_sources=[]`, `cwd=sandbox/`. Codex: `--sandbox read-only`, run
  from `sandbox/`, whose `AGENTS.md` is the chat persona (Codex reads it
  automatically — putting the persona in the prompt instead confused the
  model). These are *coding agents* being used as chatbots; the guardrails
  are what stop them from editing your disk.
- **Codex gotchas found while building this.** (1) Sessions are recorded
  per working directory, so `codex exec resume <id>` silently starts a
  fresh thread unless launched from the same cwd — hence `cwd=SANDBOX` on
  the subprocess. (2) `codex exec` reads stdin when it isn't a TTY; pass
  `stdin=DEVNULL` or it hangs under uvicorn. (3) With the `plugins` feature
  on, every run clones the plugin marketplace (~55 MB) into `CODEX_HOME/.tmp`
  and delays exit by ~15–30 s — `config.toml` turns it off. (4) Newer Codex
  only speaks the Responses API (`wire_api = "responses"`); OpenRouter serves
  that too.
- **Frontend switch.** `backends.ts` is the whole configuration; `app.ts`
  holds a transcript + session id *per backend* so switching doesn't lose
  either conversation. `chat.service.ts` parses SSE from a POST via
  `fetch` + `ReadableStream` (EventSource is GET-only); unsubscribing
  aborts the request, which is what the Stop button does.
