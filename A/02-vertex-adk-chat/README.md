# 02 — Vertex AI ADK chat (FastAPI + browser UI)

The same ADK chatbot as [01](../01-google-adk-chat), but the model runs on
**Vertex AI** — Google Cloud's hosted path — instead of AI Studio's API key.
Adds Gemini's built-in **Google Search grounding** tool. Local only.

## What's actually different from 01

| | 01 (AI Studio / OpenRouter) | 02 (Vertex AI) |
|---|---|---|
| Auth | API key in env | Application Default Credentials (`gcloud auth application-default login`) — IAM, no key |
| Routing | `generativelanguage.googleapis.com` | `{location}-aiplatform.googleapis.com` in *your* project |
| Switch | `GOOGLE_GENAI_USE_VERTEXAI=FALSE` | `GOOGLE_GENAI_USE_VERTEXAI=TRUE` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` |
| Tools | function tool (`get_current_time`) | `google_search` built-in (grounded answers, search queries surfaced in the UI) |
| Agent code | identical `LlmAgent(...)` | identical `LlmAgent(...)` |

The ADK API is the same; Vertex is a *deployment/auth* decision. That's the
thing to say out loud: the agent code doesn't know which one it's on.

## Run on Vertex

```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT
gcloud services enable aiplatform.googleapis.com

python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
# edit .env: MODEL_PROVIDER=vertex, GOOGLE_CLOUD_PROJECT=YOUR_PROJECT
uvicorn app.main:app --reload --port 8020
# open http://localhost:8020
```

## Run without GCP

`.env` ships with `MODEL_PROVIDER=openrouter`, so it runs immediately on a
free OpenRouter model via ADK's `LiteLlm` wrapper (no search grounding — that
tool is Gemini-only).

## Notes

- Gemini **built-in tools** (`google_search`, code execution) cannot be mixed
  with function tools in one agent in ADK; `agent.py` picks one set per
  provider. Use a sub-agent (`AgentTool`) when you need both.
- Grounding metadata (`event.grounding_metadata.web_search_queries`) shows
  which searches the model ran — `main.py` streams them as status lines.
- Deploying this agent to **Vertex AI Agent Engine** is
  `adk deploy agent_engine --project … --region … app` — out of scope here
  (local only), but the `root_agent` is already in the layout that expects.
