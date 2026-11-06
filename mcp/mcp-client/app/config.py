"""One settings object for every framework, so each adapter differs only in framework code."""

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Export .env into os.environ: each vendor SDK reads its own credentials from there
# (ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY, AWS_* ...).
load_dotenv()


class Settings(BaseSettings):
    # The single MCP server every framework talks to. Swap 8001 (FastAPI) for 8002 (Spring Boot).
    mcp_server_url: str = "http://localhost:8001/mcp"
    # Server-side MCP (Claude connector, OpenAI hosted MCP) is called from the vendor's cloud,
    # so it needs a public URL, e.g. an ngrok / cloudflared tunnel to the server above.
    public_mcp_server_url: str | None = None

    anthropic_model: str = "claude-opus-5-5"
    gemini_model: str = "gemini-3.5-flash"
    google_cloud_project: str | None = None
    google_cloud_location: str = "global"
    bedrock_model_id: str | None = None  # None -> Strands' default Bedrock model
    aws_region: str = "us-east-1"
    openai_model: str | None = None  # None -> OpenAI Agents SDK default model
    agentcore_url: str = "http://localhost:8080/invocations"  # local AgentCore runtime

    system_prompt: str = "You are a concise assistant. Use the MCP tools to answer; do not guess."


settings = Settings()
