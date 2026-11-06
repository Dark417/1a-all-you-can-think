"""Plain business logic shared by the MCP tools and the REST routes.

Keeping it framework-free is the point: MCP and FastAPI are two "front doors"
onto the same functions. The Spring Boot server implements the identical contract.
"""

from pydantic import BaseModel

NOTES: list[str] = [
    "MCP tools are model-controlled actions; the LLM decides when to call them.",
    "MCP resources are application-controlled context, read by URI.",
    "MCP prompts are user-controlled templates, usually exposed as slash commands.",
    "Streamable HTTP is the remote MCP transport; stdio is for local subprocesses.",
]

_WEATHER: dict[str, tuple[str, int]] = {
    "london": ("rain", 12),
    "paris": ("cloudy", 16),
    "tokyo": ("sunny", 22),
    "sydney": ("windy", 19),
}


def add(a: int, b: int) -> int:
    return a + b


class Weather(BaseModel):
    city: str
    condition: str
    temp_c: int


def get_weather(city: str) -> Weather:
    condition, temp_c = _WEATHER.get(city.strip().lower(), ("unknown", 0))
    return Weather(city=city, condition=condition, temp_c=temp_c)


def search_notes(query: str) -> list[str]:
    q = query.lower()
    return [n for n in NOTES if q in n.lower()]
