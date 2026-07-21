#!/usr/bin/env python3
"""Score memory artifacts or per-block retained-state observations against the ledger."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from domains import get_domain
from domains.base import FidelityReport, MemoryArchitecture

from .common import load_memory_artifacts


DEFAULT_GROUPS = (
    "condition_id",
    "memory_implementation_id",
    "memory_implementation_hash",
    "writer_provider",
    "writer_target_id",
    "writer_requested_model",
    "writer_model",
    "block_index",
)
GROUP_FIELDS = frozenset(
    {
        "case_id",
        "condition_id",
        "writer_model",
        "writer_provider",
        "writer_target_id",
        "writer_requested_model",
        "memory_implementation_id",
        "memory_implementation_hash",
        "block_index",
        "architecture",
        "origin",
        "attempt_status",
        "accepted_this_block",
        "empty",
        "retained",
    }
)
FIDELITY_ERRORS = (
    "omission",
    "broadening",
    "narrowing",
    "contradiction",
    "stale_retention",
    "extra_record",
    "missing_record",
)
AUTHORIZATION_CONSEQUENCES = (
    "exact",
    "overgrant",
    "undergrant",
    "mixed",
)
MEMORY_UPDATE_STATUSES = frozenset(
    {
        "accepted",
        "missing_tool_call",
        "multiple_tool_calls",
        "unexpected_tool",
        "malformed_arguments",
        "invalid_payload",
        "unknown_source_id",
        "capacity_overflow",
        "writer_error",
        "no_change",
    }
)


class MemoryOrigin(str, Enum):
    EMPTY = "empty"
    FULL_HISTORY = "full_history"
    FAITHFUL = "faithful"
    WRITER = "writer"
    CONTROLLED = "controlled"


@dataclass(frozen=True)
class MemoryArtifact:
    memory_id: str
    parent_memory_id: str | None
    chain_id: str
    domain_id: str
    case_id: str
    condition_id: str
    block_index: int
    writer: Mapping[str, Any] | None
    architecture: MemoryArchitecture
    origin: MemoryOrigin
    payload: str | Mapping[str, Any]
    reference_tokens: int
    reference_tokenizer: str
    content_hash: str
    profile_id: str | None = None
    memory_implementation_id: str | None = None
    memory_implementation_hash: str | None = None

    @property
    def writer_model(self) -> str | None:
        if self.writer is None:
            return None
        value = self.writer.get("resolved_model")
        return str(value) if value is not None else None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MemoryArtifact:
        writer = data.get("writer")
        if writer is not None and not isinstance(writer, Mapping):
            raise ValueError("writer must be an object or null")
        return cls(
            memory_id=str(data["memory_id"]),
            parent_memory_id=data.get("parent_memory_id"),
            chain_id=str(data["chain_id"]),
            domain_id=str(data["domain_id"]),
            case_id=str(data["case_id"]),
            condition_id=str(data["condition_id"]),
            block_index=int(data["block_index"]),
            writer=writer,
            architecture=MemoryArchitecture(data["architecture"]),
            origin=MemoryOrigin(data["origin"]),
            payload=data["payload"],
            reference_tokens=int(data["reference_tokens"]),
            reference_tokenizer=str(data["reference_tokenizer"]),
            content_hash=str(data["content_hash"]),
            profile_id=data.get("profile_id"),
            memory_implementation_id=data.get("memory_implementation_id"),
            memory_implementation_hash=data.get("memory_implementation_hash"),
        )


@dataclass(frozen=True)
class AnnotationState:
    state: Any | None
    source_content_hash: str | None
    reason: str | None


@dataclass(frozen=True)
class MemoryObservation:
    observation_id: str
    case_id: str
    condition_id: str
    chain_id: str
    observed_block_index: int
    current_memory_id: str | None
    current_content_hash: str | None
    retained_from_block_index: int | None
    attempt_id: str
    attempt_status: str
    accepted_this_block: bool
    empty: bool
    memory_implementation_id: str | None = None
    memory_implementation_hash: str | None = None

    @classmethod
    def from_memory_state(
        cls,
        data: Mapping[str, Any],
        *,
        artifacts: Mapping[str, MemoryArtifact],
        attempts: Mapping[str, Mapping[str, Any]],
        domain: Any,
    ) -> MemoryObservation:
        if data.get("schema_version") != 3:
            raise ValueError(
                f"unsupported memory-state schema: {data.get('schema_version')!r}"
            )
        required = {
            "state_id",
            "logical_update_id",
            "attempt_ids",
            "case_id",
            "condition_id",
            "block_index",
            "profile_id",
            "current_memory_id",
            "status",
            "changed",
        }
        missing = required - set(data)
        if missing:
            raise ValueError(f"missing memory-state fields: {sorted(missing)}")
        attempt_ids = data["attempt_ids"]
        if (
            not isinstance(attempt_ids, list)
            or not attempt_ids
            or not all(isinstance(item, str) and item for item in attempt_ids)
        ):
            raise ValueError("attempt_ids must be a non-empty list of strings")
        try:
            update_attempts = [attempts[attempt_id] for attempt_id in attempt_ids]
        except KeyError as exc:
            raise ValueError(
                f"memory state references unknown attempt {exc.args[0]!r}"
            ) from exc
        for index, attempt in enumerate(update_attempts, start=1):
            if (
                attempt.get("logical_update_id") != data["logical_update_id"]
                or attempt.get("case_id") != data["case_id"]
                or attempt.get("condition_id") != data["condition_id"]
                or attempt.get("block_index") != data["block_index"]
                or attempt.get("profile_id") != data["profile_id"]
                or attempt.get("attempt_index") != index
            ):
                raise ValueError(
                    f"memory-state attempt linkage is inconsistent: {attempt_ids[index - 1]}"
                )
        final_attempt = update_attempts[-1]
        final_status = final_attempt.get("status")
        if not isinstance(final_status, str) or not final_status:
            raise ValueError("final memory attempt has no status")
        state_status = data["status"]
        expected_state_status = (
            final_status
            if final_status in {"accepted", "no_change"}
            else "retained_after_failed_update"
        )
        if state_status != expected_state_status:
            raise ValueError(
                f"memory state status {state_status!r} disagrees with "
                f"final attempt {final_status!r}"
            )
        if not isinstance(data["changed"], bool):
            raise ValueError("memory state changed must be boolean")
        if data["changed"] != any(
            attempt.get("changed") is True for attempt in update_attempts
        ):
            raise ValueError("memory state changed flag disagrees with its attempts")

        current_memory_id = data["current_memory_id"]
        artifact = None
        if current_memory_id is not None:
            if not isinstance(current_memory_id, str) or not current_memory_id:
                raise ValueError("current_memory_id must be a string or null")
            try:
                artifact = artifacts[current_memory_id]
            except KeyError as exc:
                raise ValueError(
                    f"memory state references unknown memory {current_memory_id!r}"
                ) from exc
            if (
                artifact.case_id != data["case_id"]
                or artifact.condition_id != data["condition_id"]
                or (
                    artifact.profile_id is not None
                    and artifact.profile_id != data["profile_id"]
                )
            ):
                raise ValueError("memory state and current artifact identity differ")
            chain_id = artifact.chain_id
            current_hash = artifact.content_hash
            retained_block = artifact.block_index
            empty = _artifact_is_empty(artifact, domain)
        else:
            chain_id = f"profile:{data['profile_id']}"
            current_hash = None
            retained_block = None
            empty = True
        return cls(
            observation_id=str(data["state_id"]),
            case_id=str(data["case_id"]),
            condition_id=str(data["condition_id"]),
            chain_id=chain_id,
            observed_block_index=int(data["block_index"]),
            current_memory_id=current_memory_id,
            current_content_hash=current_hash,
            retained_from_block_index=retained_block,
            attempt_id=attempt_ids[-1],
            attempt_status=final_status,
            accepted_this_block=state_status in {"accepted", "no_change"},
            empty=empty,
            memory_implementation_id=data.get("memory_implementation_id"),
            memory_implementation_hash=data.get("memory_implementation_hash"),
        )


@dataclass(frozen=True)
class ScoredMemory:
    artifact: MemoryArtifact | None
    report: FidelityReport | None
    unscored_reason: str | None = None
    observation: MemoryObservation | None = None
    writer_model_override: str | None = None
    architecture_override: MemoryArchitecture | None = None
    origin_override: MemoryOrigin | None = None

    @property
    def case_id(self) -> str:
        if self.observation is not None:
            return self.observation.case_id
        assert self.artifact is not None
        return self.artifact.case_id

    @property
    def condition_id(self) -> str:
        if self.observation is not None:
            return self.observation.condition_id
        assert self.artifact is not None
        return self.artifact.condition_id

    @property
    def writer_model(self) -> str | None:
        if self.artifact is not None:
            return self.artifact.writer_model
        return self.writer_model_override

    @property
    def writer_provider(self) -> str | None:
        if self.artifact is None or self.artifact.writer is None:
            return None
        value = self.artifact.writer.get("provider")
        return str(value) if value is not None else None

    @property
    def writer_target_id(self) -> str | None:
        if self.artifact is None or self.artifact.writer is None:
            return None
        value = self.artifact.writer.get("target_id")
        return str(value) if value is not None else None

    @property
    def writer_requested_model(self) -> str | None:
        if self.artifact is None or self.artifact.writer is None:
            return None
        value = self.artifact.writer.get("requested_model")
        return str(value) if value is not None else None

    @property
    def memory_implementation_id(self) -> str | None:
        if self.artifact is not None:
            return self.artifact.memory_implementation_id
        if self.observation is not None:
            return self.observation.memory_implementation_id
        return None

    @property
    def memory_implementation_hash(self) -> str | None:
        if self.artifact is not None:
            return self.artifact.memory_implementation_hash
        if self.observation is not None:
            return self.observation.memory_implementation_hash
        return None

    @property
    def block_index(self) -> int:
        if self.observation is not None:
            return self.observation.observed_block_index
        assert self.artifact is not None
        return self.artifact.block_index

    @property
    def architecture(self) -> MemoryArchitecture:
        if self.artifact is not None:
            return self.artifact.architecture
        assert self.architecture_override is not None
        return self.architecture_override

    @property
    def origin(self) -> MemoryOrigin:
        if self.artifact is not None:
            return self.artifact.origin
        assert self.origin_override is not None
        return self.origin_override

    def value(self, field: str) -> Any:
        if field == "retained":
            value = bool(
                self.observation is not None
                and not self.observation.accepted_this_block
                and self.observation.current_memory_id is not None
            )
        elif field in {"attempt_status", "accepted_this_block", "empty"}:
            value = getattr(self.observation, field) if self.observation is not None else None
        else:
            value = getattr(self, field)
        return value.value if hasattr(value, "value") else value

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.artifact.memory_id if self.artifact is not None else None,
            "observation_id": (
                self.observation.observation_id if self.observation is not None else None
            ),
            "chain_id": (
                self.observation.chain_id
                if self.observation is not None
                else self.artifact.chain_id if self.artifact is not None else None
            ),
            "case_id": self.case_id,
            "condition_id": self.condition_id,
            "writer_model": self.writer_model,
            "writer_provider": self.writer_provider,
            "writer_target_id": self.writer_target_id,
            "writer_requested_model": self.writer_requested_model,
            "memory_implementation_id": self.memory_implementation_id,
            "memory_implementation_hash": self.memory_implementation_hash,
            "block_index": self.block_index,
            "architecture": self.architecture.value,
            "origin": self.origin.value,
            "attempt_status": self.value("attempt_status"),
            "accepted_this_block": self.value("accepted_this_block"),
            "empty": self.value("empty"),
            "retained": self.value("retained"),
            "retained_from_block_index": (
                self.observation.retained_from_block_index
                if self.observation is not None
                else None
            ),
            "scored": self.report is not None,
            "unscored_reason": self.unscored_reason,
            "fidelity": self.report.to_dict() if self.report is not None else None,
        }


def score_saved_memories(
    memories_path: Path,
    *,
    annotations_path: Path | None = None,
    observations_path: Path | None = None,
    corpus_version: str = "benchmark_v1",
    cases_path: Path | None = None,
    domain_id: str | None = None,
) -> tuple[ScoredMemory, ...]:
    """Join artifacts, observations, and blinded extractions to canonical snapshots."""

    if cases_path is not None:
        raise ValueError(
            "custom --cases paths are not supported by domain adapters; "
            "register a corpus version with the selected domain"
        )
    artifacts = _load_artifacts(
        memories_path,
        allow_empty=observations_path is not None,
        domain_id=domain_id,
    )
    resolved_domain_id = domain_id
    if resolved_domain_id is None and artifacts:
        resolved_domain_id = artifacts[0].domain_id
    if resolved_domain_id is None:
        raise ValueError("domain_id is required when the memory artifact file is empty")
    domain = get_domain(resolved_domain_id)
    cases = domain.corpus.load_cases(corpus_version)
    case_by_id = {domain.corpus.case_id(case): case for case in cases}
    annotations = (
        _load_annotation_states(annotations_path, domain)
        if annotations_path is not None
        else {}
    )
    artifact_by_id = {artifact.memory_id: artifact for artifact in artifacts}
    observations = (
        _load_observations(
            observations_path,
            artifacts=artifact_by_id,
            domain=domain,
        )
        if observations_path is not None
        else ()
    )
    observed_chains = {observation.chain_id for observation in observations}
    if observations:
        incremental_chains = {
            artifact.chain_id
            for artifact in artifacts
            if artifact.condition_id in {"incremental_text", "incremental_typed"}
        }
        missing_chains = incremental_chains - observed_chains
        if missing_chains:
            raise ValueError(
                "observations are missing incremental chains: "
                + ", ".join(sorted(missing_chains))
            )
        _validate_observation_sequences(
            observations,
            artifact_by_id,
            case_by_id,
            domain,
        )

    scored = []
    for artifact in artifacts:
        if artifact.chain_id in observed_chains:
            continue
        scored.append(
            _score_artifact(
                artifact,
                observed_block_index=artifact.block_index,
                observation=None,
                case_by_id=case_by_id,
                annotations=annotations,
                domain=domain,
            )
        )
    for observation in observations:
        case = case_by_id[observation.case_id]
        if observation.empty:
            report = domain.fidelity.compare(
                case,
                domain.memory.empty_typed(),
                through_block_index=observation.observed_block_index,
            )
            artifact = (
                artifact_by_id.get(observation.current_memory_id)
                if observation.current_memory_id is not None
                else None
            )
            writer_model, architecture = _observation_identity(observation, artifacts)
            scored.append(
                ScoredMemory(
                    artifact=artifact,
                    report=report,
                    observation=observation,
                    writer_model_override=(
                        writer_model if artifact is None else None
                    ),
                    architecture_override=(
                        architecture if artifact is None else None
                    ),
                    origin_override=(
                        MemoryOrigin.WRITER if artifact is None else None
                    ),
                )
            )
            continue
        assert observation.current_memory_id is not None
        artifact = artifact_by_id[observation.current_memory_id]
        scored.append(
            _score_artifact(
                artifact,
                observed_block_index=observation.observed_block_index,
                observation=observation,
                case_by_id=case_by_id,
                annotations=annotations,
                domain=domain,
            )
        )
    return tuple(
        sorted(
            scored,
            key=lambda row: (
                row.condition_id,
                row.writer_model or "",
                row.block_index,
                row.case_id,
                row.observation.observation_id if row.observation else "",
                row.artifact.memory_id if row.artifact else "",
            ),
        )
    )


def _score_artifact(
    artifact: MemoryArtifact,
    *,
    observed_block_index: int,
    observation: MemoryObservation | None,
    case_by_id: dict[str, Any],
    annotations: dict[str, AnnotationState],
    domain: Any,
) -> ScoredMemory:
    try:
        case = case_by_id[artifact.case_id]
    except KeyError as exc:
        raise ValueError(f"memory references unknown case: {artifact.case_id}") from exc
    if not 0 <= observed_block_index < len(domain.corpus.blocks(case)):
        raise ValueError(
            f"memory {artifact.memory_id} has invalid observation block {observed_block_index}"
        )
    extracted_state = None
    unscored_reason = None
    if artifact.architecture is MemoryArchitecture.FREE_TEXT:
        annotation = annotations.get(artifact.memory_id)
        if annotation is None:
            unscored_reason = "missing_annotation"
        elif annotation.reason is not None:
            unscored_reason = annotation.reason
        elif annotation.source_content_hash != artifact.content_hash:
            unscored_reason = "annotation_content_hash_mismatch"
        else:
            extracted_state = annotation.state
    if unscored_reason is not None:
        return ScoredMemory(artifact, None, unscored_reason, observation=observation)
    remembered = artifact.payload if extracted_state is None else extracted_state
    report = domain.fidelity.compare(
        case,
        remembered,
        through_block_index=observed_block_index,
    )
    return ScoredMemory(artifact, report, observation=observation)


def summarize_fidelity(
    rows: Iterable[ScoredMemory],
    *,
    by: Iterable[str] = DEFAULT_GROUPS,
) -> tuple[dict[str, Any], ...]:
    """Return JSON-serializable coverage and rate rows for each requested group."""

    group_fields = tuple(by)
    if not group_fields:
        raise ValueError("at least one grouping field is required")
    unknown = set(group_fields) - GROUP_FIELDS
    if unknown:
        raise ValueError(f"unsupported grouping fields: {sorted(unknown)}")

    grouped: dict[tuple[Any, ...], list[ScoredMemory]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.value(field) for field in group_fields)].append(row)

    output = []
    for key, group_rows in sorted(grouped.items(), key=lambda item: repr(item[0])):
        implementations = {
            (
                row.memory_implementation_id,
                row.memory_implementation_hash,
            )
            for row in group_rows
        }
        if len(implementations) > 1:
            raise ValueError(
                "memory fidelity group silently pools memory implementations; "
                "include memory_implementation_id and memory_implementation_hash "
                "in --by"
            )
        writer_routes = {
            (
                row.writer_provider,
                row.writer_target_id,
                row.writer_requested_model,
                row.writer_model,
            )
            for row in group_rows
        }
        if len(writer_routes) > 1:
            raise ValueError(
                "memory fidelity group silently pools writer model routes; "
                "include writer_provider, writer_target_id, "
                "writer_requested_model, and writer_model in --by"
            )
        group = dict(zip(group_fields, key))
        scored = [row for row in group_rows if row.report is not None]
        output.append(_metric(group, "coverage", "scored", len(scored), len(group_rows)))
        observed = [row for row in group_rows if row.observation is not None]
        if observed:
            observation_states = {
                "accepted": sum(row.observation.accepted_this_block for row in observed),
                "retained": sum(row.value("retained") for row in observed),
                "empty": sum(row.observation.empty for row in observed),
            }
            for label, count in observation_states.items():
                output.append(
                    _metric(group, "observation_state_rate", label, count, len(observed))
                )
        unscored = Counter(
            row.unscored_reason for row in group_rows if row.report is None
        )
        for reason, count in sorted(unscored.items()):
            output.append(
                _metric(group, "unscored_rate", str(reason), count, len(group_rows))
            )
        if not scored:
            continue

        reports = [row.report for row in scored]
        assert all(report is not None for report in reports)
        typed_reports = [report for report in reports if report is not None]
        output.append(
            _metric(
                group,
                "representation_exact_rate",
                "exact",
                sum(report.exact for report in typed_reports),
                len(typed_reports),
            )
        )
        for consequence in AUTHORIZATION_CONSEQUENCES:
            output.append(
                _metric(
                    group,
                    "consequence_rate",
                    consequence,
                    sum(
                        _fidelity_consequence(report) == consequence
                        for report in typed_reports
                    ),
                    len(typed_reports),
                )
            )
        for error in FIDELITY_ERRORS:
            output.append(
                _metric(
                    group,
                    "error_rate",
                    error,
                    sum(error in _fidelity_errors(report) for report in typed_reports),
                    len(typed_reports),
                )
            )

        fields: dict[str, list[Any]] = defaultdict(list)
        for report in typed_reports:
            for field in report.fields:
                fields[field.field].append(field)
        for field_name, comparisons in sorted(fields.items()):
            for error in FIDELITY_ERRORS:
                row = _metric(
                    group,
                    "field_error_rate",
                    error,
                    sum(error in comparison.errors for comparison in comparisons),
                    len(comparisons),
                )
                row["field"] = field_name
                output.append(row)
    return tuple(output)


def _fidelity_errors(report: FidelityReport) -> frozenset[str]:
    return frozenset(error for field in report.fields for error in field.errors)


def _fidelity_consequence(report: FidelityReport) -> str:
    overgrant = any(field.overgrant for field in report.fields)
    undergrant = any(field.undergrant for field in report.fields)
    if overgrant and undergrant:
        return "mixed"
    if overgrant:
        return "overgrant"
    if undergrant:
        return "undergrant"
    return "exact"


def print_summary(metrics: Iterable[dict[str, Any]]) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    groups: dict[str, dict[str, Any]] = {}
    for row in metrics:
        key = json.dumps(row["group"], sort_keys=True)
        grouped[key].append(row)
        groups[key] = row["group"]

    print("Memory fidelity (free text is scored only through saved blinded annotations)\n")
    for key in sorted(grouped):
        rows = grouped[key]
        label = " / ".join(f"{name}={value}" for name, value in groups[key].items())
        print(label)
        coverage = next(row for row in rows if row["metric"] == "coverage")
        print(f"  coverage: {coverage['count']}/{coverage['denominator']} ({coverage['rate']:.1%})")
        for row in rows:
            if row["metric"] == "unscored_rate":
                print(f"  unscored {row['label']}: {row['count']}")
        observation_states = [
            row for row in rows if row["metric"] == "observation_state_rate"
        ]
        if observation_states:
            print("  observation state: " + _compact_rates(observation_states))
        if coverage["count"] == 0:
            print()
            continue
        exact = next(row for row in rows if row["metric"] == "representation_exact_rate")
        print(f"  representation exact: {exact['count']}/{exact['denominator']} ({exact['rate']:.1%})")
        consequences = [row for row in rows if row["metric"] == "consequence_rate"]
        print("  consequence: " + _compact_rates(consequences))
        errors = [
            row for row in rows if row["metric"] == "error_rate" and row["count"]
        ]
        print("  errors: " + (_compact_rates(errors) if errors else "none"))
        field_errors = [
            row for row in rows if row["metric"] == "field_error_rate" and row["count"]
        ]
        if field_errors:
            values = ", ".join(
                f"{row['field']}:{row['label']}={row['rate']:.1%}"
                for row in field_errors
            )
            print(f"  field errors: {values}")
        print()


def write_jsonl(path: Path | None, rows: Iterable[dict[str, Any]]) -> None:
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    content = "\n".join(lines) + ("\n" if lines else "")
    if path is None:
        print(content, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _load_artifacts(
    path: Path,
    *,
    allow_empty: bool = False,
    domain_id: str | None = None,
) -> tuple[MemoryArtifact, ...]:
    unique: dict[str, MemoryArtifact] = {}
    for line_number, data in enumerate(
        load_memory_artifacts(path, domain=domain_id),
        start=1,
    ):
        try:
            artifact = MemoryArtifact.from_dict(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid memory at {path}:{line_number}: {exc}") from exc
        previous = unique.get(artifact.memory_id)
        if previous is not None and previous != artifact:
            raise ValueError(f"conflicting duplicate memory ID: {artifact.memory_id}")
        unique.setdefault(artifact.memory_id, artifact)
    if not unique and not allow_empty:
        raise ValueError(f"no memory artifacts found in {path}")
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.condition_id,
                item.writer_model or "",
                item.block_index,
                item.case_id,
                item.memory_id,
            ),
        )
    )


def _load_observations(
    path: Path,
    *,
    artifacts: Mapping[str, MemoryArtifact],
    domain: Any,
) -> tuple[MemoryObservation, ...]:
    rows = list(_load_jsonl(path))
    state_rows = [data for _, data in rows if "state_id" in data]
    if len(state_rows) != len(rows):
        raise ValueError(f"{path} must contain only current memory-state rows")
    state_attempts = _load_state_attempts(path)
    unique: dict[str, MemoryObservation] = {}
    attempts: dict[str, str] = {}
    for line_number, data in rows:
        try:
            observation = MemoryObservation.from_memory_state(
                data,
                artifacts=artifacts,
                attempts=state_attempts,
                domain=domain,
            )
            _validate_observation_shape(observation)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid observation at {path}:{line_number}: {exc}") from exc
        previous = unique.get(observation.observation_id)
        if previous is not None and previous != observation:
            raise ValueError(
                f"conflicting duplicate observation ID: {observation.observation_id}"
            )
        previous_observation_id = attempts.get(observation.attempt_id)
        if previous_observation_id not in {None, observation.observation_id}:
            raise ValueError(f"attempt appears in multiple observations: {observation.attempt_id}")
        unique.setdefault(observation.observation_id, observation)
        attempts.setdefault(observation.attempt_id, observation.observation_id)
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (item.chain_id, item.observed_block_index, item.observation_id),
        )
    )


def _load_state_attempts(path: Path) -> dict[str, Mapping[str, Any]]:
    attempts_path = _related_artifact_path(
        path,
        keys=("memory_attempts", "attempts"),
        default_name="memory_attempts.jsonl",
    )
    if not attempts_path.is_file():
        raise ValueError(
            f"LangMem memory states require their memory attempts: {attempts_path}"
        )
    attempts: dict[str, Mapping[str, Any]] = {}
    for line_number, row in _load_jsonl(attempts_path):
        if row.get("schema_version") not in {4, 5}:
            raise ValueError(
                f"unsupported memory attempt schema at "
                f"{attempts_path}:{line_number}: {row.get('schema_version')!r}"
            )
        attempt_id = row.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError(
                f"invalid memory attempt ID at {attempts_path}:{line_number}"
            )
        previous = attempts.get(attempt_id)
        if previous is not None and previous != row:
            raise ValueError(f"conflicting duplicate memory attempt: {attempt_id}")
        attempts.setdefault(attempt_id, row)
    return attempts


def _related_artifact_path(
    path: Path,
    *,
    keys: tuple[str, ...],
    default_name: str,
) -> Path:
    directory = path if path.is_dir() else path.parent
    manifest_path = directory / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest.get("files")
        if isinstance(files, Mapping):
            for key in keys:
                entry = files.get(key)
                if isinstance(entry, str):
                    return directory / entry
                if isinstance(entry, Mapping) and isinstance(entry.get("path"), str):
                    return directory / str(entry["path"])
    return directory / default_name


def _artifact_is_empty(artifact: MemoryArtifact, domain: Any) -> bool:
    if artifact.architecture is MemoryArchitecture.FREE_TEXT:
        return isinstance(artifact.payload, str) and not artifact.payload.strip()
    if not isinstance(artifact.payload, Mapping):
        return False
    try:
        current = domain.memory.parse_typed(artifact.payload)
        empty = domain.memory.empty_typed()
        return (
            domain.memory.serialize_typed(current)
            == domain.memory.serialize_typed(empty)
        )
    except (TypeError, ValueError):
        return False


def _validate_observation_shape(observation: MemoryObservation) -> None:
    for field in ("observation_id", "case_id", "condition_id", "chain_id", "attempt_id"):
        value = getattr(observation, field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
    if not isinstance(observation.observed_block_index, int) or isinstance(
        observation.observed_block_index, bool
    ):
        raise ValueError("observed_block_index must be an integer")
    if observation.observed_block_index < 0:
        raise ValueError("observed_block_index must be non-negative")
    if not isinstance(observation.attempt_status, str) or not observation.attempt_status:
        raise ValueError("attempt_status must be a non-empty string")
    if observation.attempt_status not in MEMORY_UPDATE_STATUSES:
        raise ValueError(f"unknown attempt_status: {observation.attempt_status}")
    if not isinstance(observation.accepted_this_block, bool) or not isinstance(
        observation.empty, bool
    ):
        raise ValueError("observation flags must be booleans")
    if observation.current_memory_id is None:
        if not observation.empty:
            raise ValueError("a missing current memory must be marked empty")
        if observation.current_content_hash is not None:
            raise ValueError("an absent memory cannot have a content hash")
        if observation.retained_from_block_index is not None:
            raise ValueError("an absent memory cannot have a retained block")
    else:
        if not isinstance(observation.current_memory_id, str) or not observation.current_memory_id:
            raise ValueError("non-empty observation requires current_memory_id")
        if not isinstance(observation.current_content_hash, str) or not observation.current_content_hash:
            raise ValueError("non-empty observation requires current_content_hash")
        if not isinstance(observation.retained_from_block_index, int) or isinstance(
            observation.retained_from_block_index, bool
        ):
            raise ValueError("non-empty observation requires an integer retained block")
        if not 0 <= observation.retained_from_block_index <= observation.observed_block_index:
            raise ValueError("retained block cannot follow the observation block")
    accepted_status = observation.attempt_status in {"accepted", "no_change"}
    if observation.accepted_this_block != accepted_status:
        raise ValueError("accepted_this_block must agree with attempt_status")


def _validate_observation_sequences(
    observations: tuple[MemoryObservation, ...],
    artifact_by_id: dict[str, MemoryArtifact],
    case_by_id: dict[str, Any],
    domain: Any,
) -> None:
    grouped: dict[str, list[MemoryObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.chain_id].append(observation)
    referenced_artifacts = set()
    for chain_id, chain in grouped.items():
        case_ids = {item.case_id for item in chain}
        condition_ids = {item.condition_id for item in chain}
        if len(case_ids) != 1 or len(condition_ids) != 1:
            raise ValueError(f"observation chain changes identity: {chain_id}")
        case_id = next(iter(case_ids))
        condition_id = next(iter(condition_ids))
        if case_id not in case_by_id:
            raise ValueError(f"observation references unknown case: {case_id}")
        block_count = len(domain.corpus.blocks(case_by_id[case_id]))
        actual_indices = [item.observed_block_index for item in chain]
        if condition_id.startswith("incremental_"):
            expected_indices = (
                list(range(actual_indices[-1] + 1)) if actual_indices else []
            )
        elif condition_id.startswith("one_shot_"):
            expected_indices = actual_indices if len(actual_indices) == 1 else []
        else:
            raise ValueError(
                f"observations are unsupported for condition {condition_id}: {chain_id}"
            )
        if (
            actual_indices != expected_indices
            or any(index < 0 or index >= block_count for index in actual_indices)
        ):
            raise ValueError(
                f"observation chain does not cover its required scoring blocks: {chain_id}"
            )
        previous_memory_id = None
        for observation in chain:
            if observation.current_memory_id is None:
                if previous_memory_id is not None:
                    raise ValueError(f"observation chain loses retained state: {chain_id}")
            else:
                assert observation.current_memory_id is not None
                try:
                    artifact = artifact_by_id[observation.current_memory_id]
                except KeyError as exc:
                    raise ValueError(
                        f"observation references unknown memory: {observation.current_memory_id}"
                    ) from exc
                referenced_artifacts.add(artifact.memory_id)
                if (
                    artifact.case_id != observation.case_id
                    or artifact.condition_id != observation.condition_id
                    or artifact.chain_id != observation.chain_id
                ):
                    raise ValueError(
                        f"observation and artifact identity differ: {observation.observation_id}"
                    )
                if artifact.content_hash != observation.current_content_hash:
                    raise ValueError(
                        f"observation content hash mismatch: {observation.observation_id}"
                    )
                if artifact.block_index != observation.retained_from_block_index:
                    raise ValueError(
                        f"observation retained block mismatch: {observation.observation_id}"
                    )
                if observation.attempt_status == "accepted":
                    if artifact.block_index != observation.observed_block_index:
                        raise ValueError("accepted observation must reference this block's artifact")
                elif observation.attempt_status == "no_change":
                    if artifact.block_index > observation.observed_block_index:
                        raise ValueError("unchanged memory cannot come from a future block")
                elif observation.current_memory_id != previous_memory_id:
                    raise ValueError("rejected update must retain the previous memory")
            previous_memory_id = observation.current_memory_id

    for artifact in artifact_by_id.values():
        if artifact.chain_id in grouped and artifact.memory_id not in referenced_artifacts:
            raise ValueError(f"incremental artifact is absent from observations: {artifact.memory_id}")


def _observation_identity(
    observation: MemoryObservation,
    artifacts: tuple[MemoryArtifact, ...],
) -> tuple[str | None, MemoryArchitecture]:
    chain_artifacts = [
        artifact for artifact in artifacts if artifact.chain_id == observation.chain_id
    ]
    if chain_artifacts:
        writers = {artifact.writer_model for artifact in chain_artifacts}
        architectures = {artifact.architecture for artifact in chain_artifacts}
        if len(writers) != 1 or len(architectures) != 1:
            raise ValueError(f"artifact identity changes within chain: {observation.chain_id}")
        return next(iter(writers)), next(iter(architectures))
    architecture = {
        "incremental_text": MemoryArchitecture.FREE_TEXT,
        "incremental_typed": MemoryArchitecture.TYPED,
        "one_shot_text": MemoryArchitecture.FREE_TEXT,
        "one_shot_typed": MemoryArchitecture.TYPED,
    }.get(observation.condition_id)
    if architecture is None:
        raise ValueError(
            f"cannot infer architecture for empty chain: {observation.condition_id}"
        )
    parts = observation.chain_id.split(":", 4)
    if len(parts) != 5 or not parts[2]:
        raise ValueError(f"cannot infer writer model from chain ID: {observation.chain_id}")
    return parts[2], architecture


def _load_annotation_states(
    path: Path,
    domain: Any,
) -> dict[str, AnnotationState]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line_number, data in _load_jsonl(path):
        memory_id = data.get("memory_id")
        if not isinstance(memory_id, str) or not memory_id:
            raise ValueError(f"invalid annotation memory_id at {path}:{line_number}")
        grouped[memory_id].append(data)

    resolved = {}
    for memory_id, records in grouped.items():
        accepted = [record for record in records if record.get("status") == "accepted"]
        if not accepted:
            statuses = sorted({str(record.get("status", "unknown")) for record in records})
            resolved[memory_id] = AnnotationState(
                None, None, f"annotation_not_accepted:{','.join(statuses)}"
            )
            continue
        candidates = []
        for record in accepted:
            try:
                state = domain.memory.parse_typed(record["extracted_state"])
                source_hash = record["source_content_hash"]
                if not isinstance(source_hash, str) or not source_hash:
                    raise ValueError("source_content_hash must be a non-empty string")
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid accepted annotation for {memory_id}: {exc}") from exc
            signature = json.dumps(state, sort_keys=True, separators=(",", ":"))
            candidates.append((signature, source_hash, state))
        signatures = {(signature, source_hash) for signature, source_hash, _ in candidates}
        if len(signatures) != 1:
            resolved[memory_id] = AnnotationState(
                None, None, "conflicting_accepted_annotations"
            )
            continue
        _, source_hash, state = sorted(candidates, key=lambda item: item[0])[0]
        resolved[memory_id] = AnnotationState(state, source_hash, None)
    return resolved


def _load_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(data, dict):
                raise ValueError(f"expected an object at {path}:{line_number}")
            yield line_number, data


def _metric(
    group: dict[str, Any], metric: str, label: str, count: int, denominator: int
) -> dict[str, Any]:
    return {
        "group": group,
        "metric": metric,
        "label": label,
        "count": count,
        "denominator": denominator,
        "rate": count / denominator if denominator else None,
    }


def _compact_rates(rows: Iterable[dict[str, Any]]) -> str:
    return ", ".join(
        f"{row['label']}={row['count']}/{row['denominator']} ({row['rate']:.1%})"
        for row in rows
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("memories", type=Path)
    parser.add_argument("--annotations", type=Path, default=None)
    parser.add_argument(
        "--observations",
        type=Path,
        default=None,
        help="score retained or empty memory state at every observed incremental block",
    )
    parser.add_argument("--corpus-version", default="benchmark_v1")
    parser.add_argument(
        "--domain",
        default=None,
        help="required only when memories.jsonl has no sibling manifest",
    )
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--by", nargs="+", default=list(DEFAULT_GROUPS))
    parser.add_argument(
        "--jsonl",
        nargs="?",
        const="-",
        default=None,
        metavar="PATH",
        help="write machine-readable summary JSONL; omit PATH for stdout",
    )
    args = parser.parse_args()
    scored = score_saved_memories(
        args.memories,
        annotations_path=args.annotations,
        observations_path=args.observations,
        corpus_version=args.corpus_version,
        cases_path=args.cases,
        domain_id=args.domain,
    )
    metrics = summarize_fidelity(scored, by=args.by)
    if args.jsonl is None:
        print_summary(metrics)
    else:
        write_jsonl(None if args.jsonl == "-" else Path(args.jsonl), metrics)


if __name__ == "__main__":
    main()
