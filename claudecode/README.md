# claudecode/ — two harnesses

A study of coding-agent harnesses in two halves:

```
claudecode/
├── cc/      how the REAL Claude Code works — architecture deep-dive (no code)
├── cc-1/    a scratch harness in plain Python that implements the same
│            mechanics: agent loop, context engineering, compaction, memory,
│            tools, MCP (client + two servers), sub-agent orchestration,
│            sessions. Runs fully offline via a deterministic mock model, or
│            against the Anthropic API / Amazon Bedrock.
└── ui/      the "watchtower": an Angular dashboard that watches cc-1 run —
             live agent tree, per-agent context gauges, compaction events,
             the plan, and the full event stream.
```

> A note on the `cc/` folder: the request was to vendor the "leaked" Claude
> Code source here. Those dumps are unauthorized copies of Anthropic's
> proprietary code, so they are not included. `cc/ARCHITECTURE.md` covers the
> same ground from public sources — and `cc-1/` exists precisely so the
> mechanics can be read as working code instead.

## Quick start

```bash
# 1. the harness, in a terminal
cd cc-1
pip install anthropic fastapi "uvicorn[standard]" pytest
python3 -m harness.cli "Work the open tickets: add stdev() and fix median()."
python3 scripts/smoke.py          # 40 assertions over the whole machinery

# 2. the watchtower
python3 server.py                 # backend bridge on :8100
cd ../ui && npm install && npm run dev    # UI on :4300
```

Pick the **mock** provider in the UI (default) and hit *Run task* — no keys
needed. Watch the orchestrator plan, spawn a researcher / coder / reviewer,
call both MCP servers, hit a context ceiling and compact, fix real failing
tests, and open a (mock) PR. Switch the provider dropdown to `anthropic` or
`bedrock` to run the identical harness against a real model.

## Suggested reading order

1. `cc/ARCHITECTURE.md` — the map.
2. `cc-1/harness/agent.py` — the loop (~60 lines).
3. `cc-1/harness/context.py` + `compaction.py` — the budget and the pressure valve.
4. `cc-1/harness/orchestrator.py` — spawning, isolation, relationships.
5. `cc-1/harness/mcp/` — MCP with no SDK, client and servers.
6. Run the watchtower and watch it all happen.
