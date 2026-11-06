# Agent Rules: mcp-client

> Rules every agent follows when working in this project.

## Index

- [1. Stack And Commands](#1-stack-and-commands)
- [2. Conventions](#2-conventions)
- [3. Adding A Framework](#3-adding-a-framework)
- [4. Limits](#4-limits)

## 1. Stack And Commands

This is a Python 3.12 FastAPI app managed with `uv`.

- **Install**: `uv sync`
- **Test**: `uv run pytest -q` (offline, no keys, no paid calls)
- **Run**: `uv run uvicorn app.main:app --port 8000`
- **MCP server**: start one from `../mcp-server/` first (ports 8001 and 8002).

## 2. Conventions

The project exists to compare frameworks, so adapters must stay comparable.

- Put one adapter per framework in `app/frameworks/`.
- Keep the adapter shape: `async def <func>(prompt: str) -> str`.
- Read every URL, model, and prompt from `app.config.settings`; never hard-code them.
- Write idiomatic framework code; share only `raw_mcp.open_session` across adapters.
- Mark the lines that carry the difference with `# MCP-specific:` comments.
- Start each adapter with a docstring: mental model, then required auth.

## 3. Adding A Framework

Each new framework touches exactly four places.

1. Add `app/frameworks/<name>.py` with the adapter function.
2. Add a `Framework(...)` entry in `app/frameworks/__init__.py`.
3. Add its row to the matching README table and the credentials table.
4. Run `uv run pytest -q`; the import test covers the new entry automatically.

## 4. Limits

These protect reproducibility and the user's money.

- Keep `mcp<2` until every adapter supports 2.x; test before bumping.
- Never make paid LLM calls in tests or without the user asking.
- Verify SDK APIs by introspecting installed packages, not from memory.
- Never commit `.env`.
- Follow `D:/2Alfred/0coding-setup/local-project/code-gen-n-framework.md` when generating.
