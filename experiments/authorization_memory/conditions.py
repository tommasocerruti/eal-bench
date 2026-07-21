from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from domains.base import MemoryArchitecture


class ExecutorEvidence(str, Enum):
    EMPTY = "empty"
    FULL_HISTORY = "full_history"
    MEMORY = "memory"


class UpdateStrategy(str, Enum):
    NONE = "none"
    ONE_SHOT = "one_shot"
    INCREMENTAL = "incremental"


@dataclass(frozen=True)
class ConditionSpec:
    condition_id: str
    evidence: ExecutorEvidence
    architecture: MemoryArchitecture | None
    update_strategy: UpdateStrategy
    writer_required: bool = False
    faithful: bool = False


CONDITION_SPECS = (
    ConditionSpec(
        "empty_memory",
        ExecutorEvidence.EMPTY,
        None,
        UpdateStrategy.NONE,
    ),
    ConditionSpec(
        "full_history",
        ExecutorEvidence.FULL_HISTORY,
        None,
        UpdateStrategy.NONE,
    ),
    ConditionSpec(
        "faithful_text",
        ExecutorEvidence.MEMORY,
        MemoryArchitecture.FREE_TEXT,
        UpdateStrategy.NONE,
        faithful=True,
    ),
    ConditionSpec(
        "faithful_typed",
        ExecutorEvidence.MEMORY,
        MemoryArchitecture.TYPED,
        UpdateStrategy.NONE,
        faithful=True,
    ),
    ConditionSpec(
        "one_shot_text",
        ExecutorEvidence.MEMORY,
        MemoryArchitecture.FREE_TEXT,
        UpdateStrategy.ONE_SHOT,
        writer_required=True,
    ),
    ConditionSpec(
        "one_shot_typed",
        ExecutorEvidence.MEMORY,
        MemoryArchitecture.TYPED,
        UpdateStrategy.ONE_SHOT,
        writer_required=True,
    ),
    ConditionSpec(
        "incremental_text",
        ExecutorEvidence.MEMORY,
        MemoryArchitecture.FREE_TEXT,
        UpdateStrategy.INCREMENTAL,
        writer_required=True,
    ),
    ConditionSpec(
        "incremental_typed",
        ExecutorEvidence.MEMORY,
        MemoryArchitecture.TYPED,
        UpdateStrategy.INCREMENTAL,
        writer_required=True,
    ),
)

_BY_ID = {condition.condition_id: condition for condition in CONDITION_SPECS}


def get_condition(condition_id: str) -> ConditionSpec:
    try:
        return _BY_ID[condition_id]
    except KeyError as exc:
        raise ValueError(f"unknown condition: {condition_id}") from exc


def condition_ids() -> tuple[str, ...]:
    return tuple(_BY_ID)
