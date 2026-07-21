from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Collection, Mapping
from datetime import datetime
from functools import lru_cache
from typing import Any

from .schemas import (
    AuthorizationMemoryStatus,
    MemoryArchitecture,
    MemoryArtifact,
    MemoryOrigin,
    MemoryPayload,
    MemoryUpdateStatus,
    TYPED_MEMORY_PAYLOAD_SCHEMA_ID,
    TYPED_MEMORY_SCHEMA_VERSION,
    TypedAuthorizationState,
    TypedCurrentState,
)


CANONICAL_ACTION = "submit_order"
CANONICAL_EFFECT = "permit_exception"
MAX_TYPED_AUTHORIZATIONS = 32
MAX_CATEGORIES_PER_AUTHORIZATION = 32
MAX_SOURCE_IDS_PER_AUTHORIZATION = 32
_FALLBACK_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_RECORD_KEYS = frozenset(
    {
        "authorization_id",
        "issuer",
        "grantee",
        "effect",
        "action",
        "status",
        "valid_from",
        "valid_until",
        "scope",
        "supersedes",
        "source_turn_ids",
    }
)
_SCOPE_KEYS = frozenset(
    {"vendor", "allowed_categories", "max_amount", "currency"}
)

TokenCounter = Callable[[str], int]


class MemoryValidationError(ValueError):
    def __init__(self, status: MemoryUpdateStatus, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def serialize_payload(payload: MemoryPayload) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, TypedCurrentState):
        return canonical_json(payload.to_dict())
    raise TypeError(f"unsupported memory payload: {type(payload).__name__}")


def hash_payload(payload: MemoryPayload) -> str:
    serialized = (
        canonical_json(payload.to_source_dict())
        if isinstance(payload, TypedCurrentState)
        else serialize_payload(payload)
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def _reference_encoder() -> Any | None:
    try:
        import tiktoken
    except ImportError:
        return None
    return tiktoken.get_encoding("cl100k_base")


def reference_tokenizer_name(counter: TokenCounter | None = None) -> str:
    if counter is not None:
        return "injected"
    return "cl100k_base" if _reference_encoder() is not None else "regex_fallback_v1"


def count_reference_tokens(text: str, counter: TokenCounter | None = None) -> int:
    count = counter(text) if counter is not None else _default_reference_token_count(text)
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("token counter must return a non-negative integer")
    return count


def _default_reference_token_count(text: str) -> int:
    encoder = _reference_encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return len(_FALLBACK_TOKEN_PATTERN.findall(text))


def validate_capacity(
    payload: MemoryPayload,
    capacity_tokens: int | None,
    *,
    token_counter: TokenCounter | None = None,
) -> int:
    if capacity_tokens is not None and (
        not isinstance(capacity_tokens, int)
        or isinstance(capacity_tokens, bool)
        or capacity_tokens < 0
    ):
        raise ValueError("capacity_tokens must be a non-negative integer or None")
    token_count = count_reference_tokens(serialize_payload(payload), token_counter)
    if capacity_tokens is not None and token_count > capacity_tokens:
        raise MemoryValidationError(
            MemoryUpdateStatus.CAPACITY_OVERFLOW,
            f"candidate uses {token_count} reference tokens; capacity is {capacity_tokens}",
        )
    return token_count


def typed_payload_from_dict(
    value: Mapping[str, Any],
    *,
    seen_source_ids: Collection[str] | None,
) -> TypedCurrentState:
    _require_exact_keys(value, {"schema_version", "authorizations"}, "typed payload")
    if value["schema_version"] != TYPED_MEMORY_SCHEMA_VERSION:
        raise _invalid(f"schema_version must be '{TYPED_MEMORY_SCHEMA_VERSION}'")
    records = value["authorizations"]
    if not isinstance(records, list):
        raise _invalid("authorizations must be an array")
    if len(records) > MAX_TYPED_AUTHORIZATIONS:
        raise _invalid(f"authorizations may contain at most {MAX_TYPED_AUTHORIZATIONS} records")

    seen = None if seen_source_ids is None else set(seen_source_ids)
    parsed = tuple(_typed_record_from_dict(record, seen) for record in records)
    authorization_ids = [record.authorization_id for record in parsed]
    if len(authorization_ids) != len(set(authorization_ids)):
        raise _invalid("authorization_id values must be unique")
    return TypedCurrentState(
        authorizations=parsed,
        schema_version=TYPED_MEMORY_SCHEMA_VERSION,
    )


def validate_typed_payload(
    payload: TypedCurrentState,
    *,
    seen_source_ids: Collection[str] | None,
) -> TypedCurrentState:
    if not isinstance(payload, TypedCurrentState):
        raise _invalid("typed memory must be a TypedCurrentState")
    return typed_payload_from_dict(payload.to_dict(), seen_source_ids=seen_source_ids)


def _typed_record_from_dict(
    value: Any, seen_source_ids: set[str] | None
) -> TypedAuthorizationState:
    if not isinstance(value, Mapping):
        raise _invalid("each authorization must be an object")
    _require_exact_keys(value, _RECORD_KEYS, "authorization")
    scope = value["scope"]
    if not isinstance(scope, Mapping):
        raise _invalid("authorization scope must be an object")
    _require_exact_keys(scope, _SCOPE_KEYS, "authorization scope")

    authorization_id = _required_string(value["authorization_id"], "authorization_id", 128)
    issuer = _nullable_string(value["issuer"], "issuer")
    grantee = _nullable_string(value["grantee"], "grantee")
    effect = _nullable_enum(value["effect"], "effect", (CANONICAL_EFFECT,))
    action = _nullable_enum(value["action"], "action", (CANONICAL_ACTION,))
    vendor = _nullable_string(scope["vendor"], "scope.vendor")
    categories = _nullable_string_array(
        scope["allowed_categories"],
        "scope.allowed_categories",
        MAX_CATEGORIES_PER_AUTHORIZATION,
    )
    max_amount = scope["max_amount"]
    if max_amount is not None and (
        not isinstance(max_amount, int) or isinstance(max_amount, bool) or max_amount < 0
    ):
        raise _invalid("max_amount must be a non-negative integer or null")
    currency = _nullable_string(scope["currency"], "scope.currency", max_length=3)
    if currency is not None and not re.fullmatch(r"[A-Z]{3}", currency):
        raise _invalid("currency must be a three-letter uppercase code or null")
    valid_from = _nullable_timestamp(value["valid_from"], "valid_from")
    valid_until = _nullable_timestamp(value["valid_until"], "valid_until")
    try:
        status = AuthorizationMemoryStatus(value["status"])
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(status.value for status in AuthorizationMemoryStatus)
        raise _invalid(f"status must be one of: {allowed}") from exc
    supersedes = _nullable_string(value["supersedes"], "supersedes", max_length=128)
    source_turn_ids = _string_array(
        value["source_turn_ids"],
        "source_turn_ids",
        MAX_SOURCE_IDS_PER_AUTHORIZATION,
        require_nonempty=True,
        item_max_length=128,
    )
    if seen_source_ids is not None:
        unknown = sorted(set(source_turn_ids) - seen_source_ids)
        if unknown:
            raise MemoryValidationError(
                MemoryUpdateStatus.UNKNOWN_SOURCE_ID,
                f"source_turn_ids were not visible to the writer: {', '.join(unknown)}",
            )

    return TypedAuthorizationState(
        authorization_id=authorization_id,
        issuer=issuer,
        grantee=grantee,
        effect=effect,
        action=action,
        vendor=vendor,
        allowed_categories=categories,
        max_amount=max_amount,
        currency=currency,
        valid_from=valid_from,
        valid_until=valid_until,
        status=status,
        supersedes=supersedes,
        source_turn_ids=source_turn_ids,
    )


def _require_exact_keys(value: Mapping[str, Any], expected: Collection[str], name: str) -> None:
    keys = set(value)
    missing = sorted(set(expected) - keys)
    extra = sorted(keys - set(expected))
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing: {', '.join(missing)}")
        if extra:
            parts.append(f"unexpected: {', '.join(extra)}")
        raise _invalid(f"{name} has invalid fields ({'; '.join(parts)})")


def _invalid(detail: str) -> MemoryValidationError:
    return MemoryValidationError(MemoryUpdateStatus.INVALID_PAYLOAD, detail)


def _required_string(value: Any, field: str, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise _invalid(f"{field} must be a non-empty string of at most {max_length} characters")
    return value


def _nullable_string(value: Any, field: str, max_length: int = 256) -> str | None:
    if value is None:
        return None
    return _required_string(value, field, max_length)


def _nullable_enum(
    value: Any,
    field: str,
    allowed: Collection[str],
) -> str | None:
    if value is None:
        return None
    parsed = _required_string(value, field)
    if parsed not in allowed:
        choices = ", ".join(sorted(allowed))
        raise _invalid(f"{field} must be one of: {choices}; or null")
    return parsed


def _string_array(
    value: Any,
    field: str,
    max_items: int,
    *,
    require_nonempty: bool,
    item_max_length: int = 256,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _invalid(f"{field} must be an array")
    if require_nonempty and not value:
        raise _invalid(f"{field} must contain at least one item")
    if len(value) > max_items:
        raise _invalid(f"{field} may contain at most {max_items} items")
    parsed = tuple(_required_string(item, field, item_max_length) for item in value)
    if len(parsed) != len(set(parsed)):
        raise _invalid(f"{field} must not contain duplicates")
    return parsed


def _nullable_string_array(
    value: Any, field: str, max_items: int
) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _string_array(value, field, max_items, require_nonempty=True)


def _nullable_timestamp(value: Any, field: str) -> str | None:
    if value is None:
        return None
    timestamp = _required_string(value, field, 64)
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _invalid(f"{field} must be an RFC 3339 timestamp or null") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _invalid(f"{field} must include a timezone offset")
    return timestamp


def create_memory_artifact(
    *,
    chain_id: str,
    case_id: str,
    condition_id: str,
    block_index: int,
    writer_model: str | None,
    architecture: MemoryArchitecture,
    origin: MemoryOrigin,
    payload: MemoryPayload,
    previous_artifact: MemoryArtifact | None = None,
    seen_source_ids: Collection[str] | None = None,
    capacity_tokens: int | None = None,
    token_counter: TokenCounter | None = None,
) -> MemoryArtifact:
    _validate_artifact_metadata(chain_id, case_id, condition_id, block_index)
    _validate_parent(previous_artifact, chain_id, case_id, condition_id, architecture, block_index)
    normalized = _validate_payload(payload, architecture, seen_source_ids)
    reference_tokens = validate_capacity(
        normalized, capacity_tokens, token_counter=token_counter
    )
    content_hash = hash_payload(normalized)
    parent_id = previous_artifact.memory_id if previous_artifact else None
    identity = canonical_json(
        {
            "parent_memory_id": parent_id,
            "chain_id": chain_id,
            "case_id": case_id,
            "condition_id": condition_id,
            "block_index": block_index,
            "writer_model": writer_model,
            "architecture": architecture.value,
            "origin": origin.value,
            "content_hash": content_hash,
        }
    )
    memory_id = "mem_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return MemoryArtifact(
        memory_id=memory_id,
        parent_memory_id=parent_id,
        chain_id=chain_id,
        case_id=case_id,
        condition_id=condition_id,
        block_index=block_index,
        writer_model=writer_model,
        architecture=architecture,
        origin=origin,
        payload=normalized,
        reference_tokens=reference_tokens,
        reference_tokenizer=reference_tokenizer_name(token_counter),
        content_hash=content_hash,
        payload_schema_id=(
            TYPED_MEMORY_PAYLOAD_SCHEMA_ID
            if architecture is MemoryArchitecture.TYPED
            else None
        ),
        payload_schema_version=(
            TYPED_MEMORY_SCHEMA_VERSION
            if architecture is MemoryArchitecture.TYPED
            else None
        ),
    )


def _validate_payload(
    payload: MemoryPayload,
    architecture: MemoryArchitecture,
    seen_source_ids: Collection[str] | None,
) -> MemoryPayload:
    if architecture is MemoryArchitecture.FREE_TEXT:
        if not isinstance(payload, str):
            raise _invalid("free-text memory must be a string")
        return payload
    if architecture is MemoryArchitecture.TYPED:
        return validate_typed_payload(payload, seen_source_ids=seen_source_ids)
    raise ValueError(f"unsupported memory architecture: {architecture}")


def _validate_artifact_metadata(
    chain_id: str, case_id: str, condition_id: str, block_index: int
) -> None:
    for name, value in (
        ("chain_id", chain_id),
        ("case_id", case_id),
        ("condition_id", condition_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
    if not isinstance(block_index, int) or isinstance(block_index, bool) or block_index < 0:
        raise ValueError("block_index must be a non-negative integer")


def _validate_parent(
    previous: MemoryArtifact | None,
    chain_id: str,
    case_id: str,
    condition_id: str,
    architecture: MemoryArchitecture,
    block_index: int,
) -> None:
    if previous is None:
        return
    expected = (chain_id, case_id, condition_id, architecture)
    actual = (previous.chain_id, previous.case_id, previous.condition_id, previous.architecture)
    if actual != expected:
        raise ValueError("previous artifact belongs to a different memory chain")
    if previous.block_index >= block_index:
        raise ValueError("previous artifact must precede the current block")
