from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .schemas import MemoryArchitecture, MemoryOrigin


class UpdateStrategy(str, Enum):
    NONE = "none"
    ONE_SHOT = "one_shot"
    INCREMENTAL = "incremental"


class ExecutorEvidence(str, Enum):
    EMPTY = "empty"
    FULL_HISTORY = "full_history"
    MEMORY = "memory"


@dataclass(frozen=True)
class ConditionSpec:
    condition_id: str
    label: str
    origin: MemoryOrigin
    architecture: MemoryArchitecture | None
    update_strategy: UpdateStrategy
    executor_evidence: ExecutorEvidence
    writer_required: bool


CONDITION_SPECS = (
    ConditionSpec(
        "empty_memory",
        "Empty memory",
        MemoryOrigin.EMPTY,
        None,
        UpdateStrategy.NONE,
        ExecutorEvidence.EMPTY,
        False,
    ),
    ConditionSpec(
        "full_history",
        "Full history",
        MemoryOrigin.FULL_HISTORY,
        None,
        UpdateStrategy.NONE,
        ExecutorEvidence.FULL_HISTORY,
        False,
    ),
    ConditionSpec(
        "faithful_text",
        "Faithful free-text memory",
        MemoryOrigin.FAITHFUL,
        MemoryArchitecture.FREE_TEXT,
        UpdateStrategy.NONE,
        ExecutorEvidence.MEMORY,
        False,
    ),
    ConditionSpec(
        "faithful_typed",
        "Faithful typed memory",
        MemoryOrigin.FAITHFUL,
        MemoryArchitecture.TYPED,
        UpdateStrategy.NONE,
        ExecutorEvidence.MEMORY,
        False,
    ),
    ConditionSpec(
        "one_shot_text",
        "One-shot free-text memory",
        MemoryOrigin.WRITER,
        MemoryArchitecture.FREE_TEXT,
        UpdateStrategy.ONE_SHOT,
        ExecutorEvidence.MEMORY,
        True,
    ),
    ConditionSpec(
        "one_shot_typed",
        "One-shot typed memory",
        MemoryOrigin.WRITER,
        MemoryArchitecture.TYPED,
        UpdateStrategy.ONE_SHOT,
        ExecutorEvidence.MEMORY,
        True,
    ),
    ConditionSpec(
        "incremental_text",
        "Incremental free-text memory",
        MemoryOrigin.WRITER,
        MemoryArchitecture.FREE_TEXT,
        UpdateStrategy.INCREMENTAL,
        ExecutorEvidence.MEMORY,
        True,
    ),
    ConditionSpec(
        "incremental_typed",
        "Incremental typed memory",
        MemoryOrigin.WRITER,
        MemoryArchitecture.TYPED,
        UpdateStrategy.INCREMENTAL,
        ExecutorEvidence.MEMORY,
        True,
    ),
)

_BY_ID = {condition.condition_id: condition for condition in CONDITION_SPECS}


def get_condition(condition_id: str) -> ConditionSpec:
    try:
        return _BY_ID[condition_id]
    except KeyError as exc:
        raise ValueError(f"unknown condition: {condition_id}") from exc
