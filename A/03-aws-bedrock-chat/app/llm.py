"""Two interchangeable chat backends behind one tiny interface.

    stream(history, user_text) -> Iterator[str]     # yields text deltas

`history` is a list of {"role": "user"|"assistant", "content": str}.
Both are synchronous generators on purpose: Starlette runs sync iterators in
a worker thread, and boto3 has no async client.
"""

from __future__ import annotations

import os
from typing import Iterator, Protocol

SYSTEM_PROMPT = "You are a concise, friendly assistant running on a developer's laptop."


class ChatBackend(Protocol):
    name: str
    model: str

    def stream(self, history: list[dict], user_text: str) -> Iterator[str]: ...


class BedrockChat:
    """Amazon Bedrock via the Converse API.

    Converse is the model-agnostic API: the same request shape works for Nova,
    Claude, Llama, Mistral… (vs. InvokeModel, where every family has its own
    JSON body). `converse_stream` returns an event stream; text arrives in
    `contentBlockDelta` events.
    """

    name = "bedrock"

    def __init__(self) -> None:
        import boto3  # imported lazily so the openrouter path needs no AWS deps

        self.model = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
        self.client = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION", "us-east-1"))

    def stream(self, history: list[dict], user_text: str) -> Iterator[str]:
        messages = [
            {"role": m["role"], "content": [{"text": m["content"]}]} for m in history
        ] + [{"role": "user", "content": [{"text": user_text}]}]

        resp = self.client.converse_stream(
            modelId=self.model,
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            inferenceConfig={"maxTokens": 1024, "temperature": 0.7},
        )
        for event in resp["stream"]:
            if "contentBlockDelta" in event:
                yield event["contentBlockDelta"]["delta"].get("text", "")
            elif "messageStop" in event and event["messageStop"].get("stopReason") == "max_tokens":
                yield "\n\n[truncated: max_tokens]"


class OpenRouterChat:
    """OpenRouter through its OpenAI-compatible endpoint (fallback, no AWS needed)."""

    name = "openrouter"

    def __init__(self) -> None:
        from openai import OpenAI

        self.model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )

    def stream(self, history: list[dict], user_text: str) -> Iterator[str]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                    {"role": "user", "content": user_text}]
        completion = self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True, max_tokens=1024,
        )
        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def build_backend() -> ChatBackend:
    provider = os.getenv("MODEL_PROVIDER", "bedrock").lower()
    return BedrockChat() if provider == "bedrock" else OpenRouterChat()
