"""Gradio entry point — `python app.py` runs a local web UI.

This file lives at the project root so it doubles as the Hugging Face
Spaces entry point. HF Spaces looks for `app.py` + `requirements.txt`
at the root of the Space repo.

Before first run:
    pip install -r requirements.txt
    cp .env.example .env       # add your ANTHROPIC_API_KEY
    python -m atlas ingest     # build the local vector index
    python app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src/atlas` importable when running from a fresh checkout.
SRC = Path(__file__).parent / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import gradio as gr  # noqa: E402

from atlas.config import settings  # noqa: E402
from atlas.controller import Controller  # noqa: E402
from atlas.llm import LLM, LLMError  # noqa: E402
from atlas.memory import ConversationMemory, NoteStore  # noqa: E402
from atlas.tools import default_registry  # noqa: E402
from atlas.tracing import Tracer  # noqa: E402
from atlas.vectorstore import VectorStore  # noqa: E402


def _make_controller() -> Controller | str:
    try:
        llm = LLM()
    except LLMError as e:
        return str(e)
    store = VectorStore()
    notes = NoteStore()
    registry = default_registry(vector_store=store, note_store=notes)
    return Controller(llm=llm, tools=registry, memory=ConversationMemory(), tracer=Tracer())


def build_app() -> gr.Blocks:
    controller = _make_controller()

    with gr.Blocks(title="Atlas — AI Agents Tutor", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            f"# Atlas\n"
            f"Local ReAct tutor for AI-agent architecture. "
            f"Model: **{settings.model}**.\n\n"
            f"_Try: \"What's the difference between ReAct and Plan-and-Execute?\" "
            f"or \"Recommend an architecture for an on-call triage bot.\"_"
        )

        if isinstance(controller, str):
            gr.Markdown(f"❌ **Startup error:** {controller}")
            return demo

        chatbot = gr.Chatbot(type="messages", height=520, show_copy_button=True)
        msg = gr.Textbox(placeholder="Ask Atlas…", show_label=False, autofocus=True)
        with gr.Row():
            send = gr.Button("Send", variant="primary")
            clear = gr.Button("New conversation")

        def respond(user_text: str, history: list[dict]):
            if not user_text.strip():
                return history, ""
            result = controller.run_turn(user_text)
            footer = (
                f"\n\n<sub>iterations={result.iterations} · "
                f"tool_calls={result.tool_calls}</sub>"
            )
            history = history + [
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": result.text + footer},
            ]
            return history, ""

        def reset():
            controller.memory.clear()
            return []

        send.click(respond, [msg, chatbot], [chatbot, msg])
        msg.submit(respond, [msg, chatbot], [chatbot, msg])
        clear.click(reset, None, chatbot)

    return demo


if __name__ == "__main__":
    build_app().launch()
