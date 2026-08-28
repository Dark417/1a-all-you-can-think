# 01 — Google ADK chat (FastAPI + browser UI)

A minimal chatbot built on **Google's Agent Development Kit (ADK)**, served
by FastAPI with a streaming browser UI. Local only.

```
app/agent.py   the agent: model + instruction + tools  (what ADK calls root_agent)
app/main.py    Runner + InMemorySessionService + SSE transport
static/        the chat page
```

## Run

```bash
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env                                # .env already filled in here
uvicorn app.main:app --reload --port 8010
# open http://localhost:8010
```

ADK's own dev UI also works against the same agent (it looks for `root_agent`):

```bash
adk web app      # from this folder; pick "app" in the dropdown
```

## Model providers

| `MODEL_PROVIDER` | Auth | How ADK talks to it |
|---|---|---|
| `openrouter` (default) | `OPENROUTER_API_KEY` | `LiteLlm(model="openrouter/<id>")` — ADK's wrapper for any non-Gemini model |
| `gemini` | `GOOGLE_API_KEY` (AI Studio) | plain model string `"gemini-2.5-flash"` — native path |

Free OpenRouter models rotate and rate-limit; if you get 429s, set
`OPENROUTER_MODEL=openrouter/free` (auto-picks an available free model) or
another `:free` id from https://openrouter.ai/models?q=free.
Some free models reject tool calls — set `ENABLE_TOOLS=false` then.

## What to look at

- **Sessions are the memory.** `InMemorySessionService` stores every event
  per `session_id`; the runner replays history to the model each turn.
  `POST /reset` deletes the session. Swap in
  `DatabaseSessionService("sqlite:///sessions.db")` to persist.
- **Streaming.** `RunConfig(streaming_mode=StreamingMode.SSE)` makes
  `run_async` yield `partial=True` events with text chunks, then a final
  event with the full text — `main.py` de-duplicates the two.
- **Tools are plain functions.** `get_current_time`'s docstring becomes the
  tool description the model sees. ADK emits a function-call event before
  running it — the UI shows those as `⚙ tool:` lines.
