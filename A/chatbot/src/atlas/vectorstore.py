"""Chroma persistent client. Wraps just the calls we use so the rest of
the codebase doesn't depend on Chroma's API directly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import settings


@dataclass
class Hit:
    text: str
    source: str
    section: str
    score: float  # cosine distance; lower is better


class VectorStore:
    def __init__(self) -> None:
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(
            path=str(settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        # Default embedding function: all-MiniLM-L6-v2 (downloaded on first use).
        self.collection = self.client.get_or_create_collection(
            name=settings.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, ids: list[str], docs: list[str], metas: list[dict[str, Any]]) -> None:
        if not ids:
            return
        self.collection.upsert(ids=ids, documents=docs, metadatas=metas)

    def count(self) -> int:
        return self.collection.count()

    def query(self, text: str, k: int = 5) -> list[Hit]:
        if self.count() == 0:
            return []
        res = self.collection.query(query_texts=[text], n_results=k)
        out: list[Hit] = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            out.append(
                Hit(
                    text=doc,
                    source=str((meta or {}).get("source", "?")),
                    section=str((meta or {}).get("section", "")),
                    score=float(dist),
                )
            )
        return out

    def reset(self) -> None:
        try:
            self.client.delete_collection(settings.collection_name)
        except Exception:
            pass
        self.collection = self.client.get_or_create_collection(
            name=settings.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
