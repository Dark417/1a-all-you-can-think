"""Vertex AI (google-genai SDK): no agent framework at all.

The genai SDK accepts a live MCP ClientSession directly in `tools`; its automatic function
calling lists the tools, calls them, and loops until Gemini returns text.
Auth: Application Default Credentials (gcloud auth application-default login).
"""

from google import genai
from google.genai import types

from app.config import settings
from app.frameworks.raw_mcp import open_session


async def ask(prompt: str) -> str:
    client = genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )
    # MCP-specific: you open the session yourself (raw MCP SDK) and hand it to the model call.
    async with open_session() as session:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=settings.system_prompt,
                tools=[session],
            ),
        )
    return response.text or ""
