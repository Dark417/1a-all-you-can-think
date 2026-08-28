"""The ReAct agent loop. This is the classic Flow 4 from tutorial 05:

    while not done:
        Thought  ← LLM reasons over (system + history + tool results)
        Action   ← LLM emits 0+ tool_use blocks
        Observation ← we execute tools and append tool_result blocks
    Final answer ← LLM emits a text-only stop_reason="end_turn"

The controller owns: prompt assembly, tool dispatch, iteration & tool
budgets, guardrails, tracing. The LLM owns: deciding what to do."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import guardrails
from .config import settings
from .llm import LLM, LLMError
from .memory import ConversationMemory
from .prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION
from .tools import ToolRegistry
from .tracing import Tracer


@dataclass
class TurnResult:
    text: str
    iterations: int
    tool_calls: int
    flags: tuple[str, ...] = ()
    error: str | None = None
    raw_blocks: list[dict[str, Any]] = field(default_factory=list)


class Controller:
    def __init__(
        self,
        *,
        llm: LLM,
        tools: ToolRegistry,
        memory: ConversationMemory | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.memory = memory or ConversationMemory()
        self.tracer = tracer or Tracer()
        self.system_prompt = SYSTEM_PROMPT
        self._logged_session_start = False

    # ---- public API ------------------------------------------------------

    def run_turn(self, user_text: str) -> TurnResult:
        self._maybe_log_session_start()
        check = guardrails.check_input(user_text)
        if not check.ok:
            return TurnResult(text=f"(rejected: {check.reason})", iterations=0, tool_calls=0,
                              error=check.reason)
        self.tracer.log("user_message", {"text": guardrails.redact(user_text), "flags": check.flags})

        self.memory.append({"role": "user", "content": user_text})
        tool_calls_used = 0

        for iteration in range(1, settings.max_iterations + 1):
            try:
                resp = self.llm.complete(
                    system=self.system_prompt,
                    messages=self.memory.compose(),
                    tools=self.tools.specs(),
                )
            except LLMError as e:
                self.tracer.log("error", {"where": "llm", "msg": str(e)})
                return TurnResult(text=f"(model error: {e})", iterations=iteration,
                                  tool_calls=tool_calls_used, error=str(e))

            self.tracer.log("llm_response", {
                "iteration": iteration,
                "stop_reason": resp.stop_reason,
                "content": [_block_to_dict(b) for b in resp.content],
                "usage": _usage_to_dict(resp),
            })

            if resp.stop_reason == "tool_use":
                assistant_msg = {"role": "assistant", "content": [_block_to_dict(b) for b in resp.content]}
                self.memory.append(assistant_msg)

                tool_results: list[dict[str, Any]] = []
                for block in resp.content:
                    if _block_type(block) != "tool_use":
                        continue
                    tool_calls_used += 1
                    try:
                        guardrails.enforce_tool_budget(tool_calls_used, cap=settings.max_tool_calls_per_turn)
                    except guardrails.GuardrailError as e:
                        tool_results.append(_tool_result(block.id, {"error": str(e)}, is_error=True))
                        break

                    name = block.name
                    payload = block.input or {}
                    self.tracer.log("tool_call", {"name": name, "input": payload, "id": block.id})
                    try:
                        result = self.tools.run(name, payload)
                        is_error = isinstance(result, dict) and "error" in result
                    except Exception as e:  # tools must not crash the loop
                        result = {"error": f"{type(e).__name__}: {e}"}
                        is_error = True
                    self.tracer.log("tool_result", {"name": name, "id": block.id,
                                                    "result": result, "is_error": is_error})
                    tool_results.append(_tool_result(block.id, result, is_error=is_error))

                self.memory.append({"role": "user", "content": tool_results})

                if tool_calls_used >= settings.max_tool_calls_per_turn:
                    # Force the model to wrap up rather than burning more budget.
                    self.memory.append({"role": "user", "content":
                        "Tool-call budget reached. Answer the user now using "
                        "what you already have."})
                continue  # next ReAct iteration

            # stop_reason in {"end_turn", "max_tokens", "stop_sequence"}
            text = _extract_text(resp.content)
            text = guardrails.check_output(text)
            self.memory.append({"role": "assistant", "content": text})
            self.tracer.log("final_answer", {"text": guardrails.redact(text),
                                             "iterations": iteration,
                                             "tool_calls": tool_calls_used})
            return TurnResult(
                text=text,
                iterations=iteration,
                tool_calls=tool_calls_used,
                flags=check.flags,
                raw_blocks=[_block_to_dict(b) for b in resp.content],
            )

        self.tracer.log("error", {"where": "loop", "msg": "iteration budget exhausted"})
        return TurnResult(
            text="(I hit my reasoning budget. Could you narrow the question?)",
            iterations=settings.max_iterations,
            tool_calls=tool_calls_used,
            error="iteration_budget",
        )

    # ---- helpers ---------------------------------------------------------

    def _maybe_log_session_start(self) -> None:
        if self._logged_session_start:
            return
        self.tracer.log("session_start", {
            "model": self.llm.model,
            "system_prompt_version": SYSTEM_PROMPT_VERSION,
            "tools": self.tools.names(),
            "max_iterations": settings.max_iterations,
            "max_tool_calls_per_turn": settings.max_tool_calls_per_turn,
        })
        self._logged_session_start = True


# ---- block helpers --------------------------------------------------------


def _block_type(block: Any) -> str:
    return getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else "")


def _block_to_dict(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump()
    if hasattr(block, "dict"):
        try:
            return block.dict()
        except Exception:
            pass
    return {"type": getattr(block, "type", "unknown"), "repr": repr(block)}


def _extract_text(blocks: list[Any]) -> str:
    parts: list[str] = []
    for b in blocks:
        if _block_type(b) == "text":
            parts.append(getattr(b, "text", "") or (b.get("text", "") if isinstance(b, dict) else ""))
    return "".join(parts).strip()


def _tool_result(tool_use_id: str, content: Any, *, is_error: bool = False) -> dict[str, Any]:
    # Anthropic accepts string or list-of-blocks for tool_result content.
    # We send a JSON string for structured results, plain string otherwise.
    import json

    if isinstance(content, str):
        body = content
    else:
        body = json.dumps(content, default=str)
    out: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": body,
    }
    if is_error:
        out["is_error"] = True
    return out


def _usage_to_dict(resp: Any) -> dict[str, Any]:
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    if hasattr(u, "model_dump"):
        return u.model_dump()
    return {"input_tokens": getattr(u, "input_tokens", None),
            "output_tokens": getattr(u, "output_tokens", None)}
