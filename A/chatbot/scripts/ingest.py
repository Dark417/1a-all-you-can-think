"""Standalone ingest entry point.

Equivalent to `python -m atlas ingest`. Useful in CI or as a one-liner."""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from atlas.config import settings  # noqa: E402
from atlas.rag import ingest  # noqa: E402


def main() -> int:
    target = settings.corpus_dir
    if not target.exists():
        print(f"corpus directory not found: {target}", file=sys.stderr)
        return 1
    n = ingest(target, reset=True)
    print(f"ingested {n} chunks from {target}")
    print(f"chroma stored at {settings.chroma_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
