from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from domains.base import AuthorizationMemoryDomain

from .pipeline import _study_job_messages, planned_study_job_identity
from .study_plan import ExecutorJob


@dataclass(frozen=True)
class PlannedExecutorCall:
    job: ExecutorJob
    target_id: str
    executor_run_id: int
    executor_seed: int
    trial_id: str
    call_id: str
    executor: Any
    messages: tuple[Mapping[str, Any], ...]


def planned_executor_calls(
    domain: AuthorizationMemoryDomain,
    jobs: Sequence[ExecutorJob],
    *,
    study_id: str,
    executor_task: str,
    executor_targets: Sequence[str],
    executor_runs: int,
    seed: int,
    presentation: Any,
    config: Any,
    pressure_specs: Sequence[Any],
) -> dict[str, PlannedExecutorCall]:
    pressure_by_id = {item.pressure_id: item for item in pressure_specs}
    routed: list[tuple[ExecutorJob, str, int, int]] = []
    for job in jobs:
        if job.executor_target_id is None:
            for target_id in executor_targets:
                for run_id in range(executor_runs):
                    routed.append((job, target_id, run_id, seed + run_id))
        else:
            assert job.executor_run_id is not None
            assert job.executor_seed is not None
            routed.append(
                (
                    job,
                    job.executor_target_id,
                    job.executor_run_id,
                    job.executor_seed,
                )
            )
    planned: dict[str, PlannedExecutorCall] = {}
    for job, target_id, run_id, executor_seed in routed:
        identity = planned_study_job_identity(
            domain,
            job,
            study_id=study_id,
            executor_task=executor_task,
            target_id=target_id,
            executor_run_id=run_id,
            seed=executor_seed,
            presentation=presentation,
            config=config,
        )
        pressure = (
            pressure_by_id[job.pressure_id]
            if job.pressure_id is not None
            else None
        )
        item = PlannedExecutorCall(
            job=job,
            target_id=target_id,
            executor_run_id=run_id,
            executor_seed=executor_seed,
            trial_id=identity["trial_id"],
            call_id=identity["call_id"],
            executor=identity["executor"],
            messages=tuple(
                _study_job_messages(
                    domain,
                    job,
                    presentation=presentation,
                    pressure=pressure,
                )
            ),
        )
        if item.call_id in planned:
            raise ValueError(f"duplicate planned call ID: {item.call_id}")
        planned[item.call_id] = item
    return planned


def executor_plan_rows(
    planned: Mapping[str, PlannedExecutorCall],
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "schema_version": 1,
            "call_id": item.call_id,
            "trial_id": item.trial_id,
            "job_id": item.job.job_id,
            "case_id": item.job.evidence.case_id,
            "probe_id": item.job.probe.probe_id,
            "condition_id": item.job.evidence.condition_id,
            "evidence_id": item.job.evidence.evidence_id,
            "memory_id": item.job.evidence.memory_id,
            "executor_target_id": item.target_id,
            "executor_run_id": item.executor_run_id,
            "executor_seed": item.executor_seed,
            "pressure_id": item.job.pressure_id,
            "oracle_block_index": item.job.oracle_block_index,
            "messages": list(item.messages),
            "executor": item.executor,
            "job_metadata": dict(item.job.metadata),
        }
        for item in planned.values()
    )
