"""Runtime configuration — loaded from environment with sane defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    model: str
    max_iterations: int
    max_tool_calls_per_turn: int
    history_max_turns: int
    data_dir: Path
    corpus_dir: Path
    trace_dir: Path
    chroma_dir: Path
    notes_db: Path
    collection_name: str
    log_level: str

    @classmethod
    def load(cls) -> "Settings":
        data_dir = Path(_env("ATLAS_DATA_DIR", "./data")).resolve()
        return cls(
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            model=_env("ATLAS_MODEL", "claude-haiku-4-5"),
            max_iterations=_env_int("ATLAS_MAX_ITERATIONS", 8),
            max_tool_calls_per_turn=_env_int("ATLAS_MAX_TOOL_CALLS_PER_TURN", 5),
            history_max_turns=_env_int("ATLAS_HISTORY_MAX_TURNS", 20),
            data_dir=data_dir,
            corpus_dir=Path(_env("ATLAS_CORPUS_DIR", "../tutorial")).resolve(),
            trace_dir=Path(_env("ATLAS_TRACE_DIR", str(data_dir / "traces"))).resolve(),
            chroma_dir=data_dir / "chroma",
            notes_db=data_dir / "notes.sqlite",
            collection_name="atlas_kb",
            log_level=_env("ATLAS_LOG_LEVEL", "INFO"),
        )


settings = Settings.load()
