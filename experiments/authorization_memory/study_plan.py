from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from domains.base import AuthorizationMemoryDomain, BenchmarkProbe
from experiments.authorization_memory.schemas import (
    FrozenEvidence,
    MemoryArtifact,
)


@dataclass(frozen=True)
class PressureSpec:
    pressure_id: str
    placement: str
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    challenge_pressure_id: str | None = None

    def validate(self) -> None:
        for label, value in (
            ("pressure_id", self.pressure_id),
            ("placement", self.placement),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be a non-empty string")
        if not isinstance(self.text, str):
            raise ValueError("pressure text must be a string")
        if self.challenge_pressure_id is not None and (
            not isinstance(self.challenge_pressure_id, str)
            or not self.challenge_pressure_id.strip()
        ):
            raise ValueError(
                "challenge pressure ID must be null or a non-empty string"
            )


@dataclass(frozen=True)
class ExecutorContext:
    identity: str | None = None
    operational: str | None = None
    sections: Mapping[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        for label, value in (
            ("identity", self.identity),
            ("operational", self.operational),
        ):
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"{label} context must be null or non-empty")
        if any(
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(value, str)
            or not value.strip()
            for name, value in self.sections.items()
        ):
            raise ValueError("executor context sections must be non-empty strings")


@dataclass(frozen=True)
class ExecutorJob:
    job_id: str
    case: Any
    probe: BenchmarkProbe
    evidence: FrozenEvidence
    context: ExecutorContext = field(default_factory=ExecutorContext)
    pressure_id: str | None = None
    oracle_block_index: int | None = None
    messages: tuple[Mapping[str, Any], ...] | None = None
    challenge_metadata: Mapping[str, Any] | None = None
    challenge_context: Any | None = None
    executor_target_id: str | None = None
    executor_run_id: int | None = None
    executor_seed: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def validate(self, domain: AuthorizationMemoryDomain) -> None:
        if not self.job_id.strip():
            raise ValueError("executor job ID must not be empty")
        if self.oracle_block_index is not None and (
            isinstance(self.oracle_block_index, bool)
            or not isinstance(self.oracle_block_index, int)
            or self.oracle_block_index < 0
        ):
            raise ValueError(
                f"{self.job_id}: oracle block index must be non-negative"
            )
        self.context.validate()
        if self.evidence.domain_id != domain.domain_id:
            raise ValueError(f"{self.job_id}: evidence belongs to another domain")
        if self.evidence.case_id != domain.corpus.case_id(self.case):
            raise ValueError(f"{self.job_id}: evidence belongs to another case")
        if self.messages is not None:
            if not self.messages:
                raise ValueError(f"{self.job_id}: explicit messages must not be empty")
            if any(
                not isinstance(message, Mapping)
                or not isinstance(message.get("role"), str)
                or not isinstance(message.get("content"), str)
                for message in self.messages
            ):
                raise ValueError(
                    f"{self.job_id}: explicit messages must use chat role/content objects"
                )
        if self.challenge_metadata is not None and not isinstance(
            self.challenge_metadata,
            Mapping,
        ):
            raise ValueError(
                f"{self.job_id}: challenge metadata must be null or an object"
            )
        if self.challenge_context is not None:
            from .challenges import validate_challenge_context

            validate_challenge_context(
                domain,
                self.case,
                self.probe,
                self.challenge_context,
                through_block_index=self.oracle_block_index,
            )
        route_values = (
            self.executor_target_id,
            self.executor_run_id,
            self.executor_seed,
        )
        if any(value is not None for value in route_values) and any(
            value is None for value in route_values
        ):
            raise ValueError(
                f"{self.job_id}: frozen executor route requires target, run, and seed"
            )
        if self.executor_target_id is not None and (
            not isinstance(self.executor_target_id, str)
            or not self.executor_target_id.strip()
        ):
            raise ValueError(
                f"{self.job_id}: executor target must be a non-empty string"
            )
        for label, value in (
            ("executor run", self.executor_run_id),
            ("executor seed", self.executor_seed),
        ):
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{self.job_id}: {label} must be a non-negative integer"
                )


JobBuilder = Callable[
    [
        AuthorizationMemoryDomain,
        Sequence[Any],
        Sequence[FrozenEvidence],
        Mapping[str, Any],
    ],
    Sequence[ExecutorJob],
]
PlanFinalizer = Callable[
    [
        AuthorizationMemoryDomain,
        Sequence[Any],
        Sequence[Any],
        Sequence[Any],
        Sequence[Any],
        Sequence[FrozenEvidence],
        Mapping[str, Any],
    ],
    "StudyFinalization",
]


@dataclass(frozen=True)
class WriterRunBundle:
    memories: tuple[MemoryArtifact, ...] = ()
    attempts: tuple[Any, ...] = ()
    states: tuple[Any, ...] = ()
    evidence: tuple[FrozenEvidence, ...] = ()
    contexts: tuple[Any, ...] = ()


@dataclass(frozen=True)
class StudyExpansion:
    jobs: tuple[ExecutorJob, ...] = ()
    additional_memories: tuple[MemoryArtifact, ...] = ()
    additional_evidence: tuple[FrozenEvidence, ...] = ()
    additional_contexts: tuple[Any, ...] = ()
    artifact_rows: Mapping[str, Sequence[Any]] = field(default_factory=dict)
    manifest_metadata: Mapping[str, Any] = field(default_factory=dict)


PostWriterBuilder = Callable[
    [
        AuthorizationMemoryDomain,
        Sequence[Any],
        WriterRunBundle,
        Mapping[str, Any],
    ],
    StudyExpansion,
]
PostWriterReviewer = Callable[
    [
        Any,
        AuthorizationMemoryDomain,
        Sequence[Any],
        WriterRunBundle,
        Mapping[str, Any],
    ],
    StudyExpansion,
]


@dataclass(frozen=True)
class StudyFinalization:
    artifact_rows: Mapping[str, Sequence[Any]] = field(default_factory=dict)
    additional_evidence: tuple[FrozenEvidence, ...] = ()
    replace_evidence: bool = False
    manifest_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StudyPlan:
    study_id: str
    writer_only: bool = False
    executor_only: bool = False
    jobs: tuple[ExecutorJob, ...] = ()
    job_builder: JobBuilder | None = None
    writer_chains: tuple[Any, ...] = ()
    controlled_memories: tuple[Any, ...] = ()
    source_evidence: tuple[FrozenEvidence, ...] = ()
    validation_evidence: tuple[FrozenEvidence, ...] = ()
    validation_writer_bundles: tuple[WriterRunBundle, ...] = ()
    pressure_specs: tuple[PressureSpec, ...] = ()
    artifact_schemas: Mapping[str, int] = field(default_factory=dict)
    artifact_rows: Mapping[str, Sequence[Any]] = field(default_factory=dict)
    artifact_paths: Mapping[str, str] = field(default_factory=dict)
    persist_empty_artifacts: tuple[str, ...] = ()
    post_writer_builder: PostWriterBuilder | None = None
    post_writer_reviewer: PostWriterReviewer | None = None
    finalizer: PlanFinalizer | None = None
    file_aliases: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    allow_empty_jobs: bool = False

    def validate_definition(self) -> None:
        if not self.study_id.strip():
            raise ValueError("study plan ID must not be empty")
        if self.writer_only and self.executor_only:
            raise ValueError("a study plan cannot be both writer-only and executor-only")
        pressure_ids = [pressure.pressure_id for pressure in self.pressure_specs]
        if len(pressure_ids) != len(set(pressure_ids)):
            raise ValueError("study pressure IDs must be unique")
        for pressure in self.pressure_specs:
            pressure.validate()
        if self.executor_only and self.writer_chains:
            raise ValueError("executor-only plans cannot contain writer chains")
        if (
            self.writer_chains
            and self.job_builder is not None
            and not self.validation_evidence
        ):
            raise ValueError(
                "writer-backed deferred jobs require offline validation evidence"
            )
        for name, version in self.artifact_schemas.items():
            if (
                not isinstance(name, str)
                or not name.strip()
                or isinstance(version, bool)
                or not isinstance(version, int)
                or version < 1
            ):
                raise ValueError(
                    "artifact schemas must map non-empty names to positive versions"
                )
        for alias, target in self.file_aliases.items():
            if (
                not isinstance(alias, str)
                or not alias.strip()
                or not isinstance(target, str)
                or not target.strip()
            ):
                raise ValueError("file aliases must map non-empty names")
        for name, path in self.artifact_paths.items():
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(path, str)
                or not path.strip()
                or Path(path).name != path
                or not path.endswith(".jsonl")
            ):
                raise ValueError(
                    "artifact paths must map names to local JSONL filenames"
                )
        declared_artifacts = set(self.artifact_schemas)
        unknown_empty = sorted(
            set(self.persist_empty_artifacts) - declared_artifacts
        )
        if unknown_empty:
            raise ValueError(
                "empty artifact persistence requires declared schemas: "
                + ", ".join(unknown_empty)
            )
        if (
            self.post_writer_builder is not None
            or self.post_writer_reviewer is not None
        ) and not self.writer_chains and not (
            self.metadata.get("post_writer_source_only")
            and self.source_evidence
            and self.validation_writer_bundles
        ):
            raise ValueError(
                "post-writer stages require writer chains or a frozen source-only pool"
            )
        if (
            self.post_writer_reviewer is not None
            and self.post_writer_builder is None
        ):
            raise ValueError(
                "live post-writer reviewers require an offline builder"
            )

    def validate(
        self,
        domain: AuthorizationMemoryDomain,
        cases: Sequence[Any],
        options: Mapping[str, Any],
        *,
        generated_evidence: Sequence[FrozenEvidence] = (),
        expansion_jobs: Sequence[ExecutorJob] = (),
    ) -> tuple[ExecutorJob, ...]:
        self.validate_definition()
        pressure_ids = [pressure.pressure_id for pressure in self.pressure_specs]
        available_evidence = (*self.source_evidence, *generated_evidence)
        base_jobs = (
            tuple(self.job_builder(domain, cases, available_evidence, options))
            if self.job_builder is not None
            else self.jobs
        )
        jobs = (*base_jobs, *expansion_jobs)
        job_ids = [job.job_id for job in jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("study executor job IDs must be unique")
        known_pressures = set(pressure_ids)
        for job in jobs:
            job.validate(domain)
            if job.pressure_id is not None and job.pressure_id not in known_pressures:
                raise ValueError(
                    f"{job.job_id}: unknown pressure {job.pressure_id!r}"
                )
        if self.writer_only and jobs:
            raise ValueError("writer-only plans cannot contain executor jobs")
        if (
            not self.writer_only
            and not jobs
            and not self.writer_chains
            and not self.allow_empty_jobs
        ):
            raise ValueError("a study plan must contain writer chains or executor jobs")
        return jobs
