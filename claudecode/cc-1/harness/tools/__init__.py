"""The tool layer.

A Tool is a name, a JSON schema, and a Python callable. The registry:

  - hands the schema list to the model (this *is* the tool prompt),
  - dispatches tool_use blocks to the right callable,
  - enforces a permission policy before anything runs,
  - emits an event for every call, so every consumer sees the same story.

Failures come back as tool_result with is_error=True rather than exceptions:
the model is expected to read errors and adapt, so errors are data.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from ..events import EventBus


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[..., str]
    # "read" tools are always allowed; "write"/"execute" pass the permission gate
    capability: str = "read"

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class PermissionPolicy:
    """A miniature of a real harness's permission system.

    Modes: "auto" allows everything (like --dangerously-skip-permissions),
    "readonly" denies write/execute, "ask" would prompt a human — here it
    consults an allowlist the caller pre-approved, which is exactly what
    settings.json permission rules are.
    """

    def __init__(self, mode: str = "auto", allow: set[str] | None = None) -> None:
        self.mode = mode
        self.allow = allow or set()

    def check(self, tool: Tool) -> tuple[bool, str]:
        if tool.capability == "read" or self.mode == "auto":
            return True, ""
        if self.mode == "readonly":
            return False, f"Permission denied: {tool.name} needs {tool.capability!r} and policy is readonly."
        if self.mode == "ask":
            if tool.name in self.allow:
                return True, ""
            return False, f"Permission denied: {tool.name} is not on the allowlist."
        return False, f"Unknown permission mode {self.mode!r}."


class ToolRegistry:
    def __init__(self, bus: EventBus, policy: PermissionPolicy | None = None) -> None:
        self.bus = bus
        self.policy = policy or PermissionPolicy()
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def register_all(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def dispatch(self, agent_id: str, tool_use: dict[str, Any]) -> dict[str, Any]:
        """Execute one tool_use block, returning a tool_result block."""
        name = tool_use.get("name", "")
        args = tool_use.get("input", {}) or {}
        tool_use_id = tool_use.get("id", "")

        tool = self._tools.get(name)
        started = time.time()

        if tool is None:
            return self._result(agent_id, name, args, tool_use_id, started,
                                f"Unknown tool {name!r}. Available: {', '.join(self._tools)}", error=True)

        allowed, reason = self.policy.check(tool)
        if not allowed:
            return self._result(agent_id, name, args, tool_use_id, started, reason, error=True)

        try:
            output = tool.handler(**args)
        except TypeError as exc:
            output, error = f"Bad arguments for {name}: {exc}", True
        except Exception:
            output, error = f"Tool {name} crashed:\n{traceback.format_exc(limit=3)}", True
        else:
            error = False
        return self._result(agent_id, name, args, tool_use_id, started, str(output), error=error)

    def _result(self, agent_id: str, name: str, args: dict, tool_use_id: str,
                started: float, output: str, error: bool) -> dict[str, Any]:
        self.bus.emit(
            "tool.call",
            agent_id=agent_id,
            tool=name,
            args=_truncate_args(args),
            ok=not error,
            duration_ms=round((time.time() - started) * 1000, 1),
            output_preview=output[:300],
        )
        result: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": output,
        }
        if error:
            result["is_error"] = True
        return result


def _truncate_args(args: dict[str, Any]) -> dict[str, Any]:
    return {k: (v[:120] + "…" if isinstance(v, str) and len(v) > 120 else v) for k, v in args.items()}
