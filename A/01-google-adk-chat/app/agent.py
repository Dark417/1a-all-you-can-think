"""The ADK agent definition.

ADK separates *what the agent is* (this file: model, instruction, tools)
from *how it runs* (main.py: Runner + SessionService + transport).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

SYSTEM_INSTRUCTION = (
    "You are a concise, friendly assistant running on a developer's laptop. "
    "Answer directly. Use the get_current_time tool only when the user asks "
    "about the current date or time."
)


def get_current_time() -> dict:
    """Returns the current date and time in UTC.

    Use this when the user asks what time or what day it is.
    """
    return {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def build_model():
    """Pick the LLM behind the agent from env.

    - "gemini": ADK's native path — a plain model-name string, authenticated by
      GOOGLE_API_KEY (AI Studio). No extra wrapper needed.
    - "openrouter": any non-Google model goes through ADK's LiteLlm wrapper;
      LiteLLM reads OPENROUTER_API_KEY from the environment.
    """
    provider = os.getenv("MODEL_PROVIDER", "openrouter").lower()
    if provider == "gemini":
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    model = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    return LiteLlm(model=f"openrouter/{model}")


def build_agent() -> LlmAgent:
    tools = [get_current_time] if os.getenv("ENABLE_TOOLS", "true").lower() == "true" else []
    return LlmAgent(
        name="chat_agent",
        model=build_model(),
        description="A general-purpose chat assistant.",
        instruction=SYSTEM_INSTRUCTION,
        tools=tools,
    )


# `adk web` / `adk run` look for a module-level `root_agent`.
root_agent = build_agent()
