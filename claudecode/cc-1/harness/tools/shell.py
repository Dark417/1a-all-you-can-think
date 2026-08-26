"""Shell tool: run a command in the workspace, with the obvious guardrails.

Three layers a real harness also has, in miniature:
  - an allowlist of executables (the permission story),
  - a timeout (the runaway story),
  - captured, truncated output (the context-budget story — a 100k-line build
    log would destroy the window; the tool truncates so the model gets the
    tail, which is where errors live).
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from . import Tool

ALLOWED_BINARIES = {"python3", "python", "pytest", "ls", "cat", "echo", "wc", "sort", "head", "tail", "diff"}
MAX_OUTPUT = 8_000
TIMEOUT_SECONDS = 30


def make_shell_tool(workspace: Path) -> Tool:
    root = Path(workspace).resolve()

    def run_command(command: str) -> str:
        try:
            argv = shlex.split(command)
        except ValueError as exc:
            return f"ERROR: cannot parse command: {exc}"
        if not argv:
            return "ERROR: empty command"
        if argv[0] not in ALLOWED_BINARIES:
            return (f"ERROR: {argv[0]!r} is not on the allowlist "
                    f"({', '.join(sorted(ALLOWED_BINARIES))}). Shell operators are not supported.")
        try:
            proc = subprocess.run(
                argv, cwd=root, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return f"ERROR: command timed out after {TIMEOUT_SECONDS}s"
        except FileNotFoundError:
            return f"ERROR: {argv[0]} not installed"

        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        if len(out) > MAX_OUTPUT:
            out = "… (output truncated, showing tail)\n" + out[-MAX_OUTPUT:]
        return f"exit code {proc.returncode}\n{out.strip() or '(no output)'}"

    return Tool(
        "run_command",
        "Run an allowlisted command (python3, pytest, ls, …) in the workspace. "
        "No pipes or shell operators — a single argv.",
        {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
        run_command,
        capability="execute",
    )
