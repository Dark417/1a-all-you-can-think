"""Amazon Bedrock AgentCore Runtime: hosting, not a framework.

AgentCore runs *any* agent (here, the Strands agent) behind a fixed contract:
POST /invocations and GET /ping on port 8080. MCP usage is unchanged; it's still Strands.

    Run locally:  uv run python -m app.frameworks.agentcore_app
    Deploy:       agentcore configure / agentcore launch (bedrock-agentcore-starter-toolkit)
"""

import httpx
from bedrock_agentcore import BedrockAgentCoreApp

from app.config import settings
from app.frameworks import strands_agent

app = BedrockAgentCoreApp()


@app.entrypoint
async def invoke(payload: dict) -> dict:
    return {"result": await strands_agent.ask(str(payload.get("prompt", "")))}


async def ask_via_runtime(prompt: str) -> str:
    """Client side: call the runtime over HTTP, the same contract as a deployed endpoint."""
    async with httpx.AsyncClient(timeout=120) as http:
        response = await http.post(settings.agentcore_url, json={"prompt": prompt})
        response.raise_for_status()
    return response.json()["result"]


if __name__ == "__main__":
    app.run()  # http://localhost:8080/invocations
