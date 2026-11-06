"""Document loading, chunking, and ingestion into the vector store.

Strategy: walk the corpus directory for `.md`/`.markdown`/`.txt`, split
each file by H1/H2 headings into sections, then group paragraphs within
a section into ~800-character chunks with ~100-character overlap.
Metadata carries the source filename and section title so retrieval can
cite back."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .vectorstore import VectorStore

CHUNK_TARGET = 800
CHUNK_OVERLAP = 100
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}

# split on lines starting with `#` or `##` while keeping the heading line
_SECTION_SPLIT = re.compile(r"(?m)^(#{1,2}\s+.+)$")


@dataclass
class Chunk:
    id: str
    text: str
    source: str
    section: str


def _split_sections(md: str) -> list[tuple[str, str]]:
    """Return [(section_title, body), ...]. Content before the first
    heading is filed under 'preamble'."""
    parts = _SECTION_SPLIT.split(md)
    if len(parts) == 1:
        return [("preamble", md.strip())]
    sections: list[tuple[str, str]] = []
    if parts[0].strip():
        sections.append(("preamble", parts[0].strip()))
    # parts alternates: [pre, heading, body, heading, body, ...]
    for i in range(1, len(parts), 2):
        heading = parts[i].strip().lstrip("#").strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            sections.append((heading, body))
    return sections


def _chunk_text(text: str, target: int = CHUNK_TARGET, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Greedy paragraph-aware chunker. Joins paragraphs until target,
    then carries the last `overlap` chars into the next chunk."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if not buf:
            buf = p
        elif len(buf) + 1 + len(p) <= target:
            buf = f"{buf}\n\n{p}"
        else:
            chunks.append(buf)
            tail = buf[-overlap:] if overlap and len(buf) > overlap else ""
            buf = (tail + "\n\n" + p).strip() if tail else p
    if buf:
        chunks.append(buf)
    # Hard-split any single paragraph that blew past target.
    final: list[str] = []
    for c in chunks:
        if len(c) <= target * 1.5:
            final.append(c)
            continue
        for i in range(0, len(c), target - overlap):
            final.append(c[i : i + target])
    return final


def _iter_files(corpus_dir: Path) -> Iterable[Path]:
    if not corpus_dir.exists():
        return
    for p in sorted(corpus_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            yield p


def build_chunks(corpus_dir: Path) -> list[Chunk]:
    out: list[Chunk] = []
    for path in _iter_files(corpus_dir):
        rel = path.relative_to(corpus_dir).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for section_title, body in _split_sections(text):
            for piece in _chunk_text(body):
                cid = hashlib.sha1(f"{rel}::{section_title}::{piece[:64]}".encode()).hexdigest()[:16]
                out.append(Chunk(id=cid, text=piece, source=rel, section=section_title))
    return out


def ingest(corpus_dir: Path, store: "VectorStore | None" = None, *, reset: bool = False) -> int:
    if store is None:
        from .vectorstore import VectorStore as _VS
        store = _VS()
    if reset:
        store.reset()
    chunks = build_chunks(corpus_dir)
    if not chunks:
        return 0
    store.upsert(
        ids=[c.id for c in chunks],
        docs=[c.text for c in chunks],
        metas=[{"source": c.source, "section": c.section} for c in chunks],
    )
    return len(chunks)
