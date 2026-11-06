"""Google ADK: an McpToolset is just another tool in LlmAgent(tools=[...]).

ADK owns the agent loop, sessions and events; you consume an event stream from a Runner.
Auth: GOOGLE_API_KEY (Gemini API) or GOOGLE_GENAI_USE_VERTEXAI=true + project/location (Vertex).
"""

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
from google.genai import types

from app.config import settings

APP_NAME = "mcp-client"
USER_ID = "demo"


async def ask(prompt: str) -> str:
    # MCP-specific: connection params (+ optional tool_filter); ADK keeps the session open.
    toolset = McpToolset(connection_params=StreamableHTTPConnectionParams(url=settings.mcp_server_url))
    agent = LlmAgent(
        name="mcp_demo",
        model=settings.gemini_model,
        instruction=settings.system_prompt,
        tools=[toolset],
    )
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    session = await runner.session_service.create_session(app_name=APP_NAME, user_id=USER_ID)

    answer = ""
    try:
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                answer = "".join(p.text or "" for p in event.content.parts)
    finally:
        await toolset.close()  # ADK does not close MCP sessions for you
    return answer
