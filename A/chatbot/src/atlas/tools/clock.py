"""Trivial demo tool — proves the tool-calling pipeline works end-to-end
without depending on any external service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

if TYPE_CHECKING:
    from . import Tool


def build_clock_tool() -> "Tool":
    from . import Tool

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        tz_name = (payload.get("timezone") or "UTC").strip()
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            return {"error": f"unknown timezone: {tz_name}"}
        now = datetime.now(timezone.utc).astimezone(tz)
        return {
            "iso": now.isoformat(timespec="seconds"),
            "timezone": tz_name,
            "weekday": now.strftime("%A"),
        }

    return Tool(
        name="get_current_time",
        description="Return the current wall-clock time in the given IANA timezone (default UTC).",
        input_schema={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA tz, e.g. 'UTC', 'America/Los_Angeles'.",
                    "default": "UTC",
                }
            },
        },
        handler=handler,
    )
