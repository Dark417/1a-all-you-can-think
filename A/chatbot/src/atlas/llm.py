"""Anthropic client wrapper. One thin layer so the rest of the code doesn't
import `anthropic` directly — makes it trivial to swap providers later."""

from __future__ import annotations

from typing import Any

import anthropic

from .config import settings


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, model: str | None = None) -> None:
        if not settings.anthropic_api_key:
            raise LLMError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = model or settings.model

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 2048,
    ) -> anthropic.types.Message:
        """One model call. Caller owns the loop."""
        try:
            return self.client.messages.create(
                model=self.model,
                system=system,
                messages=messages,
                tools=tools or [],
                max_tokens=max_tokens,
            )
        except anthropic.APIError as e:
            raise LLMError(f"Anthropic API error: {e}") from e
