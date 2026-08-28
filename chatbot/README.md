---
title: Atlas — AI Agents Tutor
emoji: 🧭
colorFrom: indigo
colorTo: blue
sdk: gradio
sdk_version: "4.40.0"
app_file: app.py
pinned: false
license: mit
---

# Atlas — your local AI-agents tutor

A small but production-shaped **ReAct chat agent** that teaches you AI-agent
architecture by retrieving from your own tutorial notes. It runs entirely on
your laptop — the only external call is to the Anthropic API.

It's the "show, don't tell" companion to the tutorial in
[`../tutorial`](../tutorial). Every component named in those docs is wired up
here in code.

## What's in the box

| Layer (from `tutorial/01`) | Implementation |
|---|---|
| LLM | Anthropic Claude via the official SDK (`src/atlas/llm.py`) |
| Controller | ReAct loop with iteration + tool-call budgets (`controller.py`) |
| Prompt layer | Versioned system prompt (`prompts.py`) |
| Short-term memory | Rolling conversation buffer (`memory.py`) |
| Long-term memory | SQLite-backed notes, exposed as tools |
| Embeddings | Chroma default (`all-MiniLM-L6-v2`, downloaded on first use) |
| Vector DB | Persistent ChromaDB (`vectorstore.py`) |
| Document store | Local markdown corpus (`../tutorial` by default) |
| RAG pipeline | Heading-aware chunking + similarity search (`rag.py`) |
| Tools | `search_knowledge_base`, `save_note`, `list_notes`, `get_current_time` |
| Guardrails | Input length, prompt-injection heuristic, PII redaction, budgets |
| Observability | JSONL session traces under `data/traces/` |
| Eval harness | Golden-set eval with pytest-style summary |

**Flow:** classic ReAct (Flow 4 in `tutorial/05`). **Level:** ~6 in
`tutorial/04` — Tools + RAG + Memory + Guardrails + Tracing.

## Quickstart

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate
pip install -e .          # or: pip install -r requirements.txt

# 2. configure
cp .env.example .env      # then put your ANTHROPIC_API_KEY in .env

# 3. build the local vector index from ../tutorial
atlas ingest              # or: python -m atlas ingest

# 4. chat (CLI)
atlas chat                # or: python -m atlas chat

# 5. or run the web UI
python app.py             # → http://localhost:7860
```

`atlas info` prints the current configuration and how many chunks are
indexed. `atlas eval` runs the golden-set check (uses the API).

## Demo questions to try

- "What's the difference between ReAct and Plan-and-Execute?"
- "I'm building a customer-support bot — what architecture do you recommend?"
- "Explain MCP and when I'd use it instead of raw tool calling."
- "Save a note that I prefer pgvector for vector storage."
- "List my notes about RAG."
- "What time is it in Tokyo?"

You should see Atlas call `search_knowledge_base` first, cite the file it
drew from, then answer in ≤6 sentences.

## Project layout

```
chatbot/
├── app.py                       # Gradio web UI (also the HF Spaces entry)
├── requirements.txt
├── pyproject.toml
├── .env.example
├── src/atlas/
│   ├── cli.py                   # `atlas chat | ingest | info | eval`
│   ├── controller.py            # ReAct loop
│   ├── llm.py                   # Anthropic wrapper
│   ├── prompts.py
│   ├── rag.py                   # chunking + ingestion
│   ├── vectorstore.py           # Chroma wrapper
│   ├── memory.py                # ConversationMemory + NoteStore
│   ├── guardrails.py
│   ├── tracing.py               # JSONL session traces
│   ├── tools/                   # search_kb, notes, clock
│   └── evals/                   # golden.jsonl + run.py
├── scripts/ingest.py            # standalone ingest entry
├── tests/test_smoke.py          # offline unit tests
└── data/                        # local runtime state (gitignored)
    ├── chroma/                  # vector index
    ├── notes.sqlite             # long-term memory
    └── traces/                  # JSONL session logs
```

## Tests

```bash
pip install -e ".[dev]"
pytest                            # smoke tests (no API calls)
atlas eval                        # golden-set eval (API calls)
```

## How it maps to the tutorial

| Tutorial concept | Where to see it in code |
|---|---|
| Tool-using agent (Level 3) | `controller.py` + `tools/` |
| RAG over docs (Level 4) | `rag.py` + `vectorstore.py` + `tools/search_kb.py` |
| Memory layer (Level 6) | `memory.py` (both classes) |
| Guardrails (Level 6) | `guardrails.py` |
| Observability (Level 6) | `tracing.py` + `data/traces/*.jsonl` |
| ReAct loop (Flow 4) | `Controller.run_turn` |
| Tool catalog (per `tutorial/07`) | `tools/__init__.py:default_registry` |
| Per-tool JSON schemas | `input_schema` in each tool builder |

## Trade-offs (honest)

- **No reranker.** One easy quality bump if you want it — call Cohere or
  Voyage after `vectorstore.query`.
- **No streaming.** Tool-use streaming with Anthropic is straightforward to
  add (`messages.stream`); skipped to keep the loop legible.
- **No prompt caching.** A `cache_control` block on the system prompt would
  cut cost meaningfully if you scale this up.
- **Local-only auth.** No multi-tenant isolation in the vector store —
  add a `tenant_id` metadata filter when you outgrow that.
- **In-process tools.** When you're ready, the same tool surface can be
  re-published as an MCP server (see `tutorial/07-mcp-and-config.md`) and
  Atlas can connect to it as an MCP client instead.

## Uploading to Hugging Face Spaces

The repo root is already Spaces-compatible:

- `app.py` — Gradio entry
- `requirements.txt` — pinned-floor deps
- README frontmatter — Spaces metadata

To publish: create a new Space (SDK: Gradio), push this folder, set the
`ANTHROPIC_API_KEY` secret. The first request will trigger the Chroma
embedding-model download (~80 MB) — give it a beat.

> Note: HF Spaces' default storage is ephemeral; the `data/` directory
> resets on rebuild. For a persistent demo, either run `ingest` at
> startup in `app.py` or attach persistent storage to the Space.
