"""Append-only JSONL call log: one JSON object per line (input, output, usage, latency,
attempts, error). A lock serializes writes so concurrent calls don't interleave lines."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any


class JSONLLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    async def log(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            # Synchronous append under the lock; lines are small and the OS buffers them.
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
