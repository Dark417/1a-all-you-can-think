"""Model providers.

The whole harness speaks one wire format: plain dicts in the shape of the
Anthropic Messages API (content blocks, tool_use / tool_result, stop_reason).
A provider takes a ModelRequest and returns a ModelResponse in that shape.

Three implementations:

  MockProvider      - deterministic, offline. A scripted policy plays the role
                      of the model so the loop / tools / MCP / sub-agents /
                      compaction can all be exercised locally with zero keys.
  AnthropicProvider - the real Claude API via the official `anthropic` SDK.
  BedrockProvider   - the same models through Amazon Bedrock (Mantle client).

Because the wire format is identical, switching provider changes model
behaviour but not one line of harness code — the same idea as the mock IdP
in ../oauth2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_BEDROCK_MODEL = "anthropic.claude-opus-5"


@dataclass
class ModelRequest:
    system: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    max_tokens: int = 16000
    # metadata the mock policy uses to know "who is asking" (harmless to real providers)
    agent_role: str = "orchestrator"


@dataclass
class ModelResponse:
    content: list[dict[str, Any]]      # [{"type":"text",...}, {"type":"tool_use",...}]
    stop_reason: str                   # "end_turn" | "tool_use" | "max_tokens"
    input_tokens: int
    output_tokens: int
    model: str

    @property
    def tool_uses(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]

    @property
    def text(self) -> str:
        return "\n".join(b.get("text", "") for b in self.content if b.get("type") == "text")


class ModelProvider(Protocol):
    name: str

    def complete(self, request: ModelRequest) -> ModelResponse: ...
    def summarize(self, text: str, instruction: str) -> str: ...


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------

class MockProvider:
    """Deterministic stand-in for the model.

    Delegates the actual 'thinking' to a MockPolicy (see mock_policy.py),
    which inspects the conversation and decides — by rules, not weights —
    which tool to call next. Token counts are estimated at ~4 chars/token so
    context accounting and compaction behave realistically.
    """

    name = "mock"

    def __init__(self) -> None:
        from .mock_policy import MockPolicy
        self._policy = MockPolicy()

    def complete(self, request: ModelRequest) -> ModelResponse:
        content, stop_reason = self._policy.decide(request)
        return ModelResponse(
            content=content,
            stop_reason=stop_reason,
            input_tokens=estimate_tokens_request(request),
            output_tokens=estimate_tokens_blocks(content),
            model="mock-policy-1",
        )

    def summarize(self, text: str, instruction: str) -> str:
        return self._policy.summarize(text, instruction)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_tokens_blocks(blocks: list[dict[str, Any]]) -> int:
    import json
    return estimate_tokens(json.dumps(blocks, ensure_ascii=False))


def estimate_tokens_request(request: ModelRequest) -> int:
    import json
    return (
        estimate_tokens(request.system)
        + estimate_tokens(json.dumps(request.messages, ensure_ascii=False))
        + estimate_tokens(json.dumps(request.tools, ensure_ascii=False))
    )


# ---------------------------------------------------------------------------
# Anthropic API
# ---------------------------------------------------------------------------

class AnthropicProvider:
    """The real thing, via the official SDK.

    Notes for readers:
      - thinking is adaptive by default on claude-opus-5; we pass effort via
        output_config instead of a thinking budget (budget_tokens is gone).
      - the system prompt carries a cache_control breakpoint: it is the stable
        prefix, re-sent on every turn of the loop, and caching it is the
        single biggest cost lever in an agent harness.
    """

    def __init__(self, model: str = DEFAULT_ANTHROPIC_MODEL, effort: str = "high") -> None:
        import anthropic
        self.name = "anthropic"
        self.model = model
        self.effort = effort
        self._client = anthropic.Anthropic()

    def complete(self, request: ModelRequest) -> ModelResponse:
        kwargs: dict = {}
        if request.tools:
            kwargs["tools"] = request.tools
        response = self._client.messages.create(
            model=self.model,
            max_tokens=request.max_tokens,
            system=[{
                "type": "text",
                "text": request.system,
                "cache_control": {"type": "ephemeral"},
            }],
            output_config={"effort": self.effort},
            messages=request.messages,
            **kwargs,
        )
        return ModelResponse(
            content=[b.to_dict() for b in response.content],
            stop_reason=response.stop_reason or "end_turn",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )

    def summarize(self, text: str, instruction: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=2000,
            output_config={"effort": "low"},
            system="You compress agent transcripts. Keep decisions, file paths, and open questions. Drop everything else.",
            messages=[{"role": "user", "content": f"{instruction}\n\n{text}"}],
        )
        return "".join(b.text for b in response.content if b.type == "text")


# ---------------------------------------------------------------------------
# Amazon Bedrock
# ---------------------------------------------------------------------------

class BedrockProvider(AnthropicProvider):
    """Same models, AWS billing/credentials. Only the client and the model-id
    prefix differ — which is exactly why it subclasses AnthropicProvider."""

    def __init__(self, model: str = DEFAULT_BEDROCK_MODEL, region: str = "us-east-1", effort: str = "high") -> None:
        from anthropic import AnthropicBedrockMantle
        self.name = "bedrock"
        self.model = model
        self.effort = effort
        self._client = AnthropicBedrockMantle(aws_region=region)


def make_provider(name: str) -> ModelProvider:
    if name == "mock":
        return MockProvider()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "bedrock":
        return BedrockProvider()
    raise ValueError(f"unknown provider {name!r} (expected mock | anthropic | bedrock)")
