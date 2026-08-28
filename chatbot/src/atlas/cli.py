"""Rich CLI for Atlas. Three commands:

    atlas chat        # interactive ReAct loop
    atlas ingest      # (re)build the vector index from the corpus
    atlas eval        # run the golden-set eval

Run with `python -m atlas` or, after `pip install -e .`, just `atlas`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .config import settings
from .controller import Controller
from .llm import LLM, LLMError
from .memory import ConversationMemory, NoteStore
from .prompts import render_no_corpus_warning
from .rag import ingest as rag_ingest
from .tools import default_registry
from .tracing import Tracer
from .vectorstore import VectorStore

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Atlas — local AI-agents tutor.")
console = Console()


def _print_header(session_id: str) -> None:
    body = (
        f"[bold]Atlas[/bold]  ·  model: [cyan]{settings.model}[/cyan]  ·  "
        f"session: [magenta]{session_id}[/magenta]\n"
        "Type your question. Commands: [yellow]/help /reset /notes /quit[/yellow]."
    )
    console.print(Panel(body, border_style="cyan"))


def _print_help() -> None:
    t = Table(title="Slash commands", show_header=False, border_style="dim")
    t.add_row("/help", "show this help")
    t.add_row("/reset", "clear the conversation history")
    t.add_row("/notes", "list saved long-term notes")
    t.add_row("/quit, /exit", "leave the chat")
    console.print(t)


@app.command()
def chat() -> None:
    """Interactive ReAct chat."""
    try:
        llm = LLM()
    except LLMError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    store = VectorStore()
    notes = NoteStore()
    if store.count() == 0:
        console.print(f"[yellow]{render_no_corpus_warning()}[/yellow]\n")

    registry = default_registry(vector_store=store, note_store=notes)
    memory = ConversationMemory()
    tracer = Tracer()
    controller = Controller(llm=llm, tools=registry, memory=memory, tracer=tracer)

    _print_header(tracer.session_id)

    while True:
        try:
            user = console.input("[bold green]you ›[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye.[/dim]")
            break
        if not user:
            continue
        if user in {"/quit", "/exit"}:
            console.print("[dim]bye.[/dim]")
            break
        if user == "/help":
            _print_help()
            continue
        if user == "/reset":
            memory.clear()
            console.print("[dim]conversation cleared.[/dim]")
            continue
        if user == "/notes":
            rows = notes.list(limit=20)
            if not rows:
                console.print("[dim]no notes yet.[/dim]")
            else:
                t = Table(title="Notes", border_style="dim")
                t.add_column("id"); t.add_column("tags"); t.add_column("content")
                for n in rows:
                    t.add_row(str(n.id), ", ".join(n.tags), n.content[:80])
                console.print(t)
            continue

        with console.status("[dim]thinking…[/dim]", spinner="dots"):
            result = controller.run_turn(user)

        console.print(Panel(Markdown(result.text or "_(no answer)_"),
                            title="atlas", border_style="cyan"))
        console.print(
            f"[dim]· iterations={result.iterations} · tool_calls={result.tool_calls}"
            f"{' · flags=' + ','.join(result.flags) if result.flags else ''}[/dim]\n"
        )


@app.command()
def ingest(
    reset: bool = typer.Option(False, "--reset", help="Wipe the index first."),
    corpus: Path = typer.Option(None, "--corpus", help="Override corpus dir."),
) -> None:
    """Build (or rebuild) the vector index from the tutorial corpus."""
    target = corpus.resolve() if corpus else settings.corpus_dir
    console.print(f"Ingesting from [cyan]{target}[/cyan] → "
                  f"[cyan]{settings.chroma_dir}[/cyan]")
    if not target.exists():
        console.print(f"[red]corpus directory not found: {target}[/red]")
        raise typer.Exit(code=1)
    n = rag_ingest(target, reset=reset)
    console.print(f"[green]ingested {n} chunks.[/green]")


@app.command()
def info() -> None:
    """Print runtime configuration and index status."""
    store = VectorStore()
    t = Table(title="Atlas configuration", show_header=False, border_style="dim")
    t.add_row("model", settings.model)
    t.add_row("corpus_dir", str(settings.corpus_dir))
    t.add_row("chroma_dir", str(settings.chroma_dir))
    t.add_row("notes_db", str(settings.notes_db))
    t.add_row("trace_dir", str(settings.trace_dir))
    t.add_row("max_iterations", str(settings.max_iterations))
    t.add_row("max_tool_calls_per_turn", str(settings.max_tool_calls_per_turn))
    t.add_row("history_max_turns", str(settings.history_max_turns))
    t.add_row("indexed_chunks", str(store.count()))
    console.print(t)


@app.command()
def eval() -> None:
    """Run the golden-set evaluation (offline, LLM-as-judge)."""
    from .evals.run import main as run_eval

    run_eval()


if __name__ == "__main__":
    app()
