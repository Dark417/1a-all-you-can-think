# agents.md — `chatbot/` (Atlas)

This is a self-contained Python project. The parent
[`../agents.md`](../agents.md) explains the learning workspace; this file
is for anyone (or any coding agent) working inside `chatbot/`.

## What this is

**Atlas** — a local ReAct chat agent that RAGs over `../tutorial/*.md` to
teach AI-agent architecture. See `README.md` for the user-facing docs.

## Run / test / lint

```bash
pip install -e ".[dev]"
pytest                    # offline smoke tests
atlas ingest              # build index (needs ../tutorial to exist)
atlas chat                # interactive CLI (needs ANTHROPIC_API_KEY)
atlas eval                # golden-set eval (API-calling)
ruff check src tests      # lint
```

## Conventions

- **Python ≥ 3.10**, type hints required on public functions.
- **No new top-level deps without a reason.** This stays small.
- **Tools must not crash the loop.** Catch broadly, return `{"error": ...}`.
- **Every model call goes through `LLM.complete`.** No direct
  `anthropic.*` imports outside `llm.py`.
- **Trace events should be cheap.** Don't dump full prompts; redact PII.
- **Anthropic message-shape rules** (don't violate when editing memory):
  - An assistant message containing `tool_use` blocks must be immediately
    followed by a user message whose content is a list of `tool_result`
    blocks (one per `tool_use_id`).
  - `ConversationMemory._truncate` already guards this — don't bypass it.

## Where things live

- ReAct loop: `src/atlas/controller.py`
- Tool registry: `src/atlas/tools/__init__.py`
- Prompts (versioned): `src/atlas/prompts.py`
- Eval golden set: `src/atlas/evals/golden.jsonl`

## Common edits

- **Add a tool**: drop `tools/my_tool.py` with a `build_my_tool()` →
  `Tool`, then add it in `default_registry`.
- **Swap embedding model**: pass a custom `embedding_function` when
  creating the Chroma collection in `vectorstore.py`.
- **Swap LLM provider**: only `llm.py` should need changes.

## Out of scope (on purpose)

- Authentication / multi-tenant isolation.
- Streaming responses.
- Reranker / hybrid retrieval (BM25 + vector).
- Cloud deployment.

These are explicitly listed in `README.md` under *Trade-offs*.
