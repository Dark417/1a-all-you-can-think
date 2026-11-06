"""Request/response shapes shared by every framework route."""

from pydantic import BaseModel, Field

DEFAULT_PROMPT = "What's the weather in Tokyo, and what is 2 + 3? Use the tools."


class AskRequest(BaseModel):
    prompt: str = DEFAULT_PROMPT


class AskResponse(BaseModel):
    framework: str
    answer: str | None = None
    error: str | None = None
    seconds: float


class CompareRequest(BaseModel):
    prompt: str = DEFAULT_PROMPT
    frameworks: list[str] | None = Field(default=None, description="Omit to run all")


class ToolCall(BaseModel):
    tool: str = "get_weather"
    arguments: dict = {"city": "Tokyo"}
