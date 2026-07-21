#!/usr/bin/env python3
"""Measure agreement between blinded machine extractions and human consensus labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .annotations import typed_state_from_dict
from .memory import hash_payload
from .schemas import TypedCurrentState


SCHEMA_VERSION = "1"
RECORD_PRESENCE_FIELD = "__record_presence__"
STATE_FIELDS = (
    "issuer",
    "grantee",
    "effect",
    "action",
    "vendor",
    "allowed_categories",
    "max_amount",
    "currency",
    "valid_from",
    "valid_until",
    "status",
    "supersedes",
    "source_turn_ids",
)
AGREEMENT_FIELDS = (RECORD_PRESENCE_FIELD, *STATE_FIELDS)
_ARRAY_FIELDS = frozenset({"allowed_categories", "source_turn_ids"})
_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
_MISSING_RECORD = "missing_record"
_PRESENT_RECORD = "present_record"


@dataclass(frozen=True)
class ValidationSample:
    sample_id: str
    memory_id: str
    source_content_hash: str
    memory_text: str


@dataclass(frozen=True)
class HumanConsensus:
    sample_id: str
    memory_id: str
    source_content_hash: str
    state: TypedCurrentState


@dataclass(frozen=True)
class MachineExtraction:
    memory_id: str
    source_content_hash: str
    extractor_model: str
    state: TypedCurrentState


@dataclass(frozen=True)
class AgreementPair:
    sample: ValidationSample
    human: TypedCurrentState
    machine: TypedCurrentState


def measure_annotation_agreement(
    annotations_path: Path,
    samples_path: Path,
    consensus_path: Path,
    *,
    extractor_model: str | None = None,
) -> dict[str, Any]:
    """Join identity-checked labels and return deterministic agreement statistics."""

    samples = _load_samples(samples_path)
    consensus = _load_consensus(consensus_path, samples)
    machine, machine_reasons, selected_models = _load_machine_extractions(
        annotations_path,
        samples,
        extractor_model=extractor_model,
    )

    pairs = []
    exclusions: Counter[str] = Counter()
    for sample in samples.values():
        human_label = consensus.get(sample.sample_id)
        machine_label = machine.get(sample.memory_id)
        if human_label is not None and machine_label is not None:
            pairs.append(AgreementPair(sample, human_label.state, machine_label.state))
            continue
        reasons = []
        if human_label is None:
            reasons.append("missing_human_consensus")
        if machine_label is None:
            reasons.append(
                machine_reasons.get(sample.memory_id, "missing_machine_annotation")
            )
        exclusions["+".join(reasons)] += 1

    metrics = _agreement_metrics(pairs) if pairs else _empty_metrics()
    sample_count = len(samples)
    return {
        "schema_version": SCHEMA_VERSION,
        "inputs": {
            "annotations": str(annotations_path),
            "samples": str(samples_path),
            "human_consensus": str(consensus_path),
            "extractor_model_filter": extractor_model,
            "selected_extractor_models": sorted(selected_models),
        },
        "coverage": {
            "sampled": sample_count,
            "human_consensus": _coverage(len(consensus), sample_count),
            "accepted_machine": _coverage(len(machine), sample_count),
            "jointly_evaluable": _coverage(len(pairs), sample_count),
            "exclusions": dict(sorted(exclusions.items())),
        },
        "metrics": metrics,
        "metric_definitions": {
            "claim_level_macro_f1": (
                "For each memory, records become sets of atomic claims keyed by authorization "
                "ID. Record presence and every field value, including null, are claims. Set F1 "
                "is computed per memory (1.0 when both sets are empty) and averaged equally."
            ),
            "per_field_macro_f1": (
                "Records are aligned by authorization ID. For each field, categorical F1 is "
                "computed for every observed value and averaged equally across value categories; "
                "null and missing-record are ordinary, distinct categories. The reported aggregate "
                "is the unweighted mean across fields with comparisons."
            ),
            "cohens_kappa": (
                "Nominal Cohen's kappa over all aligned field judgments. Labels are prefixed by "
                "field, and null and missing-record values are included. Kappa is null when no "
                "judgments exist or expected agreement is exactly one."
            ),
        },
    }


def _load_samples(path: Path) -> dict[str, ValidationSample]:
    samples: dict[str, ValidationSample] = {}
    memory_ids: set[str] = set()
    expected = {
        "schema_version",
        "sample_id",
        "memory_id",
        "source_content_hash",
        "memory_text",
    }
    for line_number, row in _read_jsonl(path):
        _require_exact_keys(row, expected, f"sample at {path}:{line_number}")
        _require_schema_version(row, path, line_number)
        sample_id = _nonempty_text(row["sample_id"], "sample_id", path, line_number)
        memory_id = _nonempty_text(row["memory_id"], "memory_id", path, line_number)
        content_hash = _content_hash(row["source_content_hash"], path, line_number)
        memory_text = row["memory_text"]
        if not isinstance(memory_text, str):
            raise ValueError(f"memory_text must be a string at {path}:{line_number}")
        if hash_payload(memory_text) != content_hash:
            raise ValueError(f"memory text hash mismatch at {path}:{line_number}")
        if sample_id in samples:
            raise ValueError(f"duplicate sample_id {sample_id!r} at {path}:{line_number}")
        if memory_id in memory_ids:
            raise ValueError(f"duplicate sampled memory_id {memory_id!r} at {path}:{line_number}")
        samples[sample_id] = ValidationSample(
            sample_id=sample_id,
            memory_id=memory_id,
            source_content_hash=content_hash,
            memory_text=memory_text,
        )
        memory_ids.add(memory_id)
    if not samples:
        raise ValueError(f"no validation samples found in {path}")
    return samples


def _load_consensus(
    path: Path,
    samples: Mapping[str, ValidationSample],
) -> dict[str, HumanConsensus]:
    labels: dict[str, HumanConsensus] = {}
    expected = {
        "schema_version",
        "sample_id",
        "memory_id",
        "source_content_hash",
        "consensus_state",
    }
    for line_number, row in _read_jsonl(path):
        _require_exact_keys(row, expected, f"human consensus at {path}:{line_number}")
        _require_schema_version(row, path, line_number)
        sample_id = _nonempty_text(row["sample_id"], "sample_id", path, line_number)
        memory_id = _nonempty_text(row["memory_id"], "memory_id", path, line_number)
        content_hash = _content_hash(row["source_content_hash"], path, line_number)
        sample = samples.get(sample_id)
        if sample is None:
            raise ValueError(f"consensus references unknown sample_id at {path}:{line_number}")
        if memory_id != sample.memory_id:
            raise ValueError(f"consensus memory_id mismatch at {path}:{line_number}")
        if content_hash != sample.source_content_hash:
            raise ValueError(f"consensus content hash mismatch at {path}:{line_number}")
        if sample_id in labels:
            raise ValueError(f"duplicate consensus for {sample_id!r} at {path}:{line_number}")
        try:
            state = typed_state_from_dict(row["consensus_state"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid consensus_state at {path}:{line_number}: {exc}") from exc
        labels[sample_id] = HumanConsensus(sample_id, memory_id, content_hash, state)
    return labels


def _load_machine_extractions(
    path: Path,
    samples: Mapping[str, ValidationSample],
    *,
    extractor_model: str | None,
) -> tuple[dict[str, MachineExtraction], dict[str, str], set[str]]:
    samples_by_memory = {sample.memory_id: sample for sample in samples.values()}
    relevant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    required = {
        "memory_id",
        "source_content_hash",
        "status",
        "extracted_state",
        "extractor_model",
    }
    for line_number, row in _read_jsonl(path):
        missing = required - set(row)
        if missing:
            raise ValueError(
                f"machine annotation missing {sorted(missing)} at {path}:{line_number}"
            )
        memory_id = _nonempty_text(row["memory_id"], "memory_id", path, line_number)
        model = _nonempty_text(row["extractor_model"], "extractor_model", path, line_number)
        if memory_id not in samples_by_memory or (
            extractor_model is not None and model != extractor_model
        ):
            continue
        row = dict(row)
        row["_line_number"] = line_number
        relevant[memory_id].append(row)

    extractions: dict[str, MachineExtraction] = {}
    reasons: dict[str, str] = {}
    selected_models: set[str] = set()
    for memory_id, sample in samples_by_memory.items():
        records = relevant.get(memory_id, [])
        accepted = [record for record in records if record["status"] == "accepted"]
        if len(accepted) > 1:
            models = sorted({str(record["extractor_model"]) for record in accepted})
            raise ValueError(
                f"multiple accepted annotations for {memory_id}: models={models}; "
                "select one with --extractor-model"
            )
        if not accepted:
            statuses = sorted({str(record["status"]) for record in records})
            reasons[memory_id] = (
                "missing_machine_annotation"
                if not records
                else f"machine_not_accepted:{','.join(statuses)}"
            )
            continue
        record = accepted[0]
        line_number = int(record["_line_number"])
        content_hash = _content_hash(record["source_content_hash"], path, line_number)
        if content_hash != sample.source_content_hash:
            raise ValueError(f"machine annotation content hash mismatch at {path}:{line_number}")
        try:
            state = typed_state_from_dict(record["extracted_state"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid accepted machine extraction at {path}:{line_number}: {exc}"
            ) from exc
        model = str(record["extractor_model"])
        selected_models.add(model)
        extractions[memory_id] = MachineExtraction(memory_id, content_hash, model, state)
    return extractions, reasons, selected_models


def _agreement_metrics(pairs: Sequence[AgreementPair]) -> dict[str, Any]:
    claim_scores = []
    exact_count = 0
    field_pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for pair in pairs:
        human_claims = _claim_set(pair.human)
        machine_claims = _claim_set(pair.machine)
        claim_scores.append(_set_f1(human_claims, machine_claims))
        exact_count += human_claims == machine_claims
        for field, judgments in _aligned_field_judgments(pair.human, pair.machine).items():
            field_pairs[field].extend(judgments)

    field_metrics = []
    for field in AGREEMENT_FIELDS:
        judgments = field_pairs.get(field, [])
        field_metrics.append(
            {
                "field": field,
                "judgments": len(judgments),
                "macro_f1": _categorical_macro_f1(judgments),
                "cohens_kappa": _cohens_kappa(judgments),
                "exact_agreement": _exact_agreement(judgments),
            }
        )
    scored_field_f1 = [
        row["macro_f1"] for row in field_metrics if row["macro_f1"] is not None
    ]
    pooled = [
        (_prefixed_label(field, human), _prefixed_label(field, machine))
        for field, judgments in field_pairs.items()
        for human, machine in judgments
    ]
    return {
        "evaluable_memories": len(pairs),
        "claim_level_macro_f1": sum(claim_scores) / len(claim_scores),
        "exact_state_agreement": exact_count / len(pairs),
        "per_field_macro_f1": (
            sum(scored_field_f1) / len(scored_field_f1) if scored_field_f1 else None
        ),
        "cohens_kappa": _cohens_kappa(pooled),
        "aligned_field_judgments": len(pooled),
        "fields": field_metrics,
    }


def _empty_metrics() -> dict[str, Any]:
    return {
        "evaluable_memories": 0,
        "claim_level_macro_f1": None,
        "exact_state_agreement": None,
        "per_field_macro_f1": None,
        "cohens_kappa": None,
        "aligned_field_judgments": 0,
        "fields": [
            {
                "field": field,
                "judgments": 0,
                "macro_f1": None,
                "cohens_kappa": None,
                "exact_agreement": None,
            }
            for field in AGREEMENT_FIELDS
        ],
    }


def _claim_set(state: TypedCurrentState) -> set[tuple[str, str, str]]:
    claims: set[tuple[str, str, str]] = set()
    for record in state.authorizations:
        data = record.to_dict()
        authorization_id = record.authorization_id
        claims.add((authorization_id, RECORD_PRESENCE_FIELD, _PRESENT_RECORD))
        for field in STATE_FIELDS:
            claims.add((authorization_id, field, _value_label(field, data[field])))
    return claims


def _aligned_field_judgments(
    human: TypedCurrentState,
    machine: TypedCurrentState,
) -> dict[str, list[tuple[str, str]]]:
    human_records = {record.authorization_id: record.to_dict() for record in human.authorizations}
    machine_records = {
        record.authorization_id: record.to_dict() for record in machine.authorizations
    }
    judgments: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for authorization_id in sorted(set(human_records) | set(machine_records)):
        human_record = human_records.get(authorization_id)
        machine_record = machine_records.get(authorization_id)
        judgments[RECORD_PRESENCE_FIELD].append(
            (
                _PRESENT_RECORD if human_record is not None else _MISSING_RECORD,
                _PRESENT_RECORD if machine_record is not None else _MISSING_RECORD,
            )
        )
        for field in STATE_FIELDS:
            human_label = (
                _MISSING_RECORD
                if human_record is None
                else _value_label(field, human_record[field])
            )
            machine_label = (
                _MISSING_RECORD
                if machine_record is None
                else _value_label(field, machine_record[field])
            )
            judgments[field].append((human_label, machine_label))
    return judgments


def _value_label(field: str, value: Any) -> str:
    if field in _ARRAY_FIELDS and value is not None:
        value = sorted(value)
    return "value:" + json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _set_f1(human: set[Any], machine: set[Any]) -> float:
    if not human and not machine:
        return 1.0
    return 2 * len(human & machine) / (len(human) + len(machine))


def _categorical_macro_f1(judgments: Sequence[tuple[str, str]]) -> float | None:
    if not judgments:
        return None
    labels = sorted({label for pair in judgments for label in pair})
    scores = []
    for label in labels:
        true_positive = sum(human == label and machine == label for human, machine in judgments)
        false_positive = sum(human != label and machine == label for human, machine in judgments)
        false_negative = sum(human == label and machine != label for human, machine in judgments)
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(2 * true_positive / denominator if denominator else 0.0)
    return sum(scores) / len(scores)


def _cohens_kappa(judgments: Sequence[tuple[str, str]]) -> float | None:
    if not judgments:
        return None
    total = len(judgments)
    human_counts = Counter(human for human, _ in judgments)
    machine_counts = Counter(machine for _, machine in judgments)
    observed = sum(human == machine for human, machine in judgments) / total
    expected = sum(
        human_counts[label] * machine_counts[label]
        for label in set(human_counts) | set(machine_counts)
    ) / (total * total)
    if math.isclose(expected, 1.0, rel_tol=0.0, abs_tol=1e-15):
        return None
    return (observed - expected) / (1 - expected)


def _exact_agreement(judgments: Sequence[tuple[str, str]]) -> float | None:
    if not judgments:
        return None
    return sum(human == machine for human, machine in judgments) / len(judgments)


def _prefixed_label(field: str, label: str) -> str:
    return json.dumps([field, label], ensure_ascii=False, separators=(",", ":"))


def _coverage(count: int, denominator: int) -> dict[str, int | float]:
    return {
        "count": count,
        "denominator": denominator,
        "rate": count / denominator if denominator else 0.0,
    }


def _read_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"expected a JSON object at {path}:{line_number}")
            yield line_number, row


def _require_schema_version(row: Mapping[str, Any], path: Path, line_number: int) -> None:
    if row["schema_version"] != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION!r} at {path}:{line_number}")


def _require_exact_keys(row: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing = expected - set(row)
    unknown = set(row) - expected
    if missing or unknown:
        raise ValueError(
            f"{label} keys differ: missing={sorted(missing)}, unknown={sorted(unknown)}"
        )


def _nonempty_text(value: Any, name: str, path: Path, line_number: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string at {path}:{line_number}")
    return value


def _content_hash(value: Any, path: Path, line_number: int) -> str:
    if not isinstance(value, str) or _HASH_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid source_content_hash at {path}:{line_number}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _print_report(report: Mapping[str, Any]) -> None:
    coverage = report["coverage"]
    metrics = report["metrics"]
    print("Blinded free-text annotation agreement\n")
    print(f"  sampled memories: {coverage['sampled']}")
    for label in ("human_consensus", "accepted_machine", "jointly_evaluable"):
        row = coverage[label]
        print(
            f"  {label.replace('_', ' ')}: {row['count']}/{row['denominator']} "
            f"({row['rate']:.1%})"
        )
    if coverage["exclusions"]:
        detail = ", ".join(
            f"{name}={count}" for name, count in coverage["exclusions"].items()
        )
        print(f"  exclusions: {detail}")
    print()
    if metrics["evaluable_memories"] == 0:
        print("No jointly evaluable memories; agreement metrics are unavailable.")
        return
    print(f"  claim-level macro-F1: {metrics['claim_level_macro_f1']:.4f}")
    print(f"  per-field macro-F1: {metrics['per_field_macro_f1']:.4f}")
    kappa = metrics["cohens_kappa"]
    print(f"  Cohen's kappa: {'undefined' if kappa is None else f'{kappa:.4f}'}")
    print(f"  exact state agreement: {metrics['exact_state_agreement']:.1%}")
    print(f"  aligned field judgments: {metrics['aligned_field_judgments']}")
    print("\nPer field")
    for row in metrics["fields"]:
        f1 = "n/a" if row["macro_f1"] is None else f"{row['macro_f1']:.4f}"
        field_kappa = (
            "undefined" if row["cohens_kappa"] is None else f"{row['cohens_kappa']:.4f}"
        )
        print(
            f"  {row['field']}: n={row['judgments']}, macro-F1={f1}, "
            f"kappa={field_kappa}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Human-consensus JSONL schema (one object per completed sample):
  {"schema_version":"1","sample_id":"...","memory_id":"...",
   "source_content_hash":"<64 lowercase hex characters>",
   "consensus_state":{"schema_version":"2","authorizations":[...]}}

The consensus state uses the same strict fields as the blinded extraction tool. It may contain
an empty authorizations array. Do not add canonical-ledger data, probe labels, or executor outcomes.
Null field values and records missing from one label are included as agreement categories.
""",
    )
    parser.add_argument("annotations", type=Path, help="machine annotation JSONL")
    parser.add_argument("samples", type=Path, help="blinded human-validation sample JSONL")
    parser.add_argument("human_consensus", type=Path, help="adjudicated consensus JSONL")
    parser.add_argument(
        "--extractor-model",
        default=None,
        help="select one extractor model when the annotation file contains multiple models",
    )
    parser.add_argument("--json-output", type=Path, default=None)
    args = parser.parse_args()

    report = measure_annotation_agreement(
        args.annotations,
        args.samples,
        args.human_consensus,
        extractor_model=args.extractor_model,
    )
    report["input_sha256"] = {
        "annotations": _sha256_file(args.annotations),
        "samples": _sha256_file(args.samples),
        "human_consensus": _sha256_file(args.human_consensus),
    }
    if args.json_output is not None:
        if args.json_output.exists():
            raise FileExistsError(f"output already exists: {args.json_output}")
        args.json_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    _print_report(report)


if __name__ == "__main__":
    main()
