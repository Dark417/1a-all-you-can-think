# 03 — AWS Bedrock chat (FastAPI + browser UI)

A minimal chatbot on **Amazon Bedrock** using the **Converse API** through
boto3, streamed to a browser UI by FastAPI. Local only.

```
app/llm.py    BedrockChat (converse_stream) + OpenRouterChat fallback, one interface
app/main.py   per-session transcript store + SSE transport
static/       the chat page
```

## Run on Bedrock

```bash
aws configure                     # or AWS_PROFILE / SSO — the normal credential chain
# Bedrock console -> Model access -> enable the model you pick (per region)

python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
# edit .env: MODEL_PROVIDER=bedrock, AWS_REGION, BEDROCK_MODEL_ID
uvicorn app.main:app --reload --port 8030
# open http://localhost:8030
```

Minimum IAM: `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`
on the model ARN (Converse uses the same permissions as Invoke).

## Run without AWS

`.env` ships with `MODEL_PROVIDER=openrouter`; the same server streams from
a free OpenRouter model through its OpenAI-compatible endpoint.

## What to look at

- **Converse vs InvokeModel.** `InvokeModel` takes each model family's native
  JSON body (Anthropic's `messages`, Llama's `prompt`, …). `Converse` gives
  one request shape — `messages[].content[].text`, `system`,
  `inferenceConfig` — across all families, so switching `BEDROCK_MODEL_ID`
  needs no code change. Tool use is also normalized (`toolConfig`).
- **No sessions server-side.** Bedrock is a stateless inference API. The
  server keeps the transcript per `session_id` and resends the last
  `HISTORY_MAX_TURNS` turns each call — that's the whole memory model, and
  the context-window cost is yours to bound.
- **Streaming.** `converse_stream` returns an event stream; text arrives in
  `contentBlockDelta` events, `messageStop.stopReason` tells you why it ended
  (`end_turn`, `max_tokens`, `tool_use`).
- **Sync generator.** boto3 has no async client; the `/chat` generator is a
  plain `def`, which Starlette runs in a worker thread while still streaming.
- **Model IDs.** Direct ids (`amazon.nova-lite-v1:0`) are region-bound;
  cross-region *inference profiles* (`us.anthropic.claude-…`) route to
  whichever region has capacity — use those for Anthropic models.
