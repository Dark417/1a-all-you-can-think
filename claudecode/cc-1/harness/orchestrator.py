"""Agent orchestration: spawning, relationships, and the context boundary.

The rules this module enforces are the interesting part:

  isolation    Every agent gets a FRESH ContextWindow. A child never sees its
               parent's conversation; the parent never sees the child's. The
               interface between them is two strings: the task brief going
               down, the result summary coming back.

  summarized   A child may burn 50k tokens reading files; the parent receives
  returns      a few hundred tokens of conclusions. This is why sub-agents
               are the primary context-scaling mechanism in real harnesses —
               spawning is cheaper than remembering.

  relationships The registry records parent/child edges and live status; the
               UI draws it as a tree. Depth is capped so a runaway agent
               cannot fork-bomb the harness.

  role-scoped  Each role gets a different tool surface. The researcher cannot
  tools        write files; the coder cannot spawn sub-agents. Least
               privilege, decided at spawn time, enforced by the registry.
"""

from __future__ import annotations

import itertools
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agent import Agent, AgentResult
from .compaction import Compactor
from .context import ContextWindow
from .events import EventBus
from .mcp.client import MCPManager
from .memory import MemoryStore
from .providers import ModelProvider, estimate_tokens
from .tools import PermissionPolicy, Tool, ToolRegistry
from .tools.files import make_file_tools
from .tools.github import MockGitHub, make_github_tools
from .tools.memory_tools import make_memory_tools
from .tools.shell import make_shell_tool
from .tools.todos import make_todo_tool

MAX_DEPTH = 2
SUMMARY_TRIGGER_TOKENS = 400   # child answers longer than this get compressed

ROLE_PROMPTS = {
    "orchestrator": (
        "You are the lead agent of a coding harness. You own the user's task end to end. "
        "Plan first with write_plan, delegate research and implementation to sub-agents "
        "with spawn_subagent, verify results, then report. Delegate anything that would "
        "fill your context with raw file contents — your job is decisions, not reading."
    ),
    "researcher": (
        "You are a research sub-agent. Gather exactly the information your task brief asks "
        "for, using the docs/ticket MCP tools and read-only file tools. Save key findings "
        "with memory_note, then reply with a compact briefing. You cannot modify anything."
    ),
    "planner": (
        "You are a planning sub-agent. Turn the task brief into a concrete, ordered "
        "implementation plan with file-level detail. You do not write code."
    ),
    "designer": (
        "You are a design sub-agent for system/API design questions. Produce a short design "
        "with interfaces, trade-offs considered, and a recommendation. You do not write code."
    ),
    "coder": (
        "You are an implementation sub-agent. Make the change your task brief describes: "
        "read the relevant files, edit or write code, and prove it works by running the "
        "test suite with run_command. Report what you changed and the test outcome."
    ),
    "reviewer": (
        "You are a review sub-agent. Independently verify the change described in your task "
        "brief: read the code, re-run the tests, and look for missed edge cases. Report "
        "approve/reject with reasons."
    ),
}

# Per-role context budgets (tokens). Deliberately small so compaction is
# observable locally; a real harness would use the model's actual window.
ROLE_BUDGETS = {"orchestrator": 24_000, "researcher": 1_500, "planner": 8_000,
                "designer": 8_000, "coder": 20_000, "reviewer": 12_000}

# Least-privilege tool surface per role.
ROLE_TOOLS = {
    "orchestrator": {"plan", "spawn", "github", "mcp", "memory", "files_read"},
    "researcher": {"files_read", "mcp", "memory"},
    "planner": {"files_read", "memory", "plan"},
    "designer": {"files_read", "memory"},
    "coder": {"files_read", "files_write", "shell", "memory", "plan"},
    "reviewer": {"files_read", "shell", "memory"},
}


@dataclass
class AgentRecord:
    id: str
    role: str
    parent: str | None
    task: str
    status: str = "running"          # running | completed | failed
    started: float = field(default_factory=time.time)
    finished: float | None = None
    result_summary: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "role": self.role, "parent": self.parent, "task": self.task,
            "status": self.status, "started": self.started, "finished": self.finished,
            "result_summary": self.result_summary, "context": self.context,
        }


class Orchestrator:
    """Owns the agent registry and everything agents share: the workspace,
    the memory store, the MCP connections, the mock GitHub, the event bus."""

    def __init__(self, workspace: Path, session_dir: Path, provider: ModelProvider,
                 bus: EventBus, permission_mode: str = "auto") -> None:
        self.workspace = Path(workspace)
        self.provider = provider
        self.bus = bus
        self.permission_mode = permission_mode
        self.memory = MemoryStore(self.workspace, session_dir)
        self.github = MockGitHub()
        self.mcp = MCPManager(bus)
        self.records: dict[str, AgentRecord] = {}
        self._ids = itertools.count(1)

    def start(self) -> None:
        self.mcp.connect_default_servers()

    def shutdown(self) -> None:
        self.mcp.close_all()

    # ------------------------------------------------------------------ spawn

    def run_task(self, task: str) -> AgentResult:
        """Entry point: the user's task becomes the orchestrator agent's task."""
        return self._spawn(role="orchestrator", task=task, parent=None, depth=0)

    def _spawn(self, role: str, task: str, parent: str | None, depth: int) -> AgentResult:
        if role not in ROLE_PROMPTS:
            raise ValueError(f"unknown role {role!r}; choose from {sorted(ROLE_PROMPTS)}")
        agent_id = f"{role}-{next(self._ids)}"

        record = AgentRecord(id=agent_id, role=role, parent=parent, task=task)
        self.records[agent_id] = record
        self.bus.emit("agent.spawned", agent_id=agent_id, role=role, parent=parent,
                      depth=depth, task=task[:300])

        window = ContextWindow(
            agent_id=agent_id,
            max_tokens=ROLE_BUDGETS[role],
            identity=ROLE_PROMPTS[role],
            environment=(f"cwd: {self.workspace}\nplatform: {platform.system().lower()}\n"
                         f"you are agent {agent_id}" + (f", spawned by {parent}" if parent else "")),
            project_memory=self.memory.project_memory(),
            task_brief=task,
        )
        # Sub-agents also see the session notes digest: cheap shared state that
        # crosses agent boundaries without sharing raw context.
        digest = self.memory.notes_digest()
        if digest and parent is not None:
            window.project_memory += "\n\n" + digest

        registry = self._build_registry(agent_id, role, depth)
        agent = Agent(agent_id, role, window,
                      registry, self.provider,
                      Compactor(self.provider, self.bus), self.bus)

        try:
            result = agent.run(task)
        except Exception as exc:
            record.status, record.finished = "failed", time.time()
            record.result_summary = f"crashed: {exc}"
            record.context = window.snapshot()
            self.bus.emit("agent.failed", agent_id=agent_id, error=str(exc))
            raise

        record.status = "completed" if result.stop == "completed" else "failed"
        record.finished = time.time()
        record.result_summary = self._summarize_result(result.text)
        record.context = window.snapshot()
        self.bus.emit("agent.completed", agent_id=agent_id, role=role, parent=parent,
                      turns=result.turns, stop=result.stop,
                      summary=record.result_summary[:400], context=record.context)
        return result

    # --------------------------------------------------------------- registry

    def _build_registry(self, agent_id: str, role: str, depth: int) -> ToolRegistry:
        surface = ROLE_TOOLS[role]
        registry = ToolRegistry(self.bus, PermissionPolicy(mode=self.permission_mode))

        file_tools = make_file_tools(self.workspace)
        if "files_read" in surface:
            registry.register_all([t for t in file_tools if t.capability == "read"])
        if "files_write" in surface:
            registry.register_all([t for t in file_tools if t.capability == "write"])
        if "shell" in surface:
            registry.register(make_shell_tool(self.workspace))
        if "plan" in surface:
            tool, _ = make_todo_tool(self.bus, agent_id)
            registry.register(tool)
        if "github" in surface:
            registry.register_all(make_github_tools(self.github))
        if "mcp" in surface:
            registry.register_all(self.mcp.as_tools())
        if "memory" in surface:
            registry.register_all(make_memory_tools(self.memory, agent_id))
        if "spawn" in surface and depth < MAX_DEPTH:
            registry.register(self._make_spawn_tool(agent_id, depth))
        return registry

    def _make_spawn_tool(self, parent_id: str, depth: int) -> Tool:
        def spawn_subagent(role: str, task: str) -> str:
            result = self._spawn(role=role, task=task, parent=parent_id, depth=depth + 1)
            record = self.records[result.agent_id]
            # THE context boundary: the parent's tool result is the summary,
            # never the child's transcript.
            return (f"[sub-agent {result.agent_id} ({role}) finished after {result.turns} turns]\n"
                    f"{record.result_summary}")

        return Tool(
            "spawn_subagent",
            "Delegate a self-contained task to a fresh sub-agent with its own clean context. "
            f"Roles: {', '.join(r for r in ROLE_PROMPTS if r != 'orchestrator')}. "
            "Write the task brief as a complete standalone instruction — the sub-agent sees "
            "none of your conversation. You get back a summary of its work.",
            {"type": "object", "properties": {
                "role": {"type": "string", "enum": [r for r in ROLE_PROMPTS if r != "orchestrator"]},
                "task": {"type": "string"}},
             "required": ["role", "task"]},
            spawn_subagent,
            capability="execute",
        )

    def _summarize_result(self, text: str) -> str:
        if estimate_tokens(text) <= SUMMARY_TRIGGER_TOKENS:
            return text
        return self.provider.summarize(
            text, "Compress this sub-agent report for its parent. Keep conclusions, "
                  "file paths, and test results; drop process narration.")

    # ------------------------------------------------------------------- view

    def tree(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records.values()]
