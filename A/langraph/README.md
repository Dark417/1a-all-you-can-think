# LangGraph chat — FastAPI + Angular, over BazaarLink

A local chat app where the "brain" is a **LangGraph** agent (LangChain tools +
per-session memory) served by **FastAPI** and rendered by an **Angular 20** UI.
The model is any id served by BazaarLink's OpenAI-compatible gateway
(`https://api.bazaarlink.ai/v1`); the UI has a picker for all ~180 of them.

```
browser (Angular :4200) ──POST /chat (SSE)──▶ FastAPI :8000 ──▶ LangGraph
                                                                  │
                                              START → agent ⇄ tools → END
                                                        │
                                              ChatOpenAI(base_url=bazaarlink)
```

## Layout

| Path | What |
|---|---|
| `backend/graph.py` | The graph: `agent` node (model call) ⇄ `tools` node, `MemorySaver` checkpointer keyed by `thread_id` |
| `backend/tools.py` | Two `@tool`s: safe `calculator`, `current_time` |
| `backend/main.py` | FastAPI: `/chat` streams `astream_events` as SSE, `/reset`, `/health`, `/models` |
| `frontend/src/app/chat.service.ts` | fetch + ReadableStream SSE parser → RxJS Observable |
| `frontend/src/app/app.ts` | Single-file component: model picker, transcript, stop button |

## Run

Backend (Python 3.11+):

```sh
cd backend
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                 # put your sk-bl-... key in it
uvicorn main:app --reload --port 8000
```

Frontend (Node 20+):

```sh
cd frontend
npm install
npm start                                            # http://localhost:4200
```

Try: *"what's 17**5 / 3?"* (calculator tool), *"what time is it?"* (time tool),
then *"and in hours?"* to see thread memory.

## Wire contract

```
POST /chat   {"session_id","message","model"?}
             → text/event-stream:  data: {"delta":"…"} | {"tool":"calculator({...})"} | {"status":"calculator → 42"} | {"error":"…"}  …  data: [DONE]
POST /reset  {"session_id"}
GET  /health → {"status","framework","provider","model"}
GET  /models → {"default","models":[...]}
```

## Notes

- **Memory** is `MemorySaver` (in-process). Restarting the backend forgets
  everything; swap for `SqliteSaver`/`PostgresSaver` for persistence.
- **Streaming**: `graph.astream_events(version="v2")` emits every node's
  events; we forward only `on_chat_model_stream` deltas and tool start/end.
- **Model choice**: default `qwen/qwen3.7-flash:free` (no credits needed, supports tool calling). Paid ids like `deepseek-v4-flash` need account credit (402 otherwise). Models with
  `reasoning.mandatory=true` (e.g. `qwen3.8-max`)
  work but stream slower and may cost more.
- **Auth**: BazaarLink is OpenAI-compatible, so `ChatOpenAI(base_url=…, api_key=…)`
  is the whole integration — no custom provider class.
