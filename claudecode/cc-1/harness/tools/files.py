"""File tools: read / write / edit / glob / grep, jailed to the workspace.

The jail matters: every path is resolved and checked against the workspace
root, so `../../etc/passwd` is an error, not a file read. Real harnesses do
the same before any sandboxing — the tool layer is the first wall.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from . import Tool

MAX_READ_CHARS = 40_000


def make_file_tools(workspace: Path) -> list[Tool]:
    root = Path(workspace).resolve()

    def _resolve(rel: str) -> Path:
        path = (root / rel).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"path {rel!r} escapes the workspace")
        return path

    def read_file(path: str, offset: int = 0, limit: int = 400) -> str:
        target = _resolve(path)
        if not target.exists():
            siblings = ", ".join(p.name for p in target.parent.glob("*")) if target.parent.exists() else ""
            return f"ERROR: {path} does not exist. Nearby: {siblings or 'nothing'}"
        lines = target.read_text(errors="replace").splitlines()
        chunk = lines[offset: offset + limit]
        body = "\n".join(f"{i + offset + 1}\t{line}" for i, line in enumerate(chunk))
        header = f"{path} ({len(lines)} lines, showing {offset + 1}-{offset + len(chunk)})\n"
        return (header + body)[:MAX_READ_CHARS]

    def write_file(path: str, content: str) -> str:
        target = _resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Wrote {len(content)} chars to {path}"

    def edit_file(path: str, old: str, new: str) -> str:
        target = _resolve(path)
        if not target.exists():
            return f"ERROR: {path} does not exist"
        text = target.read_text()
        count = text.count(old)
        if count == 0:
            return f"ERROR: old string not found in {path}"
        if count > 1:
            return f"ERROR: old string appears {count} times in {path}; make it unique"
        target.write_text(text.replace(old, new, 1))
        return f"Edited {path}"

    def glob_files(pattern: str = "**/*") -> str:
        hits = [
            str(p.relative_to(root))
            for p in sorted(root.rglob("*"))
            if p.is_file() and fnmatch.fnmatch(str(p.relative_to(root)), pattern)
            and not any(part.startswith(".") or part == "__pycache__" for part in p.parts)
        ][:200]
        return "\n".join(hits) or f"No files match {pattern!r}"

    def grep_files(pattern: str, glob: str = "**/*") -> str:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return f"ERROR: bad regex: {exc}"
        out: list[str] = []
        for p in sorted(root.rglob("*")):
            rel = str(p.relative_to(root))
            if not p.is_file() or not fnmatch.fnmatch(rel, glob):
                continue
            if any(part.startswith(".") or part == "__pycache__" for part in p.parts):
                continue
            try:
                for n, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
                    if rx.search(line):
                        out.append(f"{rel}:{n}: {line.strip()[:200]}")
                        if len(out) >= 100:
                            return "\n".join(out) + "\n… (capped at 100 matches)"
            except OSError:
                continue
        return "\n".join(out) or f"No matches for /{pattern}/"

    return [
        Tool("read_file", "Read a file from the workspace with line numbers. Use offset/limit for large files.",
             {"type": "object", "properties": {
                 "path": {"type": "string"},
                 "offset": {"type": "integer"},
                 "limit": {"type": "integer"}},
              "required": ["path"]},
             read_file, capability="read"),
        Tool("write_file", "Create or overwrite a file in the workspace.",
             {"type": "object", "properties": {
                 "path": {"type": "string"}, "content": {"type": "string"}},
              "required": ["path", "content"]},
             write_file, capability="write"),
        Tool("edit_file", "Replace one unique occurrence of a string in a file.",
             {"type": "object", "properties": {
                 "path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}},
              "required": ["path", "old", "new"]},
             edit_file, capability="write"),
        Tool("glob", "List workspace files matching a glob pattern.",
             {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": []},
             glob_files, capability="read"),
        Tool("grep", "Regex-search file contents across the workspace.",
             {"type": "object", "properties": {
                 "pattern": {"type": "string"}, "glob": {"type": "string"}},
              "required": ["pattern"]},
             grep_files, capability="read"),
    ]
