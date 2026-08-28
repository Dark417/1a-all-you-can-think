# A — local chatbot projects, one per agent stack

Four small, self-contained projects. Every backend is FastAPI with the same
streaming contract (`POST /chat` → SSE), so the UIs are interchangeable.
Everything runs on localhost only.

| # | Project | Agent stack | UI | Port | Runs today with |
|---|---|---|---|---|---|
| 01 | [google-adk-chat](01-google-adk-chat) | Google ADK (`LlmAgent` + `Runner`) | built-in HTML | 8010 | OpenRouter (free) · or Gemini API key |
| 02 | [vertex-adk-chat](02-vertex-adk-chat) | Google ADK on Vertex AI + Google Search grounding | built-in HTML | 8020 | OpenRouter (free) · or `gcloud` ADC + project |
| 03 | [aws-bedrock-chat](03-aws-bedrock-chat) | Amazon Bedrock Converse API (boto3) | built-in HTML | 8030 | OpenRouter (free) · or `aws configure` + model access |
| 04 | [angular-agent-sdks](04-angular-agent-sdks) | Claude Agent SDK **and** Codex, switchable | Angular | 8001 / 8002 / 4200 | OpenRouter (free) · or Anthropic key / `codex login` |

## Shared contract

```
POST /chat    {"session_id": "<uuid>", "message": "..."}   -> text/event-stream
              data: {"delta": "…"}      streamed text
              data: {"tool": "…"}       a tool call happened
              data: {"status": "…"}     informational (search queries, cost, tokens)
              data: {"error": "…"}      provider error (429s show up here)
              data: [DONE]
POST /reset   {"session_id": "<uuid>"}
GET  /health  {"framework", "provider", "model"}
```

## The OpenRouter key

Each project's `.env` (gitignored — see [.gitignore](.gitignore)) carries the
OpenRouter key so everything runs without cloud accounts, on
`poolside/laguna-s-2.1:free` (verified answering at setup time).
Free models rotate and rate-limit upstream; if you see 429 errors, switch
`*_MODEL` to `openrouter/free` (auto-routes to any free model that's up) or
pick another `:free` id from https://openrouter.ai/models?q=free.

Each project's `.env.example` shows the native path (Gemini / Vertex /
Bedrock / Anthropic / OpenAI) — flip `MODEL_PROVIDER` or the `*_USE_OPENROUTER`
flag and add the cloud credentials.

## Quick start (any project)

```bash
cd 0X-…
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 80X0        # 04: see its README (two backends + Angular)
```
