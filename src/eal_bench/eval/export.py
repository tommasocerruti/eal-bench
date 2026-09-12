"""Write trials to JSONL and read outcomes back.

Lets a consumer that is not written in Python call its own model and return scores,
without importing the interface.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .scoring import TrialOutcome
from .trials import Trial, TrialTruth

__all__ = ["TRACKS", "build_track", "read_outcomes", "write_outcomes", "write_trials"]

TRACKS = ("controls",)


def build_track(track: str, domain_id: str, **kwargs: Any) -> list[tuple[Trial, TrialTruth]]:
    if track == "controls":
        from .controls import build_control_trials

        return build_control_trials(domain_id, **kwargs)
    raise ValueError(f"unknown track {track!r}; available: {', '.join(TRACKS)}")


def write_trials(path: str | Path, pairs: Sequence[tuple[Trial, TrialTruth]]) -> int:
    """One JSON object per line. Oracle state is never written to this file."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for trial, _ in pairs:
            handle.write(json.dumps(trial.to_dict(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return len(pairs)


def write_outcomes(path: str | Path, outcomes: Iterable[TrialOutcome]) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("w", encoding="utf-8") as handle:
        for outcome in outcomes:
            handle.write(json.dumps(outcome.to_dict(), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            written += 1
    return written


def read_outcomes(path: str | Path) -> list[TrialOutcome]:
    rows = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(TrialOutcome(**json.loads(line)))
    return rows
