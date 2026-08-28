"""Input / output / loop guardrails. Mature but minimal:
- input length cap
- prompt-injection heuristic on user input (warn, don't block)
- email/credit-card redaction on anything logged
- iteration & tool-call budgets enforced by the controller via these helpers
- output length cap"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_INPUT_CHARS = 8_000
MAX_OUTPUT_CHARS = 12_000

_INJECTION_PATTERNS = [
    re.compile(r"ignore (all )?(previous|prior|above) instructions", re.I),
    re.compile(r"disregard (the )?system prompt", re.I),
    re.compile(r"you are now (?:a |an )?(?!Atlas)", re.I),
]

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


class GuardrailError(ValueError):
    """Raised when input/output is rejected outright."""


@dataclass
class InputCheck:
    ok: bool
    reason: str = ""
    flags: tuple[str, ...] = ()


def check_input(text: str) -> InputCheck:
    if not text or not text.strip():
        return InputCheck(False, "empty input")
    if len(text) > MAX_INPUT_CHARS:
        return InputCheck(False, f"input exceeds {MAX_INPUT_CHARS} chars")
    flags: list[str] = []
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            flags.append("possible_prompt_injection")
            break
    return InputCheck(True, flags=tuple(flags))


def check_output(text: str) -> str:
    """Truncates over-long outputs; never raises. Use for the final answer."""
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n\n…[truncated]"
    return text


def redact(text: str) -> str:
    """Cheap PII redaction for trace logs. Not a substitute for a real DLP."""
    text = _EMAIL_RE.sub("[redacted:email]", text)
    text = _CC_RE.sub("[redacted:cc]", text)
    return text


def enforce_iteration_budget(iteration: int, *, cap: int) -> None:
    if iteration >= cap:
        raise GuardrailError(f"iteration budget exhausted ({cap})")


def enforce_tool_budget(tool_calls_used: int, *, cap: int) -> None:
    if tool_calls_used > cap:
        raise GuardrailError(f"tool-call budget exhausted ({cap})")
