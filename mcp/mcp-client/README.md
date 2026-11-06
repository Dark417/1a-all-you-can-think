# MCP Client

> One FastAPI app sends the same prompt through ten framework integrations to one MCP server.

## Index

- [1. What It Shows](#1-what-it-shows)
- [2. Quick Start](#2-quick-start)
- [3. Client-Side Frameworks](#3-client-side-frameworks)
- [4. Other Integration Styles](#4-other-integration-styles)
- [5. Credentials](#5-credentials)
- [6. Layout](#6-layout)
- [7. Gotchas Found While Building](#7-gotchas-found-while-building)
- [Where This Fits](#where-this-fits)
- [References](#references)

## 1. What It Shows

The server, prompt, tools, and system prompt stay fixed; only framework code changes.

- **Client-side MCP**: this process opens the MCP session and runs the tools.
- **Provider-side MCP**: the vendor's cloud connects to the server; you only declare it.
- **Baseline**: `/mcp/inspect` and `/mcp/call` use the raw MCP SDK, no LLM.
- Each adapter marks its framework-specific lines with `# MCP-specific:` comments.

## 2. Quick Start

Start one MCP server from [../mcp-server/](../mcp-server/), then this app.

```bash
# Terminal 1: the MCP server (FastAPI on 8001, or Spring Boot on 8002)
cd ../mcp-server/fastapi-mcp-server && uv run uvicorn app.main:app --port 8001

# Terminal 2: this app
uv sync
cp .env.example .env            # add keys only for frameworks you will try
uv run uvicorn app.main:app --port 8000
```

```bash
curl localhost:8000/frameworks
curl localhost:8000/mcp/inspect                                   # no keys needed
curl -X POST localhost:8000/ask/claude-api -H "content-type: application/json" -d "{}"
curl -X POST localhost:8000/compare -H "content-type: application/json" \
     -d '{"frameworks": ["langgraph", "openai-agents"]}'
```

- Open `http://localhost:8000/docs` for the interactive Swagger UI.
- Set `MCP_SERVER_URL=http://localhost:8002/mcp` to switch to the Spring Boot server.

## 3. Client-Side Frameworks

Each of these holds the MCP connection inside this process.

| Name | MCP entry point | Loop runs in | Session lifetime |
| --- | --- | --- | --- |
| `langgraph` | `MultiServerMCPClient.get_tools()` | Your `StateGraph` + `ToolNode` | New session per tool call |
| `adk` | `McpToolset` in `LlmAgent(tools=)` | ADK `Runner` events | Until `toolset.close()` |
| `vertex` | `ClientSession` in `GenerateContentConfig(tools=)` | genai automatic function calling | Your `async with` |
| `strands` | `MCPClient` in `Agent(tools=)` | Strands `Agent` | Background thread, `agent.cleanup()` |
| `claude-api` | `async_mcp_tool(tool, session)` | Anthropic SDK tool runner | Your `async with` |
| `openai-agents` | `MCPServerStreamableHttp` in `Agent(mcp_servers=)` | `Runner.run` | Your `async with` |

Notice where MCP plugs in: a tool converter, a toolset object, or a dedicated agent field.

## 4. Other Integration Styles

These four differ in who speaks MCP or what layer the product occupies.

| Name | MCP entry point | Who speaks MCP | Note |
| --- | --- | --- | --- |
| `claude-agent-sdk` | `mcp_servers={...}` config dict | Claude Code process | Tools named `mcp__demo__<tool>` |
| `agentcore` | Strands inside `BedrockAgentCoreApp` | This process | Hosting runtime, not a framework |
| `claude-connector` | `mcp_servers` + `mcp_toolset` | Anthropic's cloud | Needs `PUBLIC_MCP_SERVER_URL` |
| `openai-hosted` | `HostedMCPTool` | OpenAI's cloud | Needs `PUBLIC_MCP_SERVER_URL` |

- Run the local AgentCore runtime first: `uv run python -m app.frameworks.agentcore_app`.
- Provider-side styles need a tunnel, such as `ngrok http 8001`, because clouds cannot reach `localhost`.

## 5. Credentials

Every SDK reads its own environment variables; `.env` is loaded at startup.

| Frameworks | Needs |
| --- | --- |
| `langgraph`, `claude-*` | `ANTHROPIC_API_KEY` (Agent SDK also accepts a Claude Code login) |
| `adk` | `GOOGLE_API_KEY`, or `GOOGLE_GENAI_USE_VERTEXAI=true` + project |
| `vertex` | `GOOGLE_CLOUD_PROJECT` + `gcloud auth application-default login` |
| `strands`, `agentcore` | AWS credentials with Bedrock model access |
| `openai-*` | `OPENAI_API_KEY` |

A missing credential returns that framework's error in the response; other frameworks still run.

## 6. Layout

```text
app/
├── main.py             FastAPI routes
├── config.py           one Settings object for all frameworks
├── contract.py         request / response models
└── frameworks/
    ├── __init__.py     registry: name -> module, lazy import
    ├── raw_mcp.py      baseline MCP SDK client
    └── <framework>.py  one adapter per framework
tests/test_app.py       offline: in-process fake MCP server
```

## 7. Gotchas Found While Building

These were verified against installed packages on 2026-11-03.

- **`mcp` is pinned below 2**: `langchain-mcp-adapters` 0.3.2 requires `mcp<2`.
  - `mcp` 2.x renamed `FastMCP` to `MCPServer`; the 1.x client still talks to 2.x servers.
- **Transport name**: use `streamable_http_client`; `streamablehttp_client` is deprecated.
- **Claude defaults**: `claude-opus-5-5` with server-side refusal fallbacks (`fallbacks="default"`).
- **Gemini default**: `gemini-3.5-flash`, matching ADK's own default.
- **Strands default model**: its built-in Bedrock default unless `BEDROCK_MODEL_ID` is set.

## Where This Fits

This project is the client half of a learning pair; [../mcp-server/](../mcp-server/) is the server half.

- After reading it, you can wire any MCP server into each framework.
- It follows `D:/2Alfred/0coding-setup/local-project/code-gen-n-framework.md`.

## References

- [Model Context Protocol](https://modelcontextprotocol.io)
- [LangChain MCP adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [Google ADK](https://google.github.io/adk-docs/)
- [OpenAI Agents SDK: MCP](https://openai.github.io/openai-agents-python/mcp/)
- [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk)
