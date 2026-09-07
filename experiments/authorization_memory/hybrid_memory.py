"""Hybrid memory: the domain's typed profile plus one free-text ``notes`` field.

What is typed is fixed before any run: every field the oracle checks stays in the typed
records, and ``notes`` holds anything else (pending changes, informal requests, context).
The hybrid runs through the same LangMem writer as typed memory, against a copy of the domain
whose memory adapter and typed-writer instruction describe the extra field. The executor uses
the base domain and reads the whole memory. Formation is scored on the records, as for typed.

The hybrid profile model is derived from the domain's own typed profile model, so schema
version, record fields, and validators are the domain's; only ``notes`` is added.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields, replace
from typing import Any

from pydantic import BaseModel, create_model

from domains.base import AuthorizationDecision, AuthorizationMemoryDomain, FidelityReport, MemoryArchitecture


NOTES_INSTRUCTION = (
    " The profile also has one top-level free-text field named notes. Put anything relevant "
    "that does not fit the record fields in notes, such as pending changes, informal requests, "
    "or context; never record a permission only in notes. Keep notes to at most three short "
    "sentences so the profile stays within its token budget. Update notes with a single replace "
    "patch at /notes."
)


def _split(payload: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    records = {key: value for key, value in payload.items() if key != "notes"}
    notes = payload.get("notes", "")
    if not isinstance(notes, str):
        raise ValueError("notes must be a string")
    return records, notes


class HybridMemoryAdapter:
    def __init__(self, base: Any) -> None:
        self.base = base
        self.payload_schema_id = f"{base.payload_schema_id}+notes"
        self.typed_profile_model = create_model(
            f"Hybrid{base.typed_profile_model.__name__}", __base__=base.typed_profile_model, notes=(str, ...)
        )

    def typed_schema(self) -> Mapping[str, Any]:
        return self.typed_profile_model.model_json_schema()

    def parse_typed(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("typed memory must be an object")
        records, notes = _split(payload)
        return {**dict(self.base.parse_typed(records)), "notes": notes}

    def serialize_typed(self, state: Any) -> Mapping[str, Any]:
        raw = state.model_dump(mode="python") if isinstance(state, BaseModel) else state
        records, notes = _split(raw)
        return {**dict(self.base.serialize_typed(records)), "notes": notes}

    def empty_typed(self) -> Mapping[str, Any]:
        return {**dict(self.base.empty_typed()), "notes": ""}

    def to_typed_profile(self, state: Any) -> BaseModel:
        return self.typed_profile_model.model_validate(dict(self.serialize_typed(state)), strict=True)

    def from_typed_profile(self, profile: BaseModel) -> Mapping[str, Any]:
        return self.parse_typed(profile.model_dump(mode="python"))

    def records(self, state: Any) -> Mapping[str, Any]:
        """The typed part, in the base domain's state representation."""

        raw = state.model_dump(mode="python") if isinstance(state, BaseModel) else state
        return self.base.parse_typed(_split(raw)[0])

    def referenced_source_ids(self, state: Any) -> frozenset[str]:
        return self.base.referenced_source_ids(self.records(state))

    def referenced_source_ids_in_free_text(self, payload: str) -> frozenset[str]:
        return self.base.referenced_source_ids_in_free_text(payload)

    def faithful_typed(self, case: Any, through_block_index: int | None = None) -> Mapping[str, Any]:
        return {**dict(self.base.faithful_typed(case, through_block_index=through_block_index)), "notes": ""}

    def faithful_free_text(self, case: Any, through_block_index: int | None = None) -> str:
        return self.base.faithful_free_text(case, through_block_index=through_block_index)

    def authorizes(self, case: Any, remembered_state: Any, request: Any, through_block_index: int | None = None) -> AuthorizationDecision:
        return self.base.authorizes(case, self.records(remembered_state), request, through_block_index)

    def writer_instructions(self, architecture: MemoryArchitecture | str) -> str:
        return self.base.writer_instructions(architecture)


class HybridFidelityAdapter:
    def __init__(self, memory: HybridMemoryAdapter, base_fidelity: Any) -> None:
        self.memory = memory
        self.base_fidelity = base_fidelity

    def compare(self, case: Any, remembered: Any, through_block_index: int | None = None, prior_snapshots: Sequence[Any] = ()) -> FidelityReport:
        return self.base_fidelity.compare(case, self.memory.records(remembered), through_block_index, prior_snapshots)


def hybrid_domain(domain: AuthorizationMemoryDomain) -> AuthorizationMemoryDomain:
    memory = HybridMemoryAdapter(domain.memory)
    policies = {
        policy_id: replace(
            policy,
            writer_architecture_instructions={
                **policy.writer_architecture_instructions,
                "typed": policy.writer_architecture_instructions.get("typed", "") + NOTES_INSTRUCTION,
            },
        )
        for policy_id, policy in domain.prompt_policies.items()
    }
    values = {f.name: getattr(domain, f.name) for f in fields(AuthorizationMemoryDomain)}
    values.update(memory=memory, fidelity=HybridFidelityAdapter(memory, domain.fidelity), prompt_policies=policies)
    return AuthorizationMemoryDomain(**values)
