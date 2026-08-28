"""ADK agent on Vertex AI.

Same ADK code as project 01 — the Vertex difference is *authentication and
routing*, not the agent API:

  GOOGLE_GENAI_USE_VERTEXAI=TRUE   -> google-genai client targets Vertex
  GOOGLE_CLOUD_PROJECT / LOCATION  -> which project + region bills & hosts
  credentials                      -> Application Default Credentials
                                      (`gcloud auth application-default login`)

No API key: ADC is a user or service-account credential, which is what makes
this the enterprise path (IAM, VPC-SC, audit logs) vs. AI Studio's API key.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import google_search

SYSTEM_INSTRUCTION = (
    "You are a concise, friendly assistant. Answer directly. "
    "When a question needs fresh facts and you have a search tool, use it and "
    "mention that you searched."
)


def get_current_time() -> dict:
    """Returns the current date and time in UTC."""
    return {"utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def provider() -> str:
    return os.getenv("MODEL_PROVIDER", "vertex").lower()


def build_model():
    if provider() == "vertex":
        # A bare model name; the google-genai client reads
        # GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION
        # and picks up ADC automatically.
        return os.getenv("VERTEX_MODEL", "gemini-2.5-flash")
    return LiteLlm(model=f"openrouter/{os.getenv('OPENROUTER_MODEL', 'openrouter/free')}")


def build_tools() -> list:
    if provider() == "vertex":
        # google_search is a Gemini built-in tool. ADK does not let a Gemini
        # built-in tool share an agent with function tools, so it's alone here.
        if os.getenv("ENABLE_GOOGLE_SEARCH", "true").lower() == "true":
            return [google_search]
        return [get_current_time]
    return [get_current_time]


def build_agent() -> LlmAgent:
    return LlmAgent(
        name="vertex_chat_agent",
        model=build_model(),
        description="A chat assistant on Vertex AI with Google Search grounding.",
        instruction=SYSTEM_INSTRUCTION,
        tools=build_tools(),
    )


root_agent = build_agent()
