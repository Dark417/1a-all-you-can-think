# cc-1 — a Claude Code-style harness from scratch

Plain Python, no agent framework, no Claude Code / Codex SDK. Every mechanism a
coding-agent harness needs, written to be read. The companion document
[`../cc/ARCHITECTURE.md`](../cc/ARCHITECTURE.md) maps each file here to the
corresponding subsystem in the real Claude Code.

## Run it

```bash
pip install -r requirements.txt        # only needed for real providers + the server

# offline, deterministic (no API keys):
python3 -m harness.cli "Work the open tickets: add stdev() to stats.py and fix the median() crash."

# real models — the identical harness code path:
ANTHROPIC_API_KEY=... python3 -m harness.cli --provider anthropic "..."
AWS_PROFILE=...       python3 -m harness.cli --provider bedrock "..."

python3 -m harness.cli --list                      # past sessions
python3 -m harness.cli --resume <session-id> "..." # carry notes forward

python3 scripts/smoke.py     # 40 end-to-end assertions
python3 server.py            # HTTP/SSE bridge for ../ui on :8100
```

## What the demo run demonstrates

The mock provider is a scripted policy that plays the model's part (see
`harness/mock_policy.py` — including why its private state is a documented
cheat). On the demo task it drives, in order:

| Mechanism | Where you see it |
|---|---|
| Planning | orchestrator writes a 5-step plan (`write_plan`), updates it as steps finish |
| MCP, two servers | sprint tickets from `tickets` server, design docs from `docs` server, namespaced `mcp__<server>__<tool>` |
| Sub-agent spawn + isolation | researcher → coder → reviewer, each with a fresh context; parent receives only summaries |
| Context accounting | every turn reports used/max tokens per agent |
| **Compaction** | the researcher's window is deliberately tiny (1,500 tokens); mid-run its older turns are summarized: watch the `compaction` event |
| Real verification | the coder runs `pytest` (really), sees real failures, fixes `stats.py`, re-runs green; the reviewer re-runs independently |
| Parallel tool use | one orchestrator turn issues `github_create_pr` + two ticket updates together |
| Memory | agents write session notes (survive compaction) and append a durable lesson to `AGENT.md` |
| Sessions | everything lands in `sessions/<id>/` — `events.jsonl` transcript, `state.json`, private `workspace/` copy; `--resume` carries the notes forward |

## Layout

```
harness/
├── agent.py            THE LOOP: context -> model -> tools -> repeat (~60 lines)
├── context.py          ContextWindow: assembly order + token accounting
├── compaction.py       threshold -> summarize old turns -> keep recent verbatim
├── memory.py           AGENT.md project memory + session notes + transcript tiers
├── orchestrator.py     roles, budgets, tool surfaces, spawn/depth/relationships
├── providers.py        one wire format; mock | anthropic | bedrock backends
├── mock_policy.py      the deterministic 'model' for offline runs
├── events.py           pub/sub event bus — CLI, server and JSONL all subscribe
├── session.py          durable sessions, resume briefs
├── runner.py           run_task(): one entry point shared by CLI/smoke/server
├── cli.py              terminal renderer
├── tools/              registry+permissions, files, shell, todos, github, memory
└── mcp/                JSON-RPC framing, client manager, servers/ (docs, tickets)
playground/             the tiny project agents operate on (copied per session)
scripts/smoke.py        the proof: 40 assertions
server.py               FastAPI + SSE for ../ui
```

## Deliberate simplifications

Honest list of where this diverges from a production harness:

- **Token counts are estimated** (~4 chars/token) rather than tokenizer-true.
- **The mock policy keeps private state** keyed by agent id — a real model
  only has its context; the cheat is what makes runs deterministic (and it is
  called out in the file).
- **Permissions** are one gate (auto/readonly/allowlist); no hooks, no OS
  sandboxing, no per-pattern rules.
- **Sequential sub-agents** — spawn blocks the parent's tool call; real
  harnesses run parallel Task calls concurrently.
- **In-memory session index**, single process; transcripts are durable but
  there is no locking for concurrent writers to one session.
- **MCP subset** — initialize/tools only; no resources, prompts, sampling,
  SSE/HTTP transports, or capability negotiation.
