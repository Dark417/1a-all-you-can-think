"""cc-1: a from-scratch Claude Code-style agent harness.

Built for reading, not for production. Every mechanism that a real coding
agent harness needs is here in plain Python with no agent framework:

- the agent loop (model -> tool_use -> tool_result -> model ...)
- context engineering (deliberate assembly of system prompt, memory, history)
- context compaction when the window fills up
- sub-agent spawning with isolated contexts and summarized returns
- an orchestrator that tracks agent relationships
- MCP: a minimal client and two stdio JSON-RPC servers
- persistent memory (project memory file + session/cross-session stores)
- session management (JSONL transcripts, resume)

Model access is pluggable: Anthropic API, Amazon Bedrock, or a deterministic
mock that lets the whole thing run offline.
"""

__version__ = "0.1.0"
