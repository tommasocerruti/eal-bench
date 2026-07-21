from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

from .cases import (
    DATA_DIR,
    current_ledger,
    load_cases,
    render_full_history,
    replay_case,
    validate_case,
)
from .oracle import evaluate_ledger
from .schemas import AuthorizationCase


BLUEPRINT_PATH = Path(__file__).with_name("benchmark_blueprint.yaml")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_CANONICAL_TIMESTAMP_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\b")
_ISOISH_TIMESTAMP_PATTERN = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?\b"
)
_DATE_ONLY_PATTERN = re.compile(r"\b\d{4}-\d{2}-\d{2}\b(?!T)")
_AMBIGUOUS_DATE_PATTERN = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2}(?:st|nd|rd|th)?(?:,\s*\d{4})?\b"
    r"|\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b",
    re.IGNORECASE,
)
_PAIR_FIELD = {"amount": "amount", "time": "action_time", "category": "category"}
_SEQUENCE_METADATA = {
    "target_dimensions",
    "distractor_types",
    "memory_hazards",
}
_SCALAR_METADATA = {
    "split",
    "case_family_id",
    "lifecycle",
    "history_length_band",
}
_MATCH_FIELDS = _SEQUENCE_METADATA | _SCALAR_METADATA


@dataclass(frozen=True)
class HistoryLengthBand:
    name: str
    min_turns: int
    max_turns: int


@dataclass(frozen=True)
class CoverageCell:
    cell_id: str
    minimum: int
    match: dict[str, str | tuple[str, ...]]


@dataclass(frozen=True)
class SplitCoverage:
    split: str
    minimum_cases: int
    cells: tuple[CoverageCell, ...]


@dataclass(frozen=True)
class BenchmarkBlueprint:
    path: Path
    source_hash: str
    schema_version: str
    status: str
    allowed_splits: tuple[str, ...]
    lifecycle_patterns: dict[str, tuple[str, ...]]
    target_dimensions: tuple[str, ...]
    distractor_types: tuple[str, ...]
    history_length_bands: dict[str, HistoryLengthBand]
    memory_hazards: tuple[str, ...]
    capacity: dict[str, Any]
    coverage: dict[str, SplitCoverage]


@dataclass(frozen=True)
class CoverageResult:
    split: str
    item: str
    actual: int
    minimum: int

    @property
    def complete(self) -> bool:
        return self.actual >= self.minimum


@dataclass(frozen=True)
class CapacityResult:
    calibration_split: str
    calibration_version: str
    reference_tokenizer: str
    largest_faithful_tokens: int
    primary_tokens: int
    tight_tokens: int
    required_history_tokens: int
    minimum_observed_history_tokens: int


@dataclass
class LintReport:
    blueprint: BenchmarkBlueprint
    versions: tuple[str, ...]
    file_hashes: dict[str, str]
    cases: tuple[AuthorizationCase, ...]
    errors: list[str]
    warnings: list[str]
    coverage: tuple[CoverageResult, ...]
    capacity: CapacityResult | None

    @property
    def coverage_complete(self) -> bool:
        return all(item.complete for item in self.coverage)

    def failed(self, *, require_complete: bool) -> bool:
        return bool(self.errors) or (require_complete and not self.coverage_complete)


def _expect_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _expect_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _expect_int(value: Any, name: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _expect_unique_texts(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    items = tuple(_expect_text(item, f"{name} item") for item in value)
    if len(items) != len(set(items)):
        raise ValueError(f"{name} must not contain duplicates")
    return items


def _check_keys(
    data: Mapping[str, Any],
    *,
    required: set[str],
    name: str,
) -> None:
    missing = required - set(data)
    unknown = set(data) - required
    if missing:
        raise ValueError(f"{name} is missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{name} has unexpected fields: {sorted(unknown)}")


def load_blueprint(path: Path = BLUEPRINT_PATH) -> BenchmarkBlueprint:
    raw_bytes = path.read_bytes()
    try:
        loaded = yaml.safe_load(raw_bytes)
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid blueprint YAML at {path}: {exc}") from exc
    data = _expect_mapping(loaded, "blueprint")
    required = {
        "schema_version",
        "status",
        "allowed_splits",
        "lifecycle_patterns",
        "target_dimensions",
        "distractor_types",
        "history_length_bands",
        "memory_hazards",
        "capacity",
        "coverage",
    }
    _check_keys(data, required=required, name="blueprint")

    schema_version = _expect_text(data["schema_version"], "schema_version")
    status = _expect_text(data["status"], "status")
    allowed_splits = _expect_unique_texts(data["allowed_splits"], "allowed_splits")
    target_dimensions = _expect_unique_texts(data["target_dimensions"], "target_dimensions")
    distractor_types = _expect_unique_texts(data["distractor_types"], "distractor_types")
    memory_hazards = _expect_unique_texts(data["memory_hazards"], "memory_hazards")

    lifecycle_data = _expect_mapping(data["lifecycle_patterns"], "lifecycle_patterns")
    lifecycle_patterns: dict[str, tuple[str, ...]] = {}
    for name, raw_pattern in lifecycle_data.items():
        lifecycle_name = _expect_text(name, "lifecycle name")
        pattern = _expect_mapping(raw_pattern, f"lifecycle {lifecycle_name}")
        _check_keys(
            pattern,
            required={"event_types"},
            name=f"lifecycle {lifecycle_name}",
        )
        event_types = _expect_unique_texts(
            pattern["event_types"], f"lifecycle {lifecycle_name}.event_types"
        )
        unknown_types = set(event_types) - {"issue", "patch", "revoke", "replace"}
        if unknown_types:
            raise ValueError(
                f"lifecycle {lifecycle_name} has invalid event types: {sorted(unknown_types)}"
            )
        lifecycle_patterns[lifecycle_name] = event_types
    if not lifecycle_patterns:
        raise ValueError("lifecycle_patterns must not be empty")

    band_data = _expect_mapping(data["history_length_bands"], "history_length_bands")
    history_length_bands: dict[str, HistoryLengthBand] = {}
    occupied_turn_counts: set[int] = set()
    for name, raw_band in band_data.items():
        band_name = _expect_text(name, "history length band name")
        band = _expect_mapping(raw_band, f"history length band {band_name}")
        _check_keys(
            band,
            required={"min_turns", "max_turns"},
            name=f"history length band {band_name}",
        )
        min_turns = _expect_int(
            band["min_turns"], f"history length band {band_name}.min_turns", minimum=1
        )
        max_turns = _expect_int(
            band["max_turns"], f"history length band {band_name}.max_turns", minimum=1
        )
        if min_turns > max_turns:
            raise ValueError(f"history length band {band_name} has an inverted range")
        represented = set(range(min_turns, max_turns + 1))
        if represented & occupied_turn_counts:
            raise ValueError("history length bands must not overlap")
        occupied_turn_counts.update(represented)
        history_length_bands[band_name] = HistoryLengthBand(band_name, min_turns, max_turns)
    if not history_length_bands:
        raise ValueError("history_length_bands must not be empty")
    expected_turn_counts = set(range(40, 101))
    if occupied_turn_counts != expected_turn_counts:
        missing = sorted(expected_turn_counts - occupied_turn_counts)
        extra = sorted(occupied_turn_counts - expected_turn_counts)
        raise ValueError(
            "history length bands must cover exactly the supported 40-100 turn range; "
            f"missing={missing}, extra={extra}"
        )

    capacity = _expect_mapping(data["capacity"], "capacity")
    _check_keys(
        capacity,
        required={
            "calibration_split",
            "calibration_version",
            "reference_tokenizer",
            "primary_multiplier",
            "tight_multiplier",
            "minimum_history_to_primary_ratio",
        },
        name="capacity",
    )
    calibration_split = _expect_text(capacity["calibration_split"], "capacity.calibration_split")
    if calibration_split not in allowed_splits:
        raise ValueError("capacity.calibration_split is not an allowed split")
    _expect_text(capacity["calibration_version"], "capacity.calibration_version")
    _expect_text(capacity["reference_tokenizer"], "capacity.reference_tokenizer")
    for field in ("primary_multiplier", "tight_multiplier"):
        value = capacity[field]
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"capacity.{field} must be positive")
    _expect_int(
        capacity["minimum_history_to_primary_ratio"],
        "capacity.minimum_history_to_primary_ratio",
        minimum=1,
    )

    enum_by_field = {
        "split": allowed_splits,
        "lifecycle": tuple(lifecycle_patterns),
        "target_dimensions": target_dimensions,
        "distractor_types": distractor_types,
        "history_length_band": tuple(history_length_bands),
        "memory_hazards": memory_hazards,
    }
    coverage_data = _expect_mapping(data["coverage"], "coverage")
    if set(coverage_data) != set(allowed_splits):
        raise ValueError("coverage keys must exactly match allowed_splits")
    coverage: dict[str, SplitCoverage] = {}
    for split in allowed_splits:
        raw_split = _expect_mapping(coverage_data[split], f"coverage.{split}")
        _check_keys(
            raw_split,
            required={"minimum_cases", "cells"},
            name=f"coverage.{split}",
        )
        minimum_cases = _expect_int(
            raw_split["minimum_cases"], f"coverage.{split}.minimum_cases", minimum=1
        )
        raw_cells = raw_split["cells"]
        if not isinstance(raw_cells, list) or not raw_cells:
            raise ValueError(f"coverage.{split}.cells must be a non-empty list")
        cells = []
        seen_ids = set()
        for index, raw_cell in enumerate(raw_cells):
            cell = _expect_mapping(raw_cell, f"coverage.{split}.cells[{index}]")
            _check_keys(
                cell,
                required={"id", "minimum", "match"},
                name=f"coverage.{split}.cells[{index}]",
            )
            cell_id = _expect_text(cell["id"], "coverage cell id")
            if cell_id in seen_ids:
                raise ValueError(f"coverage.{split} has duplicate cell {cell_id!r}")
            seen_ids.add(cell_id)
            minimum = _expect_int(cell["minimum"], f"coverage.{split}.{cell_id}.minimum", minimum=1)
            raw_match = _expect_mapping(cell["match"], f"coverage.{split}.{cell_id}.match")
            unknown_match = set(raw_match) - _MATCH_FIELDS
            if unknown_match:
                raise ValueError(
                    f"coverage.{split}.{cell_id} has unknown selectors: {sorted(unknown_match)}"
                )
            normalized_match: dict[str, str | tuple[str, ...]] = {}
            for field, raw_value in raw_match.items():
                allowed_values = enum_by_field.get(field)
                if field == "case_family_id":
                    allowed_values = None
                if field in _SEQUENCE_METADATA:
                    values = (
                        _expect_unique_texts(raw_value, f"coverage.{split}.{cell_id}.{field}")
                        if isinstance(raw_value, list)
                        else (_expect_text(raw_value, field),)
                    )
                    if allowed_values is not None and set(values) - set(allowed_values):
                        raise ValueError(
                            f"coverage.{split}.{cell_id}.{field} contains unknown values"
                        )
                    normalized_match[field] = values
                else:
                    value = _expect_text(raw_value, field)
                    if allowed_values is not None and value not in allowed_values:
                        raise ValueError(
                            f"coverage.{split}.{cell_id}.{field} contains unknown value {value!r}"
                        )
                    normalized_match[field] = value
            cells.append(CoverageCell(cell_id, minimum, normalized_match))
        coverage[split] = SplitCoverage(split, minimum_cases, tuple(cells))

    return BenchmarkBlueprint(
        path=path,
        source_hash=hashlib.sha256(raw_bytes).hexdigest(),
        schema_version=schema_version,
        status=status,
        allowed_splits=allowed_splits,
        lifecycle_patterns=lifecycle_patterns,
        target_dimensions=target_dimensions,
        distractor_types=distractor_types,
        history_length_bands=history_length_bands,
        memory_hazards=memory_hazards,
        capacity=dict(capacity),
        coverage=coverage,
    )


def _case_metadata(case: AuthorizationCase) -> dict[str, Any]:
    benchmark = case.benchmark
    return {
        "split": benchmark.split,
        "case_family_id": benchmark.case_family_id,
        "lifecycle": benchmark.lifecycle,
        "target_dimensions": benchmark.target_dimensions,
        "distractor_types": benchmark.distractor_types,
        "history_length_band": benchmark.history_length_band,
        "memory_hazards": benchmark.memory_hazards,
    }


def _matches(case: AuthorizationCase, selectors: Mapping[str, str | tuple[str, ...]]) -> bool:
    metadata = _case_metadata(case)
    for field, expected in selectors.items():
        actual = metadata[field]
        if field in _SEQUENCE_METADATA:
            required = expected if isinstance(expected, tuple) else (expected,)
            if not set(required).issubset(actual):
                return False
        elif actual != expected:
            return False
    return True


def _coverage_results(
    cases: Sequence[AuthorizationCase], blueprint: BenchmarkBlueprint
) -> tuple[CoverageResult, ...]:
    results = []
    for split in blueprint.allowed_splits:
        split_cases = tuple(case for case in cases if case.benchmark.split == split)
        spec = blueprint.coverage[split]
        results.append(CoverageResult(split, "minimum_cases", len(split_cases), spec.minimum_cases))
        for cell in spec.cells:
            actual = sum(_matches(case, cell.match) for case in split_cases)
            results.append(CoverageResult(split, cell.cell_id, actual, cell.minimum))
    return tuple(results)


def _validate_compiler_versions(
    versions: Sequence[str],
    *,
    data_dir: Path,
    errors: list[str],
    warnings: list[str],
) -> None:
    if data_dir.resolve() != DATA_DIR.resolve():
        warnings.append("compiler divergence check skipped for a custom data directory")
        return
    try:
        from .compile_corpus import check_compiled
    except ImportError as exc:
        errors.append(f"deterministic compiler is unavailable: {exc}")
        return
    for version in versions:
        try:
            check_compiled(version)
        except (OSError, TypeError, ValueError) as exc:
            errors.append(f"{version}: compiled corpus diverges from authoring YAML: {exc}")


def _load_compiled_cases(
    versions: Sequence[str],
    *,
    data_dir: Path,
    errors: list[str],
) -> tuple[tuple[AuthorizationCase, ...], dict[str, str]]:
    all_cases: list[AuthorizationCase] = []
    file_hashes = {}
    for version in versions:
        path = data_dir / f"{version}.jsonl"
        if not path.is_file():
            errors.append(f"{version}: compiled corpus does not exist at {path}")
            continue
        raw_bytes = path.read_bytes()
        file_hashes[version] = hashlib.sha256(raw_bytes).hexdigest()
        try:
            cases = load_cases(version, path)
        except (OSError, ValueError) as exc:
            errors.append(f"{version}: {exc}")
            continue
        all_cases.extend(cases)
    return tuple(all_cases), file_hashes


def _validate_metadata(
    case: AuthorizationCase,
    blueprint: BenchmarkBlueprint,
    errors: list[str],
) -> None:
    metadata = _case_metadata(case)
    allowed = {
        "split": blueprint.allowed_splits,
        "lifecycle": tuple(blueprint.lifecycle_patterns),
        "target_dimensions": blueprint.target_dimensions,
        "distractor_types": blueprint.distractor_types,
        "history_length_band": tuple(blueprint.history_length_bands),
        "memory_hazards": blueprint.memory_hazards,
    }
    for field, values in allowed.items():
        actual = metadata[field]
        actual_values = actual if isinstance(actual, tuple) else (actual,)
        unknown = set(actual_values) - set(values)
        if unknown:
            errors.append(
                f"{case.case_id}: benchmark.{field} contains unknown values {sorted(unknown)}"
            )

    turn_count = sum(len(block.turns) for block in case.blocks)
    band = blueprint.history_length_bands.get(case.benchmark.history_length_band)
    if band is not None and not band.min_turns <= turn_count <= band.max_turns:
        errors.append(
            f"{case.case_id}: {turn_count} turns do not fit history band "
            f"{band.name}=[{band.min_turns},{band.max_turns}]"
        )

    expected_events = blueprint.lifecycle_patterns.get(case.benchmark.lifecycle)
    actual_events = tuple(event.event_type for event in case.events)
    supports_trailing_extensions = (
        expected_events is not None
        and tuple(
            event.event_type
            for event in case.events
            if not event.authorization_id.startswith("aux_")
            and "_event_v4_target_" not in event.event_id
        )
        == expected_events
        and len(actual_events) > len(expected_events)
        and all(
            event.event_type in {"issue", "patch"}
            for event in case.events
            if event.authorization_id.startswith("aux_") or "_event_v4_target_" in event.event_id
        )
        and "parallel_authorizations" in case.tags
        and case.benchmark.lifecycle
        in {
            "issue_only",
            "issue_patch",
            "issue_revoke_replace",
        }
    )
    if (
        expected_events is not None
        and actual_events != expected_events
        and not supports_trailing_extensions
    ):
        errors.append(
            f"{case.case_id}: lifecycle {case.benchmark.lifecycle!r} expects "
            f"{list(expected_events)}, observed {list(actual_events)}"
        )

    targets = set(case.benchmark.target_dimensions)
    if case.benchmark.lifecycle == "issue_only":
        probe_dimensions = {pair.dimension for pair in case.probe_pairs}
        if targets != probe_dimensions:
            errors.append(
                f"{case.case_id}: issue_only target dimensions must equal probe "
                f"dimensions {sorted(probe_dimensions)}"
            )
    elif case.benchmark.lifecycle == "issue_patch":
        patch_fields = {
            field
            for event in case.events
            if "_event_v4_target_" not in event.event_id
            if event.patch is not None
            for field in event.patch.changed_fields()
        }
        mapped = {
            {
                "max_amount": "amount",
                "valid_from": "time",
                "valid_until": "time",
                "allowed_categories": "category",
                "vendor": "vendor",
                "status": "status",
            }.get(field)
            for field in patch_fields
        }
        mapped.discard(None)
        if targets != mapped:
            errors.append(
                f"{case.case_id}: patch target dimensions {sorted(targets)} do not "
                f"match changed scope dimensions {sorted(mapped)}"
            )
    elif case.benchmark.lifecycle == "issue_revoke_replace":
        if "status" not in targets:
            errors.append(f"{case.case_id}: revoke/replace lifecycle must target status")
        issue = next((event.record for event in case.events if event.event_type == "issue"), None)
        replacement = next(
            (event.record for event in case.events if event.event_type == "replace"), None
        )
        if (
            issue is not None
            and replacement is not None
            and issue.vendor != replacement.vendor
            and "vendor" not in targets
        ):
            errors.append(f"{case.case_id}: replacement changes vendor but metadata omits vendor")


def _validate_ids(case: AuthorizationCase, errors: list[str]) -> None:
    split = case.benchmark.split
    if not _ID_PATTERN.fullmatch(case.case_id):
        errors.append(f"{case.case_id}: case_id is not normalized snake_case")
    expected_prefix = (
        "procurement_v1_" if split == "benchmark" else "calibration_v1_"
    )
    if not case.case_id.startswith(expected_prefix):
        errors.append(
            f"{case.case_id}: case_id must begin with {expected_prefix!r}"
        )
    if not _ID_PATTERN.fullmatch(case.benchmark.case_family_id):
        errors.append(f"{case.case_id}: case_family_id is not normalized snake_case")
    expected_blocks = [f"{case.case_id}_block_{index:02d}" for index in range(len(case.blocks))]
    observed_blocks = [block.block_id for block in case.blocks]
    if observed_blocks != expected_blocks:
        errors.append(f"{case.case_id}: block IDs are not deterministic and contiguous")
    for event in case.events:
        if not event.event_id.startswith(f"{case.case_id}_event_"):
            errors.append(
                f"{case.case_id}: event ID {event.event_id!r} is outside the case namespace"
            )
    for pair in case.probe_pairs:
        expected_pair = f"{case.case_id}_{pair.dimension}"
        if pair.pair_id != expected_pair:
            errors.append(f"{case.case_id}: pair ID {pair.pair_id!r} should be {expected_pair!r}")
        expected_names = (
            f"{expected_pair}_in",
            f"{expected_pair}_out",
        )
        observed_names = (pair.in_scope.name, pair.out_of_scope.name)
        if observed_names != expected_names:
            errors.append(f"{case.case_id}/{pair.pair_id}: probe names are not deterministic")
        expected_transactions = (
            f"{case.case_id}_txn_{pair.dimension}_in",
            f"{case.case_id}_txn_{pair.dimension}_out",
        )
        observed_transactions = (
            pair.in_scope.transaction.transaction_id,
            pair.out_of_scope.transaction.transaction_id,
        )
        if observed_transactions != expected_transactions:
            errors.append(f"{case.case_id}/{pair.pair_id}: transaction IDs are not deterministic")


def _validate_authoritative_temporal_language(
    case: AuthorizationCase,
    *,
    turn_id: str,
    content: str,
    errors: list[str],
) -> None:
    isoish = _ISOISH_TIMESTAMP_PATTERN.findall(content)
    noncanonical = [
        timestamp for timestamp in isoish if not _CANONICAL_TIMESTAMP_PATTERN.fullmatch(timestamp)
    ]
    if noncanonical:
        errors.append(
            f"{case.case_id}/{turn_id}: authoritative turn uses non-canonical "
            f"timestamps {noncanonical}"
        )
    if _AMBIGUOUS_DATE_PATTERN.search(content) or _DATE_ONLY_PATTERN.search(content):
        errors.append(f"{case.case_id}/{turn_id}: authoritative turn uses an ambiguous date claim")

    lowered = content.lower()
    for match in _CANONICAL_TIMESTAMP_PATTERN.finditer(content):
        prefix = lowered[max(0, match.start() - 100) : match.start()]
        suffix = lowered[match.end() : match.end() + 40]
        required_boundary = None
        if re.search(r"(?:\bvalid\s+from|\bvalid_from(?:\s+is\s+now)?|\bfrom)\s*$", prefix):
            required_boundary = "inclusive"
        elif re.search(
            r"(?:\bvalid_until(?:\s+is\s+now)?|\buntil|\bending\s+at|"
            r"\bends?\s+at|\bexpires?\s+at)\s*$",
            prefix,
        ):
            required_boundary = "exclusive"
        if required_boundary is not None and required_boundary not in suffix:
            errors.append(
                f"{case.case_id}/{turn_id}: validity timestamp {match.group()} must "
                f"state its {required_boundary} boundary"
            )


def _validate_temporal_claims(case: AuthorizationCase, errors: list[str]) -> None:
    turn_by_id = {turn.turn_id: turn for block in case.blocks for turn in block.turns}
    for turn in turn_by_id.values():
        if turn.actor_id in case.authorized_issuers:
            _validate_authoritative_temporal_language(
                case,
                turn_id=turn.turn_id,
                content=turn.content,
                errors=errors,
            )
    for event in case.events:
        source_turns = [turn_by_id[source_id] for source_id in event.source_turn_ids]
        for turn in source_turns:
            source_time = datetime.fromisoformat(turn.occurred_at.replace("Z", "+00:00"))
            event_time = datetime.fromisoformat(event.effective_at.replace("Z", "+00:00"))
            if source_time > event_time:
                errors.append(
                    f"{case.case_id}/{event.event_id}: authoritative source "
                    f"{turn.turn_id} occurs after event time {event.effective_at}"
                )
            if source_time != event_time and event.effective_at not in turn.content:
                errors.append(
                    f"{case.case_id}/{event.event_id}: delayed event source "
                    f"{turn.turn_id} must state exact effective_at={event.effective_at}"
                )
            if "immediate" in turn.content.lower() and source_time != event_time:
                errors.append(
                    f"{case.case_id}/{event.event_id}: an immediate event must become "
                    "effective at its source turn timestamp"
                )

        source_text = " ".join(turn.content for turn in source_turns)
        if event.record is not None:
            for field, boundary in (
                ("valid_from", "inclusive"),
                ("valid_until", "exclusive"),
            ):
                timestamp = getattr(event.record, field)
                position = source_text.find(timestamp)
                if position < 0:
                    errors.append(
                        f"{case.case_id}/{event.event_id}: visible source omits exact "
                        f"{field}={timestamp}"
                    )
                    continue
                suffix = source_text[position + len(timestamp) : position + len(timestamp) + 40]
                if boundary not in suffix.lower():
                    errors.append(
                        f"{case.case_id}/{event.event_id}: visible {field} must state "
                        f"its {boundary} boundary"
                    )
        if event.patch is not None:
            for field in ("valid_from", "valid_until"):
                value = getattr(event.patch, field)
                if value is None:
                    continue
                if value not in source_text:
                    errors.append(
                        f"{case.case_id}/{event.event_id}: visible source omits patched "
                        f"{field}={value}"
                    )
                boundary = "inclusive" if field == "valid_from" else "exclusive"
                position = source_text.find(value)
                suffix = (
                    source_text[position + len(value) : position + len(value) + 40]
                    if position >= 0
                    else ""
                )
                if boundary not in suffix.lower():
                    errors.append(
                        f"{case.case_id}/{event.event_id}: patched {field} must state "
                        f"its {boundary} boundary"
                    )


def _validate_pairs(case: AuthorizationCase, errors: list[str]) -> None:
    ledger = current_ledger(case)
    for pair in case.probe_pairs:
        left = pair.in_scope.transaction.to_dict()
        right = pair.out_of_scope.transaction.to_dict()
        left.pop("transaction_id")
        right.pop("transaction_id")
        differences = {field for field in left if left[field] != right[field]}
        expected_field = _PAIR_FIELD[pair.dimension]
        if differences != {expected_field}:
            errors.append(
                f"{case.case_id}/{pair.pair_id}: pair delta is {sorted(differences)}, "
                f"expected only {expected_field}"
            )
        in_decision = evaluate_ledger(
            ledger,
            pair.in_scope.transaction,
            authorized_issuers=case.authorized_issuers,
        )
        out_decision = evaluate_ledger(
            ledger,
            pair.out_of_scope.transaction,
            authorized_issuers=case.authorized_issuers,
        )
        if not in_decision.authorized or out_decision.authorized:
            errors.append(
                f"{case.case_id}/{pair.pair_id}: intended oracle delta is not "
                "authorized -> unauthorized"
            )
        expected_reason = f"{pair.dimension}_out_of_scope"
        if expected_reason not in out_decision.reason:
            errors.append(
                f"{case.case_id}/{pair.pair_id}: out-of-scope oracle reason "
                f"{out_decision.reason!r} does not isolate {pair.dimension}"
            )


def _validate_hidden_leakage(case: AuthorizationCase, errors: list[str]) -> None:
    history = render_full_history(case)
    hidden_identifiers = {
        case.case_id,
        case.authoring_hash,
        *(event.event_id for event in case.events),
        *(pair.pair_id for pair in case.probe_pairs),
        *(probe.name for pair in case.probe_pairs for probe in (pair.in_scope, pair.out_of_scope)),
        *(
            probe.transaction.transaction_id
            for pair in case.probe_pairs
            for probe in (pair.in_scope, pair.out_of_scope)
        ),
    }
    if case.benchmark.case_family_id != case.case_id:
        hidden_identifiers.add(case.benchmark.case_family_id)
    leaked = sorted(identifier for identifier in hidden_identifiers if identifier in history)
    if leaked:
        errors.append(f"{case.case_id}: model-visible history leaks hidden identifiers {leaked}")


def _normalized_family_fingerprint(case: AuthorizationCase) -> str:
    text = "\n".join(
        (
            case.policy,
            *(
                f"{block.title}\n"
                + "\n".join(
                    f"{turn.actor_id}|{turn.speaker}|{turn.content}" for turn in block.turns
                )
                for block in case.blocks
            ),
        )
    ).lower()
    scope_values = {
        value.lower()
        for event in case.events
        if event.record is not None
        for value in (
            event.record.vendor,
            event.record.grantee.replace("_", " "),
            *(category.replace("_", " ") for category in event.record.allowed_categories),
        )
    }
    for value in sorted(scope_values, key=len, reverse=True):
        text = text.replace(value, "<scope_value>")
    text = _CANONICAL_TIMESTAMP_PATTERN.sub("<timestamp>", text)
    text = re.sub(r"\bauth_[a-z0-9_]+\b", "<authorization>", text)
    text = re.sub(r"\b(?:usd\s*)?\$?\d[\d,]*(?:\.\d+)?\b", "<number>", text)
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _validate_global_uniqueness(cases: Sequence[AuthorizationCase], errors: list[str]) -> None:
    case_ids = Counter(case.case_id for case in cases)
    duplicate_cases = sorted(case_id for case_id, count in case_ids.items() if count > 1)
    if duplicate_cases:
        errors.append(f"duplicate case IDs across compiled corpora: {duplicate_cases}")

    authoring_hashes: dict[str, list[str]] = defaultdict(list)
    source_ids: dict[str, list[str]] = defaultdict(list)
    family_splits: dict[str, set[str]] = defaultdict(set)
    fingerprint_splits: dict[str, set[str]] = defaultdict(set)
    fingerprint_cases: dict[str, list[str]] = defaultdict(list)
    for case in cases:
        authoring_hash = case.authoring_hash
        if not _SHA256_PATTERN.fullmatch(authoring_hash):
            errors.append(f"{case.case_id}: authoring_hash is not a lowercase SHA-256")
        authoring_hashes[authoring_hash].append(case.case_id)
        family_splits[case.benchmark.case_family_id].add(case.benchmark.split)
        fingerprint = _normalized_family_fingerprint(case)
        fingerprint_splits[fingerprint].add(case.benchmark.split)
        fingerprint_cases[fingerprint].append(case.case_id)
        for block in case.blocks:
            for turn in block.turns:
                source_ids[turn.turn_id].append(case.case_id)

    duplicate_hashes = {value: ids for value, ids in authoring_hashes.items() if len(ids) > 1}
    for value, ids in sorted(duplicate_hashes.items()):
        errors.append(f"authoring hash {value} is shared by cases {sorted(ids)}")
    for source_id, ids in sorted(source_ids.items()):
        if len(ids) > 1:
            errors.append(f"source turn ID {source_id!r} is shared across cases {sorted(ids)}")
    for family_id, splits in sorted(family_splits.items()):
        if len(splits) > 1:
            errors.append(f"case family {family_id!r} crosses splits {sorted(splits)}")
    for fingerprint, splits in sorted(fingerprint_splits.items()):
        if len(splits) > 1:
            errors.append(
                "normalized conversation family crosses splits "
                f"{sorted(splits)} in cases {sorted(fingerprint_cases[fingerprint])}"
            )


def _validate_capacity(
    cases: Sequence[AuthorizationCase],
    blueprint: BenchmarkBlueprint,
    errors: list[str],
) -> CapacityResult | None:
    calibration_split = blueprint.capacity["calibration_split"]
    calibration_version = blueprint.capacity["calibration_version"]
    calibration_cases = tuple(case for case in cases if case.schema_version == calibration_version)
    if not calibration_cases:
        errors.append(f"capacity calibration version {calibration_version!r} has no loaded cases")
        return None
    wrong_split = sorted(
        case.case_id for case in calibration_cases if case.benchmark.split != calibration_split
    )
    if wrong_split:
        errors.append(
            f"capacity calibration version {calibration_version!r} contains cases "
            f"outside split {calibration_split!r}: {wrong_split}"
        )
        return None
    try:
        from .studies.memory import count_reference_tokens
        from .studies.pipeline import (
            MIN_HISTORY_TO_PRIMARY_RATIO,
            PRIMARY_CAPACITY_MULTIPLIER,
            TIGHT_CAPACITY_MULTIPLIER,
            calibrate_capacity_budgets,
        )

        expected = {
            "primary_multiplier": PRIMARY_CAPACITY_MULTIPLIER,
            "tight_multiplier": TIGHT_CAPACITY_MULTIPLIER,
            "minimum_history_to_primary_ratio": MIN_HISTORY_TO_PRIMARY_RATIO,
        }
        for field, value in expected.items():
            if blueprint.capacity[field] != value:
                errors.append(
                    f"blueprint capacity.{field}={blueprint.capacity[field]!r} "
                    f"does not match runtime value {value!r}"
                )
        calibration = calibrate_capacity_budgets(calibration_cases)
        if calibration.reference_tokenizer != blueprint.capacity["reference_tokenizer"]:
            errors.append(
                "blueprint reference tokenizer does not match runtime calibration: "
                f"{blueprint.capacity['reference_tokenizer']!r} != "
                f"{calibration.reference_tokenizer!r}"
            )
        required_history = (
            blueprint.capacity["minimum_history_to_primary_ratio"] * calibration.primary_tokens
        )
        history_counts = {
            case.case_id: count_reference_tokens(render_full_history(case)) for case in cases
        }
        for case_id, count in sorted(history_counts.items()):
            if count < required_history:
                errors.append(
                    f"{case_id}: history uses {count} tokens, below frozen capacity "
                    f"minimum {required_history}"
                )
        return CapacityResult(
            calibration_split=calibration_split,
            calibration_version=calibration_version,
            reference_tokenizer=calibration.reference_tokenizer,
            largest_faithful_tokens=calibration.largest_faithful_tokens,
            primary_tokens=calibration.primary_tokens,
            tight_tokens=calibration.tight_tokens,
            required_history_tokens=required_history,
            minimum_observed_history_tokens=min(history_counts.values()),
        )
    except (ImportError, ValueError) as exc:
        errors.append(f"capacity validation failed: {exc}")
        return None


def lint_corpora(
    *,
    versions: Sequence[str],
    blueprint_path: Path = BLUEPRINT_PATH,
    data_dir: Path = DATA_DIR,
) -> LintReport:
    blueprint = load_blueprint(blueprint_path)
    normalized_versions = tuple(sorted(dict.fromkeys(versions)))
    if not normalized_versions:
        raise ValueError("at least one compiled corpus version is required")
    errors: list[str] = []
    warnings: list[str] = []
    _validate_compiler_versions(
        normalized_versions,
        data_dir=data_dir,
        errors=errors,
        warnings=warnings,
    )
    cases, file_hashes = _load_compiled_cases(
        normalized_versions,
        data_dir=data_dir,
        errors=errors,
    )
    for case in cases:
        try:
            validate_case(case)
            replay_case(case)
        except ValueError as exc:
            errors.append(f"{case.case_id}: semantic validation failed: {exc}")
            continue
        _validate_metadata(case, blueprint, errors)
        _validate_ids(case, errors)
        _validate_temporal_claims(case, errors)
        _validate_pairs(case, errors)
        _validate_hidden_leakage(case, errors)
    _validate_global_uniqueness(cases, errors)
    capacity = _validate_capacity(cases, blueprint, errors) if cases else None
    coverage = _coverage_results(cases, blueprint)
    for result in coverage:
        if not result.complete:
            warnings.append(
                f"coverage gap {result.split}/{result.item}: {result.actual}/{result.minimum}"
            )
    return LintReport(
        blueprint=blueprint,
        versions=normalized_versions,
        file_hashes=file_hashes,
        cases=cases,
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
        coverage=coverage,
        capacity=capacity,
    )


def _format_report(report: LintReport, *, require_complete: bool) -> str:
    lines = [
        "Procurement corpus lint",
        f"blueprint: {report.blueprint.path}",
        f"blueprint_status: {report.blueprint.status}",
        f"blueprint_sha256: {report.blueprint.source_hash}",
        f"versions: {','.join(report.versions)}",
        f"cases: {len(report.cases)}",
    ]
    for version in report.versions:
        digest = report.file_hashes.get(version, "unavailable")
        lines.append(f"compiled_sha256[{version}]: {digest}")
    split_counts = Counter(case.benchmark.split for case in report.cases)
    lines.append(
        "split_counts: "
        + ", ".join(
            f"{split}={split_counts.get(split, 0)}" for split in report.blueprint.allowed_splits
        )
    )
    if report.capacity is not None:
        capacity = report.capacity
        lines.extend(
            (
                "capacity: "
                f"calibration_split={capacity.calibration_split}, "
                f"calibration_version={capacity.calibration_version}, "
                f"tokenizer={capacity.reference_tokenizer}, "
                f"largest_faithful={capacity.largest_faithful_tokens}, "
                f"primary={capacity.primary_tokens}, tight={capacity.tight_tokens}",
                "capacity_history: "
                f"required>={capacity.required_history_tokens}, "
                f"minimum_observed={capacity.minimum_observed_history_tokens}",
            )
        )
    lines.append("coverage:")
    for item in report.coverage:
        marker = "PASS" if item.complete else "GAP"
        lines.append(f"  {marker} {item.split}/{item.item}: {item.actual}/{item.minimum}")
    lines.append(f"errors: {len(report.errors)}")
    lines.extend(f"  ERROR {message}" for message in report.errors)
    lines.append(f"warnings: {len(report.warnings)}")
    lines.extend(f"  WARN {message}" for message in report.warnings)
    status = "FAIL" if report.failed(require_complete=require_complete) else "PASS"
    lines.append(f"status: {status}")
    return "\n".join(lines)


def _json_report(report: LintReport, *, require_complete: bool) -> str:
    payload = {
        "blueprint": {
            "path": str(report.blueprint.path),
            "status": report.blueprint.status,
            "sha256": report.blueprint.source_hash,
        },
        "versions": list(report.versions),
        "compiled_sha256": report.file_hashes,
        "case_count": len(report.cases),
        "split_counts": dict(
            sorted(Counter(case.benchmark.split for case in report.cases).items())
        ),
        "capacity": (
            {
                "calibration_split": report.capacity.calibration_split,
                "calibration_version": report.capacity.calibration_version,
                "reference_tokenizer": report.capacity.reference_tokenizer,
                "largest_faithful_tokens": report.capacity.largest_faithful_tokens,
                "primary_tokens": report.capacity.primary_tokens,
                "tight_tokens": report.capacity.tight_tokens,
                "required_history_tokens": report.capacity.required_history_tokens,
                "minimum_observed_history_tokens": (
                    report.capacity.minimum_observed_history_tokens
                ),
            }
            if report.capacity is not None
            else None
        ),
        "coverage": [
            {
                "split": item.split,
                "item": item.item,
                "actual": item.actual,
                "minimum": item.minimum,
                "complete": item.complete,
            }
            for item in report.coverage
        ],
        "errors": report.errors,
        "warnings": report.warnings,
        "status": "fail" if report.failed(require_complete=require_complete) else "pass",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _discover_versions(data_dir: Path) -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in data_dir.glob("*.jsonl")))


def _parse_versions(raw: Iterable[str]) -> tuple[str, ...]:
    versions = []
    for item in raw:
        versions.extend(part.strip() for part in item.split(",") if part.strip())
    return tuple(versions)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint compiled procurement benchmark corpora and coverage."
    )
    parser.add_argument(
        "--versions",
        nargs="*",
        default=(),
        help="Compiled versions to lint (default: every JSONL in the data directory).",
    )
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--blueprint", type=Path, default=BLUEPRINT_PATH)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Treat any blueprint coverage gap as a failure.",
    )
    parser.add_argument("--json", action="store_true", help="Emit a JSON report.")
    args = parser.parse_args(argv)
    versions = _parse_versions(args.versions) or _discover_versions(args.data_dir)
    try:
        report = lint_corpora(
            versions=versions,
            blueprint_path=args.blueprint,
            data_dir=args.data_dir,
        )
    except (OSError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f"corpus lint failed before validation: {exc}", file=sys.stderr)
        return 1
    output = (
        _json_report(report, require_complete=args.require_complete)
        if args.json
        else _format_report(report, require_complete=args.require_complete)
    )
    print(output)
    return int(report.failed(require_complete=args.require_complete))


if __name__ == "__main__":
    raise SystemExit(main())
