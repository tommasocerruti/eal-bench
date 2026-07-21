from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import tempfile
from copy import deepcopy
from collections import Counter
from collections.abc import Callable, Collection
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from ..cases import load_cases
from ..compile_corpus import compile_case
from ..schemas import AuthorizationCase
from .constants import CONTROL_CORPUS_VERSION, CONTROL_PROTOCOL_VERSION


PACKAGE_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = PACKAGE_DIR / "authoring_protocol.yaml"
COMPILED_PACKAGE_PATH = PACKAGE_DIR / "compiled" / CONTROL_CORPUS_VERSION
FIXTURE_DIR = PACKAGE_DIR / "fixture"
_AUTHOR_PATTERN = re.compile(r"^author_[a-z0-9]{2,32}$")
_REF_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_WORD_PATTERN = re.compile(r"\b[\w]+(?:[’'-][\w]+)*\b", re.UNICODE)
_FORBIDDEN_VISIBLE_PHRASES = (
    "benchmark",
    "canonical ledger",
    "evaluation-aware",
    "ground truth",
    "memory writer",
    "future probe",
    "transaction probe",
)
_REQUIRED_ATTESTATIONS = {
    "benchmark_material_unseen",
    "research_hypotheses_unseen",
    "no_generative_ai",
    "synthetic_only",
    "no_confidential_material",
    "no_personal_data",
    "consent_to_research_use",
}
_REQUIRED_REVIEW_ATTESTATIONS = {
    "structural_normalization_only",
    "substantive_changes_returned_to_author",
    "canonical_state_derived_from_visible_history",
    "synthetic_data_reconfirmed",
}
_REQUIRED_COLLECTION_FIELDS = {
    "histories",
    "minimum_authors",
    "maximum_histories_per_author",
    "generative_ai_drafting_allowed",
    "synthetic_only",
    "substantive_project_rewriting_allowed",
    "required_scope_fields",
}
_REQUIRED_SCOPE_FIELDS = {
    "grantee",
    "action",
    "vendor",
    "category",
    "maximum_amount",
    "currency",
    "valid_from",
    "valid_until",
}
_LIFECYCLES = {"issue_only", "issue_patch", "issue_revoke_replace"}
_DIMENSIONS = ("amount", "time", "category")
_PACKAGE_FILES = {
    "protocol": "protocol.json",
    "submissions": "submissions.jsonl",
    "enrichments": "enrichments.jsonl",
    "matches": "control_matches.json",
    "cases": "cases.jsonl",
}


class ControlAuthoringError(ValueError):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ControlAuthoringError(f"cannot load YAML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ControlAuthoringError(f"{path} must contain one YAML object")
    return value


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _canonical_jsonl(values: Sequence[Mapping[str, Any]]) -> str:
    return "".join(f"{_canonical_json(value)}\n" for value in values)


def _validate_protocol_requirements(
    requirements: Mapping[str, Any],
    *,
    brief_count: int,
    core_shape: bool,
) -> None:
    _require_keys(
        requirements,
        required=_REQUIRED_COLLECTION_FIELDS,
        label="authoring protocol collection_requirements",
    )
    histories = requirements["histories"]
    minimum_authors = requirements["minimum_authors"]
    maximum_per_author = requirements["maximum_histories_per_author"]
    for field, value in (
        ("histories", histories),
        ("minimum_authors", minimum_authors),
        ("maximum_histories_per_author", maximum_per_author),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ControlAuthoringError(
                f"authoring protocol {field} must be a positive integer"
            )
    if histories != brief_count:
        raise ControlAuthoringError(
            "authoring protocol histories must equal the number of structural briefs"
        )
    if minimum_authors > histories:
        raise ControlAuthoringError(
            "authoring protocol minimum_authors exceeds its history count"
        )
    if maximum_per_author * minimum_authors < histories:
        raise ControlAuthoringError(
            "authoring protocol author limits cannot cover every history"
        )
    fixed = {
        "generative_ai_drafting_allowed": False,
        "synthetic_only": True,
        "substantive_project_rewriting_allowed": False,
    }
    for field, expected in fixed.items():
        if requirements[field] is not expected:
            raise ControlAuthoringError(
                f"authoring protocol {field} must be {expected!r}"
            )
    scope_fields = requirements["required_scope_fields"]
    if (
        not isinstance(scope_fields, list)
        or len(scope_fields) != len(set(scope_fields))
        or set(scope_fields) != _REQUIRED_SCOPE_FIELDS
    ):
        raise ControlAuthoringError(
            "authoring protocol required_scope_fields must define the exact "
            "procurement authorization scope"
        )
    if core_shape and (
        histories != 12
        or minimum_authors < 4
        or maximum_per_author > 3
    ):
        raise ControlAuthoringError(
            "core protocol requires 12 histories, at least four authors, "
            "and at most three histories per author"
        )


def _validate_brief(
    brief: Mapping[str, Any],
    *,
    index: int,
    core_shape: bool,
) -> None:
    label = f"authoring protocol briefs[{index}]"
    _require_keys(
        brief,
        required={
            "brief_id",
            "lifecycle",
            "operational_setting",
            "target_blocks",
            "turn_range",
            "role_range",
            "history_length_band",
            "history_word_range",
            "turn_word_range",
        },
        label=label,
    )
    brief_id = brief["brief_id"]
    if not isinstance(brief_id, str) or not _REF_PATTERN.fullmatch(brief_id):
        raise ControlAuthoringError(f"{label}.brief_id is invalid")
    if brief["lifecycle"] not in _LIFECYCLES:
        raise ControlAuthoringError(f"{label}.lifecycle is invalid")
    _validate_visible_text(
        brief["operational_setting"],
        f"{label}.operational_setting",
    )
    target_blocks = brief["target_blocks"]
    minimum_blocks = 5 if core_shape else 2
    if (
        not isinstance(target_blocks, int)
        or isinstance(target_blocks, bool)
        or not minimum_blocks <= target_blocks <= 8
    ):
        raise ControlAuthoringError(
            f"{label}.target_blocks must be between {minimum_blocks} and 8"
        )
    for field, minimum, maximum in (
        ("turn_range", 40 if core_shape else 4, 100),
        ("role_range", 2, 100),
    ):
        values = brief[field]
        if (
            not isinstance(values, list)
            or len(values) != 2
            or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in values
            )
            or not minimum <= values[0] <= values[1] <= maximum
        ):
            raise ControlAuthoringError(
                f"{label}.{field} must be an ordered range within "
                f"{minimum}..{maximum}"
            )
    if brief["history_length_band"] not in {"fixture", "medium", "long"}:
        raise ControlAuthoringError(f"{label}.history_length_band is invalid")
    if core_shape and brief["history_length_band"] == "fixture":
        raise ControlAuthoringError(
            f"{label}.history_length_band cannot be fixture in the core protocol"
        )
    for field, minimum, maximum in (
        ("history_word_range", 1, 5_000),
        ("turn_word_range", 1, 200),
    ):
        values = brief[field]
        if (
            not isinstance(values, list)
            or len(values) != 2
            or any(
                not isinstance(value, int) or isinstance(value, bool)
                for value in values
            )
            or not minimum <= values[0] <= values[1] <= maximum
        ):
            raise ControlAuthoringError(
                f"{label}.{field} must be an ordered range within "
                f"{minimum}..{maximum}"
            )
    if core_shape:
        history_word_range = brief["history_word_range"]
        if not 1_000 <= history_word_range[0] <= history_word_range[1] <= 4_000:
            raise ControlAuthoringError(
                f"{label}.history_word_range must remain within the calibrated "
                "core envelope of 1000..4000 words"
            )
        if brief["turn_word_range"] != [10, 60]:
            raise ControlAuthoringError(
                f"{label}.turn_word_range must be [10, 60] for core controls"
            )
    turn_range = brief["turn_range"]
    turn_word_range = brief["turn_word_range"]
    history_word_range = brief["history_word_range"]
    possible_minimum = turn_range[0] * turn_word_range[0]
    possible_maximum = turn_range[1] * turn_word_range[1]
    if (
        history_word_range[1] < possible_minimum
        or history_word_range[0] > possible_maximum
    ):
        raise ControlAuthoringError(
            f"{label}.history_word_range cannot be reached within its turn and "
            "per-turn word ranges"
        )


def _validate_authoring_protocol(
    protocol: Mapping[str, Any],
    *,
    expected_briefs: int | None = 12,
    label: str = "authoring protocol",
) -> dict[str, Any]:
    if protocol.get("protocol_version") != CONTROL_PROTOCOL_VERSION:
        raise ControlAuthoringError(
            f"{label} must use protocol_version={CONTROL_PROTOCOL_VERSION!r}"
        )
    requirements = protocol.get("collection_requirements")
    briefs = protocol.get("briefs")
    if not isinstance(requirements, dict) or not isinstance(briefs, list):
        raise ControlAuthoringError(f"{label} has an invalid protocol structure")
    if expected_briefs is not None and len(briefs) != expected_briefs:
        raise ControlAuthoringError(
            f"{label} must contain exactly {expected_briefs} authoring briefs"
        )
    ids = [brief.get("brief_id") for brief in briefs if isinstance(brief, dict)]
    if len(ids) != len(briefs) or len(set(ids)) != len(briefs):
        raise ControlAuthoringError(f"{label} brief IDs must be unique")
    core_shape = expected_briefs == 12
    _validate_protocol_requirements(
        requirements,
        brief_count=len(briefs),
        core_shape=core_shape,
    )
    for index, brief in enumerate(briefs):
        _validate_brief(
            brief,
            index=index,
            core_shape=core_shape,
        )
    return dict(protocol)


def load_authoring_protocol(
    path: Path = PROTOCOL_PATH,
    *,
    expected_briefs: int | None = 12,
) -> dict[str, Any]:
    return _validate_authoring_protocol(
        _load_yaml(path),
        expected_briefs=expected_briefs,
        label=str(path),
    )


def _briefs_by_id(protocol: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    briefs = protocol.get("briefs")
    if not isinstance(briefs, list):
        raise ControlAuthoringError("protocol briefs must be an array")
    return {
        str(brief["brief_id"]): brief
        for brief in briefs
        if isinstance(brief, Mapping) and isinstance(brief.get("brief_id"), str)
    }


def _require_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    label: str,
) -> None:
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise ControlAuthoringError(f"{label} is missing fields: {sorted(missing)}")
    if unknown:
        raise ControlAuthoringError(f"{label} has unexpected fields: {sorted(unknown)}")


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not _UTC_PATTERN.fullmatch(value):
        raise ControlAuthoringError(f"{label} must be a canonical UTC timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ControlAuthoringError(f"{label} is not a valid timestamp") from exc


def _validate_visible_text(text: Any, label: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ControlAuthoringError(f"{label} must be non-empty text")
    lowered = text.casefold()
    found = [phrase for phrase in _FORBIDDEN_VISIBLE_PHRASES if phrase in lowered]
    if found:
        raise ControlAuthoringError(
            f"{label} contains research-facing language: {', '.join(found)}"
        )
    return text


def _visible_word_count(text: str) -> int:
    return len(_WORD_PATTERN.findall(text))


def _validate_case(
    case: Mapping[str, Any],
    brief: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    _require_keys(
        case,
        required={"working_title", "policy", "authorized_issuers", "blocks"},
        label=label,
    )
    _validate_visible_text(case["working_title"], f"{label}.working_title")
    _validate_visible_text(case["policy"], f"{label}.policy")
    issuers = case["authorized_issuers"]
    if (
        not isinstance(issuers, list)
        or not issuers
        or not all(isinstance(item, str) and _REF_PATTERN.fullmatch(item) for item in issuers)
    ):
        raise ControlAuthoringError(
            f"{label}.authorized_issuers must be non-empty normalized role IDs"
        )
    if len(issuers) != len(set(issuers)):
        raise ControlAuthoringError(
            f"{label}.authorized_issuers must not contain duplicates"
        )

    blocks = case["blocks"]
    expected_blocks = brief.get("target_blocks")
    if not isinstance(blocks, list) or len(blocks) != expected_blocks:
        raise ControlAuthoringError(
            f"{label} must contain exactly {expected_blocks} conversation blocks"
        )
    block_refs: set[str] = set()
    turn_refs: set[str] = set()
    actors: set[str] = set()
    turn_count = 0
    turn_word_counts: list[tuple[str, int]] = []
    previous_time: datetime | None = None
    previous_block_end: datetime | None = None
    for block_index, block in enumerate(blocks):
        block_label = f"{label}.blocks[{block_index}]"
        if not isinstance(block, Mapping):
            raise ControlAuthoringError(f"{block_label} must be an object")
        _require_keys(
            block,
            required={"ref", "title", "ended_at", "turns"},
            label=block_label,
        )
        block_ref = block["ref"]
        if not isinstance(block_ref, str) or not _REF_PATTERN.fullmatch(block_ref):
            raise ControlAuthoringError(f"{block_label}.ref is invalid")
        if block_ref in block_refs:
            raise ControlAuthoringError(f"{label} repeats block ref {block_ref!r}")
        block_refs.add(block_ref)
        _validate_visible_text(block["title"], f"{block_label}.title")
        ended_at = _timestamp(block["ended_at"], f"{block_label}.ended_at")
        if previous_block_end is not None and ended_at <= previous_block_end:
            raise ControlAuthoringError(
                f"{block_label}.ended_at must follow the previous block"
            )
        turns = block["turns"]
        if not isinstance(turns, list) or not turns:
            raise ControlAuthoringError(f"{block_label}.turns must be non-empty")
        for turn_index, turn in enumerate(turns):
            turn_label = f"{block_label}.turns[{turn_index}]"
            if not isinstance(turn, Mapping):
                raise ControlAuthoringError(f"{turn_label} must be an object")
            _require_keys(
                turn,
                required={"ref", "actor_id", "speaker", "content", "occurred_at"},
                label=turn_label,
            )
            turn_ref = turn["ref"]
            actor_id = turn["actor_id"]
            if not isinstance(turn_ref, str) or not _REF_PATTERN.fullmatch(turn_ref):
                raise ControlAuthoringError(f"{turn_label}.ref is invalid")
            if turn_ref in turn_refs:
                raise ControlAuthoringError(f"{label} repeats turn ref {turn_ref!r}")
            turn_refs.add(turn_ref)
            if not isinstance(actor_id, str) or not _REF_PATTERN.fullmatch(actor_id):
                raise ControlAuthoringError(f"{turn_label}.actor_id is invalid")
            actors.add(actor_id)
            _validate_visible_text(turn["speaker"], f"{turn_label}.speaker")
            content = _validate_visible_text(
                turn["content"],
                f"{turn_label}.content",
            )
            turn_word_counts.append((turn_ref, _visible_word_count(content)))
            occurred_at = _timestamp(turn["occurred_at"], f"{turn_label}.occurred_at")
            if previous_time is not None and occurred_at <= previous_time:
                raise ControlAuthoringError(
                    f"{turn_label} must follow the previous turn"
                )
            if (
                previous_block_end is not None
                and turn_index == 0
                and occurred_at <= previous_block_end
            ):
                raise ControlAuthoringError(
                    f"{turn_label} must occur after the previous block ended"
                )
            if occurred_at > ended_at:
                raise ControlAuthoringError(f"{turn_label} occurs after its block ended")
            previous_time = occurred_at
            turn_count += 1
        previous_block_end = ended_at

    turn_range = brief.get("turn_range")
    role_range = brief.get("role_range")
    if (
        not isinstance(turn_range, list)
        or len(turn_range) != 2
        or not all(isinstance(item, int) for item in turn_range)
    ):
        raise ControlAuthoringError("brief turn_range is invalid")
    if not turn_range[0] <= turn_count <= turn_range[1]:
        raise ControlAuthoringError(
            f"{label} has {turn_count} turns; expected {turn_range[0]}..{turn_range[1]}"
        )
    if (
        not isinstance(role_range, list)
        or len(role_range) != 2
        or not all(isinstance(item, int) for item in role_range)
    ):
        raise ControlAuthoringError("brief role_range is invalid")
    if not role_range[0] <= len(actors) <= role_range[1]:
        raise ControlAuthoringError(
            f"{label} has {len(actors)} roles; expected {role_range[0]}..{role_range[1]}"
        )
    history_word_range = brief.get("history_word_range")
    turn_word_range = brief.get("turn_word_range")
    if (
        not isinstance(history_word_range, list)
        or len(history_word_range) != 2
        or not all(isinstance(item, int) for item in history_word_range)
    ):
        raise ControlAuthoringError("brief history_word_range is invalid")
    if (
        not isinstance(turn_word_range, list)
        or len(turn_word_range) != 2
        or not all(isinstance(item, int) for item in turn_word_range)
    ):
        raise ControlAuthoringError("brief turn_word_range is invalid")
    history_words = sum(count for _, count in turn_word_counts)
    if not history_word_range[0] <= history_words <= history_word_range[1]:
        raise ControlAuthoringError(
            f"{label} has {history_words} words in visible turn content; expected "
            f"{history_word_range[0]}..{history_word_range[1]}"
        )
    turn_word_outliers = [
        (turn_ref, count)
        for turn_ref, count in turn_word_counts
        if not turn_word_range[0] <= count <= turn_word_range[1]
    ]
    if turn_word_outliers:
        rendered = ", ".join(
            f"{turn_ref}={count}" for turn_ref, count in turn_word_outliers[:8]
        )
        if len(turn_word_outliers) > 8:
            rendered += f", and {len(turn_word_outliers) - 8} more"
        raise ControlAuthoringError(
            f"{label} has turn word counts outside "
            f"{turn_word_range[0]}..{turn_word_range[1]}: {rendered}"
        )
    if not any(
        turn["actor_id"] in issuers
        for block in blocks
        for turn in block["turns"]
    ):
        raise ControlAuthoringError(
            f"{label} contains no turn from an authorized issuer"
        )
    return {
        "blocks": len(blocks),
        "turns": turn_count,
        "roles": len(actors),
        "history_length_band": str(brief["history_length_band"]),
        "history_words": history_words,
        "minimum_turn_words": min(count for _, count in turn_word_counts),
        "maximum_turn_words": max(count for _, count in turn_word_counts),
        "visible_history_sha256": _canonical_hash(case),
    }


def validate_submission(
    submission: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any] | None = None,
    label: str = "control submission",
) -> dict[str, Any]:
    selected_protocol = (
        _validate_authoring_protocol(protocol, expected_briefs=None)
        if protocol is not None
        else load_authoring_protocol()
    )
    _require_keys(
        submission,
        required={
            "schema_version",
            "protocol_version",
            "brief_id",
            "author_id",
            "attestations",
            "case",
        },
        label=label,
    )
    if submission["schema_version"] != "1":
        raise ControlAuthoringError(f"{label}.schema_version must be '1'")
    if submission["protocol_version"] != CONTROL_PROTOCOL_VERSION:
        raise ControlAuthoringError(
            f"{label}.protocol_version must be {CONTROL_PROTOCOL_VERSION!r}"
        )
    brief_id = submission["brief_id"]
    briefs = _briefs_by_id(selected_protocol)
    if brief_id not in briefs:
        raise ControlAuthoringError(f"{label} references unknown brief {brief_id!r}")
    author_id = submission["author_id"]
    if not isinstance(author_id, str) or not _AUTHOR_PATTERN.fullmatch(author_id):
        raise ControlAuthoringError(f"{label}.author_id must match author_<opaque-id>")
    attestations = submission["attestations"]
    if not isinstance(attestations, Mapping):
        raise ControlAuthoringError(f"{label}.attestations must be an object")
    _require_keys(
        attestations,
        required=_REQUIRED_ATTESTATIONS,
        label=f"{label}.attestations",
    )
    rejected = sorted(key for key, value in attestations.items() if value is not True)
    if rejected:
        raise ControlAuthoringError(
            f"{label} has unaccepted attestations: {', '.join(rejected)}"
        )
    case = submission["case"]
    if not isinstance(case, Mapping):
        raise ControlAuthoringError(f"{label}.case must be an object")
    stats = _validate_case(case, briefs[str(brief_id)], label=f"{label}.case")
    return {
        "brief_id": str(brief_id),
        "author_id": author_id,
        **stats,
    }


def validate_collection(
    submissions: Sequence[Mapping[str, Any]],
    *,
    protocol: Mapping[str, Any] | None = None,
    core_protocol: bool = True,
) -> dict[str, Any]:
    selected_protocol = (
        _validate_authoring_protocol(
            protocol,
            expected_briefs=12 if core_protocol else None,
        )
        if protocol is not None
        else load_authoring_protocol()
    )
    rows = [
        validate_submission(
            submission,
            protocol=selected_protocol,
            label=f"submission[{index}]",
        )
        for index, submission in enumerate(submissions)
    ]
    requirements = selected_protocol["collection_requirements"]
    expected = int(requirements["histories"]) if core_protocol else len(rows)
    if len(rows) != expected:
        raise ControlAuthoringError(
            f"collection contains {len(rows)} submissions; expected {expected}"
        )
    brief_ids = [row["brief_id"] for row in rows]
    if len(set(brief_ids)) != len(brief_ids):
        raise ControlAuthoringError("collection contains duplicate brief IDs")
    visible_hashes = [row["visible_history_sha256"] for row in rows]
    if len(visible_hashes) != len(set(visible_hashes)):
        raise ControlAuthoringError(
            "collection contains duplicate visible histories"
        )
    authors = Counter(row["author_id"] for row in rows)
    if core_protocol:
        expected_briefs = set(_briefs_by_id(selected_protocol))
        missing = sorted(expected_briefs - set(brief_ids))
        if missing:
            raise ControlAuthoringError(
                f"collection is missing briefs: {', '.join(missing)}"
            )
        minimum_authors = int(requirements["minimum_authors"])
        maximum_per_author = int(requirements["maximum_histories_per_author"])
        if len(authors) < minimum_authors:
            raise ControlAuthoringError(
                "core controls require at least "
                f"{minimum_authors} authors"
            )
        overloaded = sorted(
            author
            for author, count in authors.items()
            if count > maximum_per_author
        )
        if overloaded:
            raise ControlAuthoringError(
                f"authors may contribute at most {maximum_per_author} histories: "
                + ", ".join(overloaded)
            )
    return {
        "protocol_version": CONTROL_PROTOCOL_VERSION,
        "core_protocol": core_protocol,
        "submissions": len(rows),
        "authors": len(authors),
        "maximum_histories_per_author": max(authors.values(), default=0),
        "brief_ids": sorted(brief_ids),
        "visible_history_hashes": sorted(visible_hashes),
        "history_word_counts": {
            row["brief_id"]: row["history_words"]
            for row in sorted(rows, key=lambda item: item["brief_id"])
        },
    }


def _normalize_match_manifest(
    manifest: Mapping[str, Any],
    *,
    core_protocol: bool = True,
    expected_count: int | None = None,
) -> list[dict[str, str]]:
    _require_keys(
        manifest,
        required={"schema_version", "matches"},
        label="control match manifest",
    )
    if manifest["schema_version"] != 1:
        raise ControlAuthoringError("control match manifest schema_version must be 1")
    matches = manifest["matches"]
    if not isinstance(matches, list):
        raise ControlAuthoringError("control match manifest matches must be an array")
    expected = (
        expected_count
        if expected_count is not None
        else 12 if core_protocol else len(matches)
    )
    if len(matches) != expected:
        raise ControlAuthoringError(
            f"control match manifest has {len(matches)} rows; expected {expected}"
        )
    required = {"match_id", "benchmark_case_id", "control_case_id", "author_id"}
    normalized = []
    for index, row in enumerate(matches):
        if not isinstance(row, Mapping):
            raise ControlAuthoringError(f"matches[{index}] must be an object")
        _require_keys(row, required=required, label=f"matches[{index}]")
        values = {key: row[key] for key in required}
        if not all(isinstance(value, str) and value for value in values.values()):
            raise ControlAuthoringError(f"matches[{index}] fields must be non-empty strings")
        for field in ("match_id", "benchmark_case_id", "control_case_id"):
            if not _REF_PATTERN.fullmatch(values[field]):
                raise ControlAuthoringError(
                    f"matches[{index}].{field} is invalid"
                )
        if not _AUTHOR_PATTERN.fullmatch(values["author_id"]):
            raise ControlAuthoringError(f"matches[{index}].author_id is invalid")
        normalized.append(values)
    for field in ("match_id", "benchmark_case_id", "control_case_id"):
        values = [row[field] for row in normalized]
        if len(values) != len(set(values)):
            raise ControlAuthoringError(f"control match manifest repeats {field}")
    authors = Counter(row["author_id"] for row in normalized)
    if core_protocol and len(authors) < 4:
        raise ControlAuthoringError("core matches require at least four authors")
    overloaded = sorted(author for author, count in authors.items() if count > 3)
    if core_protocol and overloaded:
        raise ControlAuthoringError(
            "match manifest assigns more than three controls to: "
            + ", ".join(overloaded)
        )
    return normalized


def validate_match_manifest(
    manifest: Mapping[str, Any],
    *,
    core_protocol: bool = True,
    expected_count: int | None = None,
    expected_controls: Mapping[str, str] | None = None,
    expected_benchmark_case_ids: Collection[str] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_match_manifest(
        manifest,
        core_protocol=core_protocol,
        expected_count=expected_count,
    )
    authors = Counter(row["author_id"] for row in normalized)
    if expected_controls is not None:
        actual_controls = {
            row["control_case_id"]: row["author_id"] for row in normalized
        }
        if actual_controls.keys() != expected_controls.keys():
            missing = sorted(expected_controls.keys() - actual_controls.keys())
            unexpected = sorted(actual_controls.keys() - expected_controls.keys())
            raise ControlAuthoringError(
                "match manifest control cases differ from validated enrichments; "
                f"missing={missing}, unexpected={unexpected}"
            )
        mismatched_authors = sorted(
            case_id
            for case_id, author_id in expected_controls.items()
            if actual_controls[case_id] != author_id
        )
        if mismatched_authors:
            raise ControlAuthoringError(
                "match manifest author IDs differ from their submissions for: "
                + ", ".join(mismatched_authors)
            )
    if expected_benchmark_case_ids is not None:
        actual_benchmark_ids = {
            row["benchmark_case_id"] for row in normalized
        }
        expected_benchmark_ids = set(expected_benchmark_case_ids)
        if actual_benchmark_ids != expected_benchmark_ids:
            missing = sorted(expected_benchmark_ids - actual_benchmark_ids)
            unexpected = sorted(actual_benchmark_ids - expected_benchmark_ids)
            raise ControlAuthoringError(
                "match manifest benchmark cases differ from the scientific corpus; "
                f"missing={missing}, unexpected={unexpected}"
            )
    return {
        "matches": len(normalized),
        "authors": len(authors),
        "match_ids": sorted(row["match_id"] for row in normalized),
        "benchmark_case_ids": sorted(
            row["benchmark_case_id"] for row in normalized
        ),
        "control_case_ids": sorted(row["control_case_id"] for row in normalized),
    }


def compile_enriched_submission(
    submission: Mapping[str, Any],
    enrichment: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any] | None = None,
    allow_tiny_control_fixture: bool = False,
) -> AuthorizationCase:
    selected_protocol = (
        _validate_authoring_protocol(protocol, expected_briefs=None)
        if protocol is not None
        else load_authoring_protocol()
    )
    validation = validate_submission(submission, protocol=selected_protocol)
    _require_keys(
        enrichment,
        required={
            "schema_version",
            "brief_id",
            "visible_history_sha256",
            "case_id",
            "source_id_namespace",
            "benchmark",
            "review_attestations",
            "events",
            "probe_pairs",
            "tags",
        },
        label="control enrichment",
    )
    if enrichment["schema_version"] != "1":
        raise ControlAuthoringError("control enrichment schema_version must be '1'")
    if enrichment["brief_id"] != validation["brief_id"]:
        raise ControlAuthoringError("control enrichment brief_id does not match submission")
    if enrichment["visible_history_sha256"] != validation["visible_history_sha256"]:
        raise ControlAuthoringError(
            "control enrichment does not match the immutable visible-history hash"
        )
    review_attestations = enrichment["review_attestations"]
    if not isinstance(review_attestations, Mapping):
        raise ControlAuthoringError(
            "control enrichment review_attestations must be an object"
        )
    _require_keys(
        review_attestations,
        required=_REQUIRED_REVIEW_ATTESTATIONS,
        label="control enrichment review_attestations",
    )
    rejected = sorted(
        key
        for key, value in review_attestations.items()
        if value is not True
    )
    if rejected:
        raise ControlAuthoringError(
            "control enrichment has unaccepted review attestations: "
            + ", ".join(rejected)
        )
    brief = _briefs_by_id(selected_protocol)[validation["brief_id"]]
    benchmark = enrichment["benchmark"]
    if not isinstance(benchmark, Mapping):
        raise ControlAuthoringError("control enrichment benchmark must be an object")
    if benchmark.get("lifecycle") != brief.get("lifecycle"):
        raise ControlAuthoringError(
            "control enrichment lifecycle does not match its structural brief"
        )
    if benchmark.get("history_length_band") != brief.get("history_length_band"):
        raise ControlAuthoringError(
            "control enrichment history_length_band does not match its "
            "structural brief"
        )
    visible = submission["case"]
    source = {
        "schema_version": "deployment_like_v1",
        "case_id": enrichment["case_id"],
        "source_id_namespace": enrichment["source_id_namespace"],
        "benchmark": benchmark,
        "policy": visible["policy"],
        "authorized_issuers": visible["authorized_issuers"],
        "blocks": visible["blocks"],
        "events": enrichment["events"],
        "probe_pairs": enrichment["probe_pairs"],
        "tags": list(
            dict.fromkeys(
                [*enrichment["tags"], "deployment_like_control"]
            )
        ),
    }
    try:
        compiled = compile_case(
            source,
            allow_single_probe_pair=True,
            allow_tiny_control_fixture=allow_tiny_control_fixture,
        )
    except ValueError as exc:
        raise ControlAuthoringError(f"enriched control is invalid: {exc}") from exc
    event_types = [event.event_type for event in compiled.events]
    lifecycle = str(brief["lifecycle"])
    if lifecycle == "issue_only" and event_types != ["issue"]:
        raise ControlAuthoringError(
            "issue_only controls must contain exactly one canonical issue event"
        )
    if lifecycle == "issue_patch" and event_types != ["issue", "patch"]:
        raise ControlAuthoringError(
            "issue_patch controls must contain exactly one issue followed by one patch"
        )
    if (
        lifecycle == "issue_revoke_replace"
        and event_types != ["issue", "revoke", "replace"]
    ):
        raise ControlAuthoringError(
            "issue_revoke_replace controls must contain exactly one issue, "
            "one revocation, and one replacement in that order"
        )
    if len(compiled.probe_pairs) != 1:
        raise ControlAuthoringError(
            "each deployment-like control must define exactly one matched probe pair"
        )
    pair_dimension = compiled.probe_pairs[0].dimension
    if tuple(compiled.benchmark.target_dimensions) != (pair_dimension,):
        raise ControlAuthoringError(
            "control benchmark target_dimensions must contain only its matched "
            "probe dimension"
        )
    turns = {
        turn.turn_id: turn
        for block in compiled.blocks
        for turn in block.turns
    }
    for event in compiled.events:
        if event.issuer not in compiled.authorized_issuers:
            raise ControlAuthoringError(
                f"event {event.event_id!r} was not issued by an authorized principal"
            )
        if any(turns[source_id].actor_id != event.issuer for source_id in event.source_turn_ids):
            raise ControlAuthoringError(
                f"event {event.event_id!r} cites a source spoken by another principal"
            )
    return compiled


def _validated_control_package(
    submissions: Sequence[Mapping[str, Any]],
    enrichments: Sequence[Mapping[str, Any]],
    match_manifest: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any],
    core_protocol: bool,
    allow_tiny_control_fixture: bool,
) -> tuple[dict[str, Any], tuple[AuthorizationCase, ...]]:
    protocol = _validate_authoring_protocol(
        protocol,
        expected_briefs=12 if core_protocol else None,
    )
    if len(submissions) != len(enrichments):
        raise ControlAuthoringError(
            "control package requires one enrichment for every submission"
        )
    collection = validate_collection(
        submissions,
        protocol=protocol,
        core_protocol=core_protocol,
    )
    submission_rows = [
        validate_submission(
            submission,
            protocol=protocol,
            label=f"submission[{index}]",
        )
        for index, submission in enumerate(submissions)
    ]
    cases = tuple(
        compile_enriched_submission(
            submission,
            enrichment,
            protocol=protocol,
            allow_tiny_control_fixture=allow_tiny_control_fixture,
        )
        for submission, enrichment in zip(
            submissions,
            enrichments,
            strict=True,
        )
    )
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ControlAuthoringError(
            "control enrichments contain duplicate case IDs"
        )
    source_ids = [
        turn.turn_id
        for case in cases
        for block in case.blocks
        for turn in block.turns
    ]
    if len(source_ids) != len(set(source_ids)):
        raise ControlAuthoringError(
            "control enrichments contain colliding source ID namespaces"
        )
    case_hashes = [case.authoring_hash for case in cases]
    if len(case_hashes) != len(set(case_hashes)):
        raise ControlAuthoringError(
            "control enrichments compile to duplicate cases"
        )

    expected_controls = {
        case.case_id: submission_row["author_id"]
        for case, submission_row in zip(cases, submission_rows, strict=True)
    }
    benchmark_cases = (
        tuple(load_cases("benchmark_v1"))
        if core_protocol
        else ()
    )
    matches = validate_match_manifest(
        match_manifest,
        core_protocol=core_protocol,
        expected_count=len(cases),
        expected_controls=expected_controls,
        expected_benchmark_case_ids=(
            {case.case_id for case in benchmark_cases}
            if core_protocol
            else None
        ),
    )
    normalized_matches = sorted(
        _normalize_match_manifest(
            match_manifest,
            core_protocol=core_protocol,
            expected_count=len(cases),
        ),
        key=lambda row: row["match_id"],
    )
    controls_by_id = {case.case_id: case for case in cases}
    benchmarks_by_id = {case.case_id: case for case in benchmark_cases}
    for index, row in enumerate(normalized_matches):
        control = controls_by_id[row["control_case_id"]]
        expected_dimension = _DIMENSIONS[index % len(_DIMENSIONS)]
        actual_dimension = control.probe_pairs[0].dimension
        if actual_dimension != expected_dimension:
            raise ControlAuthoringError(
                f"{row['match_id']}: control probe dimension is "
                f"{actual_dimension!r}; protocol v1 requires "
                f"{expected_dimension!r}"
            )
        if core_protocol:
            benchmark = benchmarks_by_id[row["benchmark_case_id"]]
            structural_fields = {
                "lifecycle": (
                    benchmark.benchmark.lifecycle,
                    control.benchmark.lifecycle,
                ),
                "history_length_band": (
                    benchmark.benchmark.history_length_band,
                    control.benchmark.history_length_band,
                ),
                "block_count": (len(benchmark.blocks), len(control.blocks)),
            }
            mismatches = {
                field: values
                for field, values in structural_fields.items()
                if values[0] != values[1]
            }
            if mismatches:
                raise ControlAuthoringError(
                    f"{row['match_id']}: benchmark/control structure differs: "
                    f"{mismatches}"
                )

    return (
        {
            "protocol_version": CONTROL_PROTOCOL_VERSION,
            "corpus_version": CONTROL_CORPUS_VERSION,
            "core_ready": core_protocol,
            "collection": collection,
            "matches": matches,
            "cases": len(cases),
            "case_ids": sorted(case_ids),
            "case_authoring_hashes": {
                case.case_id: case.authoring_hash
                for case in sorted(cases, key=lambda item: item.case_id)
            },
        },
        cases,
    )


def validate_control_package(
    submissions: Sequence[Mapping[str, Any]],
    enrichments: Sequence[Mapping[str, Any]],
    match_manifest: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any] | None = None,
    core_protocol: bool = True,
    allow_tiny_control_fixture: bool = False,
) -> dict[str, Any]:
    selected_protocol = protocol or load_authoring_protocol(
        expected_briefs=12 if core_protocol else None
    )
    summary, _ = _validated_control_package(
        submissions,
        enrichments,
        match_manifest,
        protocol=selected_protocol,
        core_protocol=core_protocol,
        allow_tiny_control_fixture=allow_tiny_control_fixture,
    )
    return summary


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_compiled_control_package(
    submissions: Sequence[Mapping[str, Any]],
    enrichments: Sequence[Mapping[str, Any]],
    match_manifest: Mapping[str, Any],
    *,
    protocol: Mapping[str, Any] | None = None,
    output_path: Path = COMPILED_PACKAGE_PATH,
) -> dict[str, Any]:
    selected_protocol = protocol or load_authoring_protocol()
    summary, cases = _validated_control_package(
        submissions,
        enrichments,
        match_manifest,
        protocol=selected_protocol,
        core_protocol=True,
        allow_tiny_control_fixture=False,
    )
    ordered = sorted(
        zip(submissions, enrichments, cases, strict=True),
        key=lambda item: item[2].case_id,
    )
    canonical_matches = {
        "schema_version": match_manifest["schema_version"],
        "matches": sorted(
            match_manifest["matches"],
            key=lambda row: row["match_id"],
        ),
    }
    payloads = {
        _PACKAGE_FILES["protocol"]: (
            _canonical_json(selected_protocol) + "\n"
        ).encode("utf-8"),
        _PACKAGE_FILES["submissions"]: _canonical_jsonl(
            [dict(submission) for submission, _, _ in ordered]
        ).encode("utf-8"),
        _PACKAGE_FILES["enrichments"]: _canonical_jsonl(
            [dict(enrichment) for _, enrichment, _ in ordered]
        ).encode("utf-8"),
        _PACKAGE_FILES["matches"]: (
            _canonical_json(canonical_matches) + "\n"
        ).encode("utf-8"),
        _PACKAGE_FILES["cases"]: _canonical_jsonl(
            [case.to_dict() for _, _, case in ordered]
        ).encode("utf-8"),
    }
    files = {
        filename: _sha256_bytes(payload)
        for filename, payload in sorted(payloads.items())
    }
    manifest_without_hash = {
        "schema_version": 1,
        "protocol_version": CONTROL_PROTOCOL_VERSION,
        "corpus_version": CONTROL_CORPUS_VERSION,
        "core_ready": True,
        "summary": summary,
        "files": files,
    }
    manifest = {
        **manifest_without_hash,
        "package_sha256": _canonical_hash(manifest_without_hash),
    }
    output = output_path.resolve()
    if output.exists():
        raise ControlAuthoringError(
            f"refusing to replace existing control package: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}-",
            dir=output.parent,
        )
    )
    try:
        for filename, payload in payloads.items():
            (temporary / filename).write_bytes(payload)
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {
        **manifest,
        "path": str(output),
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ControlAuthoringError(
                        f"{path}:{line_number} must contain one JSON object"
                    )
                rows.append(value)
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlAuthoringError(f"cannot load JSONL {path}: {exc}") from exc
    return rows


def load_compiled_control_package(
    path: Path = COMPILED_PACKAGE_PATH,
) -> tuple[tuple[AuthorizationCase, ...], dict[str, Any]]:
    package_path = path.resolve()
    manifest_path = package_path / "manifest.json"
    if not manifest_path.is_file():
        raise ControlAuthoringError(
            "blocked_external_controls_missing: build the validated "
            f"{CONTROL_CORPUS_VERSION} package at {package_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ControlAuthoringError(
            f"cannot load control package manifest {manifest_path}: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise ControlAuthoringError("control package manifest must be an object")
    _require_keys(
        manifest,
        required={
            "schema_version",
            "protocol_version",
            "corpus_version",
            "core_ready",
            "summary",
            "files",
            "package_sha256",
        },
        label="control package manifest",
    )
    if (
        manifest["schema_version"] != 1
        or manifest["protocol_version"] != CONTROL_PROTOCOL_VERSION
        or manifest["corpus_version"] != CONTROL_CORPUS_VERSION
        or manifest["core_ready"] is not True
    ):
        raise ControlAuthoringError(
            "control package manifest is not core-ready deployment_like_v1"
        )
    package_hash = manifest["package_sha256"]
    if (
        not isinstance(package_hash, str)
        or not _SHA256_PATTERN.fullmatch(package_hash)
    ):
        raise ControlAuthoringError(
            "control package manifest has an invalid package hash"
        )
    without_hash = {
        key: value
        for key, value in manifest.items()
        if key != "package_sha256"
    }
    if _canonical_hash(without_hash) != package_hash:
        raise ControlAuthoringError("control package manifest hash differs")
    files = manifest["files"]
    expected_files = set(_PACKAGE_FILES.values())
    if not isinstance(files, Mapping) or set(files) != expected_files:
        raise ControlAuthoringError(
            "control package manifest has missing or unexpected files"
        )
    for filename, expected_hash in files.items():
        file_path = package_path / filename
        if (
            not isinstance(expected_hash, str)
            or not _SHA256_PATTERN.fullmatch(expected_hash)
            or not file_path.is_file()
            or _sha256_bytes(file_path.read_bytes()) != expected_hash
        ):
            raise ControlAuthoringError(
                f"control package source hash differs for {filename}"
            )

    protocol = load_authoring_protocol(
        package_path / _PACKAGE_FILES["protocol"],
        expected_briefs=12,
    )
    submissions = _load_jsonl(package_path / _PACKAGE_FILES["submissions"])
    enrichments = _load_jsonl(package_path / _PACKAGE_FILES["enrichments"])
    match_manifest = _load_yaml(package_path / _PACKAGE_FILES["matches"])
    summary, recompiled = _validated_control_package(
        submissions,
        enrichments,
        match_manifest,
        protocol=protocol,
        core_protocol=True,
        allow_tiny_control_fixture=False,
    )
    if summary != manifest["summary"]:
        raise ControlAuthoringError(
            "control package manifest summary differs from revalidation"
        )
    stored_cases = load_cases(
        CONTROL_CORPUS_VERSION,
        data_path=package_path / _PACKAGE_FILES["cases"],
        allow_single_probe_pair=True,
    )
    if tuple(case.to_dict() for case in stored_cases) != tuple(
        case.to_dict() for case in recompiled
    ):
        raise ControlAuthoringError(
            "control package cases differ from their source enrichments"
        )
    return tuple(stored_cases), manifest


def compiled_control_source_files(
    path: Path = COMPILED_PACKAGE_PATH,
) -> tuple[Path, ...]:
    _, manifest = load_compiled_control_package(path)
    return (
        path.resolve() / "manifest.json",
        *(
            path.resolve() / filename
            for filename in sorted(manifest["files"])
        ),
    )


def load_fixture_control() -> AuthorizationCase:
    protocol = load_authoring_protocol(
        FIXTURE_DIR / "authoring_protocol.yaml",
        expected_briefs=None,
    )
    _, cases = _validated_control_package(
        [_load_yaml(FIXTURE_DIR / "submission.yaml")],
        [_load_yaml(FIXTURE_DIR / "enrichment.yaml")],
        _load_yaml(FIXTURE_DIR / "control_matches.json"),
        protocol=protocol,
        core_protocol=False,
        allow_tiny_control_fixture=True,
    )
    return cases[0]


def _expect_self_check_rejection(
    label: str,
    action: Callable[[], Any],
    *,
    contains: str,
) -> str:
    try:
        action()
    except ControlAuthoringError as exc:
        message = str(exc)
        if contains not in message:
            raise ControlAuthoringError(
                f"control authoring self-check {label!r} failed for an unexpected "
                f"reason: {message}"
            ) from exc
        return message
    raise ControlAuthoringError(
        f"control authoring self-check {label!r} unexpectedly passed"
    )


def _self_check_matches(author_counts: Sequence[int]) -> dict[str, Any]:
    rows = []
    index = 0
    for author_index, count in enumerate(author_counts):
        for _ in range(count):
            rows.append(
                {
                    "match_id": f"self_match_{index:02d}",
                    "benchmark_case_id": f"self_benchmark_{index:02d}",
                    "control_case_id": f"self_control_{index:02d}",
                    "author_id": f"author_self{author_index:02d}",
                }
            )
            index += 1
    return {"schema_version": 1, "matches": rows}


def _self_check_compiled_hash_mutation() -> str:
    with tempfile.TemporaryDirectory(prefix="control-authoring-self-check-") as raw:
        package_path = Path(raw)
        payloads = {
            filename: f'{{"fixture_file":"{filename}"}}\n'.encode()
            for filename in _PACKAGE_FILES.values()
        }
        for filename, payload in payloads.items():
            (package_path / filename).write_bytes(payload)
        files = {
            filename: _sha256_bytes(payload)
            for filename, payload in sorted(payloads.items())
        }
        manifest_without_hash = {
            "schema_version": 1,
            "protocol_version": CONTROL_PROTOCOL_VERSION,
            "corpus_version": CONTROL_CORPUS_VERSION,
            "core_ready": True,
            "summary": {},
            "files": files,
        }
        manifest = {
            **manifest_without_hash,
            "package_sha256": _canonical_hash(manifest_without_hash),
        }
        (package_path / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        mutated_path = package_path / _PACKAGE_FILES["cases"]
        mutated_path.write_bytes(mutated_path.read_bytes() + b'{"mutated":true}\n')
        return _expect_self_check_rejection(
            "compiled_package_hash_mutation",
            lambda: load_compiled_control_package(package_path),
            contains="control package source hash differs",
        )


def validate_control_brief_calibration() -> dict[str, Any]:
    protocol = load_authoring_protocol()
    briefs = protocol["briefs"]
    benchmark_cases = tuple(load_cases("benchmark_v1"))
    if len(briefs) != len(benchmark_cases):
        raise ControlAuthoringError(
            "control brief calibration requires one brief per benchmark_v1 story"
        )
    rows = {}
    for brief, case in zip(briefs, benchmark_cases, strict=True):
        counts = [
            _visible_word_count(turn.content)
            for block in case.blocks
            for turn in block.turns
        ]
        history_words = sum(counts)
        history_range = brief["history_word_range"]
        turn_range = brief["turn_word_range"]
        if not history_range[0] <= history_words <= history_range[1]:
            raise ControlAuthoringError(
                f"{brief['brief_id']} does not contain its paired benchmark history's "
                f"{history_words} visible turn-content words"
            )
        rows[str(brief["brief_id"])] = {
            "paired_benchmark_case_id": case.case_id,
            "benchmark_history_words": history_words,
            "benchmark_minimum_turn_words": min(counts),
            "benchmark_maximum_turn_words": max(counts),
            "history_word_range": list(history_range),
            "turn_word_range": list(turn_range),
        }
    return {
        "status": "passed",
        "briefs": rows,
    }


def validate_control_authoring_self_check() -> dict[str, Any]:
    calibration = validate_control_brief_calibration()
    protocol = load_authoring_protocol(
        FIXTURE_DIR / "authoring_protocol.yaml",
        expected_briefs=None,
    )
    submission = _load_yaml(FIXTURE_DIR / "submission.yaml")
    enrichment = _load_yaml(FIXTURE_DIR / "enrichment.yaml")
    match_manifest = _load_yaml(FIXTURE_DIR / "control_matches.json")
    summary, cases = _validated_control_package(
        [submission],
        [enrichment],
        match_manifest,
        protocol=protocol,
        core_protocol=False,
        allow_tiny_control_fixture=True,
    )
    if len(cases) != 1 or cases[0].case_id != "fixture_control_01":
        raise ControlAuthoringError(
            "control authoring self-check did not ingest the expected fixture"
        )
    submission_stats = validate_submission(
        submission,
        protocol=protocol,
        label="self-check fixture submission",
    )

    duplicate_matches = _self_check_matches([1, 1])
    duplicate_matches["matches"][1]["match_id"] = duplicate_matches["matches"][0][
        "match_id"
    ]
    mutated_submission = deepcopy(submission)
    mutated_submission["case"]["blocks"][0]["turns"][0]["content"] += (
        " Delivery timing is unchanged."
    )
    negative_checks = {
        "too_few_authors": _expect_self_check_rejection(
            "too_few_authors",
            lambda: validate_match_manifest(
                _self_check_matches([4, 4, 4]),
                core_protocol=True,
                expected_count=12,
            ),
            contains="at least four authors",
        ),
        "author_history_limit": _expect_self_check_rejection(
            "author_history_limit",
            lambda: validate_match_manifest(
                _self_check_matches([4, 3, 3, 2]),
                core_protocol=True,
                expected_count=12,
            ),
            contains="more than three controls",
        ),
        "duplicate_match": _expect_self_check_rejection(
            "duplicate_match",
            lambda: validate_match_manifest(
                duplicate_matches,
                core_protocol=False,
                expected_count=2,
            ),
            contains="repeats match_id",
        ),
        "missing_match": _expect_self_check_rejection(
            "missing_match",
            lambda: validate_match_manifest(
                _self_check_matches([1]),
                core_protocol=False,
                expected_count=2,
            ),
            contains="has 1 rows; expected 2",
        ),
        "visible_history_hash_mutation": _expect_self_check_rejection(
            "visible_history_hash_mutation",
            lambda: compile_enriched_submission(
                mutated_submission,
                enrichment,
                protocol=protocol,
                allow_tiny_control_fixture=True,
            ),
            contains="immutable visible-history hash",
        ),
        "compiled_package_hash_mutation": _self_check_compiled_hash_mutation(),
    }
    return {
        "status": "passed",
        "claim_brief_calibration": calibration,
        "fixture": {
            "case_id": cases[0].case_id,
            "blocks": submission_stats["blocks"],
            "turns": submission_stats["turns"],
            "history_words": submission_stats["history_words"],
            "minimum_turn_words": submission_stats["minimum_turn_words"],
            "maximum_turn_words": submission_stats["maximum_turn_words"],
            "visible_history_sha256": submission_stats[
                "visible_history_sha256"
            ],
            "package_summary": summary,
        },
        "negative_checks": {
            name: {"status": "rejected", "reason": reason}
            for name, reason in sorted(negative_checks.items())
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate blinded deployment-like procurement controls."
    )
    parser.add_argument("--submission", action="append", type=Path, default=[])
    parser.add_argument("--enrichment", action="append", type=Path, default=[])
    parser.add_argument("--match-manifest", type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL_PATH)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="run deterministic positive and negative ingestion checks",
    )
    parser.add_argument(
        "--partial",
        action="store_true",
        help="validate work in progress without marking it core-ready",
    )
    parser.add_argument(
        "--output-package",
        type=Path,
        help="write the immutable deployment_like_v1 package after full validation",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.self_check:
        if (
            args.fixture
            or args.partial
            or args.submission
            or args.enrichment
            or args.match_manifest is not None
            or args.output_package is not None
            or args.protocol != PROTOCOL_PATH
        ):
            raise SystemExit("--self-check cannot be combined with other arguments")
        print(
            json.dumps(
                validate_control_authoring_self_check(),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if args.fixture and args.partial:
        raise SystemExit("--fixture and --partial are mutually exclusive")
    if not args.submission:
        raise SystemExit("pass at least one --submission")
    if args.enrichment and len(args.enrichment) != len(args.submission):
        raise SystemExit("pass one --enrichment for every --submission, in matching order")
    if args.output_package is not None and (args.fixture or args.partial):
        raise SystemExit("--output-package is only available for a full core-ready package")
    output: dict[str, Any] = {
        "status": "passed",
        "core_ready": False,
    }
    protocol = load_authoring_protocol(
        args.protocol,
        expected_briefs=None if args.fixture else 12,
    )
    submissions = [_load_yaml(path) for path in args.submission]
    enrichments = [_load_yaml(path) for path in args.enrichment]
    match_manifest = (
        _load_yaml(args.match_manifest)
        if args.match_manifest is not None
        else None
    )
    complete = (
        len(enrichments) == len(submissions)
        and match_manifest is not None
    )
    if not args.partial and not complete:
        raise SystemExit(
            "core-ready and fixture validation require every --enrichment and "
            "--match-manifest; use --partial for work-in-progress validation"
        )
    if complete:
        assert match_manifest is not None
        package_summary, _ = _validated_control_package(
            submissions,
            enrichments,
            match_manifest,
            protocol=protocol,
            core_protocol=not args.fixture,
            allow_tiny_control_fixture=args.fixture,
        )
        output["package"] = package_summary
        output["core_ready"] = not args.fixture
    else:
        output["collection"] = validate_collection(
            submissions,
            protocol=protocol,
            core_protocol=False,
        )
        if enrichments:
            compiled = tuple(
                compile_enriched_submission(
                    submission,
                    enrichment,
                    protocol=protocol,
                    allow_tiny_control_fixture=args.fixture,
                )
                for submission, enrichment in zip(
                    submissions,
                    enrichments,
                    strict=True,
                )
            )
            output["enriched_controls"] = {
                "cases": len(compiled),
                "case_ids": sorted(case.case_id for case in compiled),
                "authoring_hashes": sorted(case.authoring_hash for case in compiled),
            }
        if match_manifest is not None:
            output["matches"] = validate_match_manifest(
                match_manifest,
                core_protocol=False,
            )
    if args.output_package is not None:
        assert match_manifest is not None
        output["compiled_package"] = build_compiled_control_package(
            submissions,
            enrichments,
            match_manifest,
            protocol=protocol,
            output_path=args.output_package,
        )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
