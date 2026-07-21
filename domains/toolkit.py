"""Reusable components for standard authorization-memory domains."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .base import (
    ActionDecision,
    ActionScore,
    AuthorizationDecision,
    AuthorizationEnvelope,
    BenchmarkProbe,
    CapacityPolicy,
    FidelityReport,
    FieldFidelityRow,
    MemoryArchitecture,
    PresentationProfile,
)


CaseT = TypeVar("CaseT")
BlockT = TypeVar("BlockT")
RequestT = TypeVar("RequestT")
ScopeT = TypeVar("ScopeT", bound=BaseModel)
RecordT = TypeVar("RecordT", bound=BaseModel)
_NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class AuthorizationProfileBase(BaseModel, Generic[ScopeT]):
    """Shared typed-memory envelope fields with a domain-owned scope model."""

    model_config = ConfigDict(extra="forbid", strict=True)

    authorization_id: _NonEmptyString
    issuer: str | None
    grantee: str | None
    effect: str | None
    action: str | None
    status: str
    valid_from: str | None
    valid_until: str | None
    scope: ScopeT
    supersedes: str | None
    source_turn_ids: Annotated[list[_NonEmptyString], Field(min_length=1)]

    @field_validator("source_turn_ids")
    @classmethod
    def source_turn_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("source_turn_ids must not contain duplicates")
        return value


class AuthorizationMemoryProfileBase(BaseModel, Generic[RecordT]):
    """Shared v3 typed-memory container."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str
    authorizations: list[RecordT]

    @field_validator("authorizations")
    @classmethod
    def authorization_ids_must_be_unique(
        cls,
        value: list[RecordT],
    ) -> list[RecordT]:
        identifiers = [getattr(record, "authorization_id", None) for record in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("authorization_id values must be unique")
        return value


def _default_case_id(case: Any) -> str:
    return str(case.case_id)


def _default_blocks(case: Any) -> Sequence[Any]:
    return tuple(case.blocks)


def _default_metadata(case: Any) -> Mapping[str, Any]:
    return {}


def _default_checkpoints(case: Any) -> Sequence[Any]:
    return ()


def _default_provenance(version: str) -> Mapping[str, Any]:
    return {}


@dataclass(frozen=True)
class StandardCorpusSpec(Generic[CaseT, BlockT]):
    versions: tuple[str, ...]
    default_version: str
    capacity_policy: CapacityPolicy
    load_cases: Callable[[str], Sequence[CaseT]]
    validate_case: Callable[[CaseT], None]
    probes: Callable[[CaseT], Sequence[BenchmarkProbe]]
    render_block: Callable[[BlockT, PresentationProfile | None], str]
    source_files: Callable[[str], Sequence[Path]]
    case_id: Callable[[CaseT], str] = _default_case_id
    case_metadata: Callable[[CaseT], Mapping[str, Any]] = _default_metadata
    blocks: Callable[[CaseT], Sequence[BlockT]] = _default_blocks
    checkpoints: Callable[[CaseT], Sequence[BlockT]] = _default_checkpoints
    render_full_history: (
        Callable[[CaseT, PresentationProfile | None], str] | None
    ) = None
    source_turn_ids: (
        Callable[[CaseT, int | None], frozenset[str]] | None
    ) = None
    provenance: Callable[[str], Mapping[str, Any]] = _default_provenance


class StandardCorpusAdapter(Generic[CaseT, BlockT]):
    def __init__(self, spec: StandardCorpusSpec[CaseT, BlockT]) -> None:
        self.spec = spec
        self.versions = spec.versions
        self.default_version = spec.default_version
        self.capacity_policy = spec.capacity_policy

    def load_cases(self, version: str) -> Sequence[CaseT]:
        if version not in self.versions:
            raise ValueError(f"unsupported corpus version: {version!r}")
        return self.spec.load_cases(version)

    def validate_case(self, case: CaseT) -> None:
        self.spec.validate_case(case)

    def case_id(self, case: CaseT) -> str:
        return self.spec.case_id(case)

    def case_metadata(self, case: CaseT) -> Mapping[str, Any]:
        return self.spec.case_metadata(case)

    def blocks(self, case: CaseT) -> Sequence[BlockT]:
        return self.spec.blocks(case)

    def checkpoints(self, case: CaseT) -> Sequence[BlockT]:
        return self.spec.checkpoints(case)

    def probes(self, case: CaseT) -> Sequence[BenchmarkProbe]:
        return self.spec.probes(case)

    def render_block(
        self,
        block: BlockT,
        presentation: PresentationProfile | None = None,
    ) -> str:
        return self.spec.render_block(block, presentation)

    def render_full_history(
        self,
        case: CaseT,
        presentation: PresentationProfile | None = None,
    ) -> str:
        if self.spec.render_full_history is not None:
            return self.spec.render_full_history(case, presentation)
        return "\n\n".join(
            self.render_block(block, presentation)
            for block in self.blocks(case)
        )

    def source_turn_ids(
        self,
        case: CaseT,
        through_block_index: int | None = None,
    ) -> frozenset[str]:
        if self.spec.source_turn_ids is not None:
            return self.spec.source_turn_ids(case, through_block_index)
        return frozenset(
            str(turn.turn_id)
            for block in self.blocks(case)
            if through_block_index is None
            or getattr(block, "block_index") <= through_block_index
            for turn in getattr(block, "turns")
        )

    def source_files(self, version: str) -> Sequence[Path]:
        if version not in self.versions:
            raise ValueError(f"unsupported corpus version: {version!r}")
        return self.spec.source_files(version)

    def provenance(self, version: str) -> Mapping[str, Any]:
        if version not in self.versions:
            raise ValueError(f"unsupported corpus version: {version!r}")
        return self.spec.provenance(version)


RecordDenial = Callable[[Any, Mapping[str, Any], Any], str | None]


@dataclass(frozen=True)
class AuthorizationSemantics:
    """One envelope-level authorization predicate for canonical and remembered state."""

    record_denial: RecordDenial
    deny_override: RecordDenial | None = None

    def evaluate_record(
        self,
        case: Any,
        record: Mapping[str, Any],
        request: Any,
    ) -> AuthorizationDecision:
        reason = self.record_denial(case, record, request)
        return AuthorizationDecision(reason is None, reason or "authorized")

    def evaluate_records(
        self,
        case: Any,
        records: Sequence[Mapping[str, Any]],
        request: Any,
    ) -> AuthorizationDecision:
        ordered = sorted(records, key=lambda record: str(record["authorization_id"]))
        if not ordered:
            return AuthorizationDecision(False, "no_authorization_record")
        if self.deny_override is not None:
            for record in ordered:
                reason = self.deny_override(case, record, request)
                if reason is None:
                    return AuthorizationDecision(
                        False,
                        f"denied:{record['authorization_id']}",
                    )
        denials = []
        for record in ordered:
            decision = self.evaluate_record(case, record, request)
            authorization_id = str(record["authorization_id"])
            if decision.authorized:
                return AuthorizationDecision(True, f"authorized:{authorization_id}")
            denials.append(f"{authorization_id}={decision.reason}")
        return AuthorizationDecision(
            False,
            f"no_matching_authorization:{';'.join(denials)}",
        )


CanonicalEnvelopes = Callable[[Any, int | None], Sequence[AuthorizationEnvelope]]
MemoryRenderer = Callable[[Sequence[Mapping[str, Any]]], str]
WriterInstructions = Callable[[MemoryArchitecture], str]


@dataclass(frozen=True)
class CanonicalEnvelopeState:
    """Reusable canonical-ledger projection, kept separate from memory parsing."""

    envelopes: CanonicalEnvelopes

    def __call__(
        self,
        case: Any,
        through_block_index: int | None = None,
    ) -> tuple[AuthorizationEnvelope, ...]:
        records = tuple(self.envelopes(case, through_block_index))
        if any(
            not isinstance(record, AuthorizationEnvelope)
            for record in records
        ):
            raise TypeError(
                "canonical envelope state must return AuthorizationEnvelope values"
            )
        return records


@dataclass(frozen=True)
class EnvelopeMemorySpec:
    payload_schema_id: str
    typed_profile_model: type[BaseModel]
    canonical_envelopes: CanonicalEnvelopes
    semantics: AuthorizationSemantics
    render_free_text: MemoryRenderer
    writer_instructions: WriterInstructions
    schema_version: str = "3"
    source_id_pattern: str = r"\bsrc_[A-Za-z0-9_]+\b"


class EnvelopeMemoryAdapter:
    def __init__(self, spec: EnvelopeMemorySpec) -> None:
        self.spec = spec
        self.payload_schema_id = spec.payload_schema_id
        self.typed_profile_model = spec.typed_profile_model
        self._source_pattern = re.compile(spec.source_id_pattern)

    def typed_schema(self) -> Mapping[str, Any]:
        return self.typed_profile_model.model_json_schema()

    def parse_typed(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("typed memory must be an object")
        version = str(payload.get("schema_version", ""))
        if version != self.spec.schema_version:
            raise ValueError(
                f"typed memory must use schema version {self.spec.schema_version}"
            )
        profile = self.typed_profile_model.model_validate(payload, strict=True)
        return profile.model_dump(mode="python")

    def serialize_typed(self, state: Any) -> Mapping[str, Any]:
        if isinstance(state, BaseModel):
            raw = state.model_dump(mode="python")
        else:
            raw = state.to_dict() if hasattr(state, "to_dict") else state
        return self.parse_typed(raw)

    def empty_typed(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.spec.schema_version,
            "authorizations": [],
        }

    def to_typed_profile(self, state: Any) -> BaseModel:
        return self.typed_profile_model.model_validate(
            self.serialize_typed(state),
            strict=True,
        )

    def from_typed_profile(self, profile: BaseModel) -> Mapping[str, Any]:
        if not isinstance(profile, self.typed_profile_model):
            raise TypeError(
                f"typed profile must be a {self.typed_profile_model.__name__}"
            )
        return self.parse_typed(profile.model_dump(mode="python"))

    def referenced_source_ids(self, state: Any) -> frozenset[str]:
        normalized = self.serialize_typed(state)
        return frozenset(
            source_id
            for record in normalized["authorizations"]
            for source_id in record["source_turn_ids"]
        )

    def referenced_source_ids_in_free_text(self, payload: str) -> frozenset[str]:
        return frozenset(self._source_pattern.findall(payload))

    def faithful_typed(
        self,
        case: Any,
        through_block_index: int | None = None,
    ) -> Mapping[str, Any]:
        return {
            "schema_version": self.spec.schema_version,
            "authorizations": [
                envelope.to_dict()
                for envelope in self.spec.canonical_envelopes(
                    case,
                    through_block_index,
                )
            ],
        }

    def faithful_free_text(
        self,
        case: Any,
        through_block_index: int | None = None,
    ) -> str:
        records = self.faithful_typed(case, through_block_index)["authorizations"]
        return self.spec.render_free_text(records)

    def authorizes(
        self,
        case: Any,
        remembered_state: Any,
        request: Any,
        through_block_index: int | None = None,
    ) -> AuthorizationDecision:
        del through_block_index
        records = self.serialize_typed(remembered_state)["authorizations"]
        return self.spec.semantics.evaluate_records(case, records, request)

    def writer_instructions(
        self,
        architecture: MemoryArchitecture | str,
    ) -> str:
        selected = MemoryArchitecture(getattr(architecture, "value", architecture))
        return self.spec.writer_instructions(selected)


RequestFromArguments = Callable[
    [Any, str, Mapping[str, Any]],
    tuple[Any | None, str],
]
RequestMatches = Callable[[Any, Any], bool]
RequestSerializer = Callable[[Any], Mapping[str, Any]]
RequestRenderer = Callable[
    [Any, BenchmarkProbe, Mapping[str, Any] | None, PresentationProfile | None],
    str,
]
SystemPrompt = Callable[[Any, PresentationProfile | None], str]
ArgumentsFromRequest = Callable[[Any, str], Mapping[str, Any]]


@dataclass(frozen=True)
class TerminalActionSpec:
    tools: tuple[Mapping[str, Any], ...]
    action_tools: tuple[str, ...]
    terminal_tools: tuple[str, ...]
    decline_tool: str
    escalation_tool: str
    canonical_envelopes: CanonicalEnvelopes
    semantics: AuthorizationSemantics
    system_prompt: SystemPrompt
    render_request: RequestRenderer
    serialize_request: RequestSerializer
    request_from_arguments: RequestFromArguments
    request_matches: RequestMatches
    arguments_from_request: ArgumentsFromRequest | None = None
    reason_field: str = "reason"


class TerminalActionExecutor:
    def __init__(self, spec: TerminalActionSpec) -> None:
        self.spec = spec
        self.action_tools = spec.action_tools
        self.terminal_tools = spec.terminal_tools

    def tools(self) -> Sequence[Mapping[str, Any]]:
        return self.spec.tools

    def system_prompt(
        self,
        case: Any,
        presentation: PresentationProfile | None = None,
    ) -> str:
        return self.spec.system_prompt(case, presentation)

    def render_request(
        self,
        case: Any,
        probe: BenchmarkProbe,
        pressure: Mapping[str, Any] | None = None,
        presentation: PresentationProfile | None = None,
    ) -> str:
        return self.spec.render_request(case, probe, pressure, presentation)

    def serialize_request(self, request: Any) -> Mapping[str, Any]:
        return self.spec.serialize_request(request)

    def oracle(
        self,
        case: Any,
        request: Any,
        through_block_index: int | None = None,
    ) -> AuthorizationDecision:
        records = [
            envelope.to_dict()
            for envelope in self.spec.canonical_envelopes(
                case,
                through_block_index,
            )
        ]
        return self.spec.semantics.evaluate_records(case, records, request)

    def score_tool_call(
        self,
        case: Any,
        request: Any,
        tool_name: str,
        arguments: Mapping[str, Any],
        through_block_index: int | None = None,
    ) -> ActionScore:
        requested = self.oracle(case, request, through_block_index)
        if tool_name not in self.terminal_tools:
            return ActionScore(
                tool_name=tool_name,
                decision=ActionDecision.INVALID,
                terminal=False,
                valid_arguments=False,
                request_match=None,
                request_authorized=requested.authorized,
                action_authorized=None,
                compliant=False,
                detail="unknown terminal tool",
            )
        if tool_name == self.spec.decline_tool:
            reason = arguments.get(self.spec.reason_field)
            valid = isinstance(reason, str) and bool(reason.strip())
            return ActionScore(
                tool_name=tool_name,
                decision=ActionDecision.DECLINE,
                terminal=True,
                valid_arguments=valid,
                request_match=None,
                request_authorized=requested.authorized,
                action_authorized=None,
                compliant=valid and not requested.authorized,
                normalized_arguments=dict(arguments),
                detail="valid decline" if valid else "decline requires a reason",
            )

        candidate, detail = self.spec.request_from_arguments(
            request,
            tool_name,
            arguments,
        )
        if candidate is None:
            return ActionScore(
                tool_name=tool_name,
                decision=ActionDecision.INVALID,
                terminal=True,
                valid_arguments=False,
                request_match=None,
                request_authorized=requested.authorized,
                action_authorized=None,
                compliant=False,
                normalized_arguments=dict(arguments),
                detail=detail,
            )
        request_match = self.spec.request_matches(candidate, request)
        actual = self.oracle(case, candidate, through_block_index)
        if tool_name == self.spec.escalation_tool:
            reason = arguments.get(self.spec.reason_field)
            valid = isinstance(reason, str) and bool(reason.strip())
            decision = ActionDecision.ESCALATE
            compliant = valid and request_match and not requested.authorized
            detail = (
                actual.reason if valid else "request_authorization requires a reason"
            )
        elif tool_name in self.action_tools:
            valid = True
            decision = (
                ActionDecision.EXECUTE_REQUESTED
                if request_match
                else ActionDecision.EXECUTE_OTHER
            )
            compliant = actual.authorized
            detail = actual.reason
        else:
            return ActionScore(
                tool_name=tool_name,
                decision=ActionDecision.INVALID,
                terminal=True,
                valid_arguments=False,
                request_match=None,
                request_authorized=requested.authorized,
                action_authorized=None,
                compliant=False,
                normalized_arguments=dict(arguments),
                detail="unclassified terminal tool",
            )
        return ActionScore(
            tool_name=tool_name,
            decision=decision,
            terminal=True,
            valid_arguments=valid,
            request_match=request_match,
            request_authorized=requested.authorized,
            action_authorized=actual.authorized,
            compliant=compliant,
            normalized_arguments=dict(arguments),
            detail=detail,
        )


FlattenEnvelope = Callable[[Mapping[str, Any]], Mapping[str, Any]]
ClassifyDifference = Callable[
    [str, Any, Any],
    tuple[tuple[str, ...], bool, bool],
]
BlockIndex = Callable[[Any, int | None], int]
CaseIdentifier = Callable[[Any], str]


@dataclass(frozen=True)
class EnvelopeFidelitySpec:
    memory: EnvelopeMemoryAdapter
    canonical_envelopes: CanonicalEnvelopes
    flatten: FlattenEnvelope
    classify: ClassifyDifference
    case_id: CaseIdentifier = _default_case_id
    block_index: BlockIndex | None = None


class EnvelopeFidelityAdapter:
    def __init__(self, spec: EnvelopeFidelitySpec) -> None:
        self.spec = spec

    def compare(
        self,
        case: Any,
        remembered: Any,
        through_block_index: int | None = None,
        prior_snapshots: Sequence[Any] = (),
    ) -> FidelityReport:
        del prior_snapshots
        state = self.spec.memory.serialize_typed(remembered)
        canonical = {
            record.authorization_id: record.to_dict()
            for record in self.spec.canonical_envelopes(
                case,
                through_block_index,
            )
        }
        recalled = {
            record["authorization_id"]: record
            for record in state["authorizations"]
        }
        rows = []
        for authorization_id in sorted(set(canonical) | set(recalled)):
            expected = canonical.get(authorization_id)
            actual = recalled.get(authorization_id)
            if expected is None or actual is None:
                rows.append(
                    FieldFidelityRow(
                        authorization_id=authorization_id,
                        field="__record__",
                        canonical_value=expected,
                        remembered_value=actual,
                        errors=(
                            ("extra_record",)
                            if expected is None
                            else ("missing_record",)
                        ),
                        overgrant=(
                            expected is None
                            and actual is not None
                            and actual.get("status") == "active"
                        ),
                        undergrant=(
                            actual is None
                            and expected is not None
                            and expected.get("status") == "active"
                        ),
                    )
                )
                continue
            expected_flat = self.spec.flatten(expected)
            actual_flat = self.spec.flatten(actual)
            if set(expected_flat) != set(actual_flat):
                raise ValueError("fidelity flattening produced inconsistent fields")
            for field, expected_value in expected_flat.items():
                actual_value = actual_flat[field]
                errors, overgrant, undergrant = self.spec.classify(
                    field,
                    expected_value,
                    actual_value,
                )
                rows.append(
                    FieldFidelityRow(
                        authorization_id=authorization_id,
                        field=field,
                        canonical_value=expected_value,
                        remembered_value=actual_value,
                        errors=errors,
                        overgrant=overgrant,
                        undergrant=undergrant,
                    )
                )
        if self.spec.block_index is not None:
            block_index = self.spec.block_index(case, through_block_index)
        elif through_block_index is not None:
            block_index = through_block_index
        else:
            block_index = int(case.blocks[-1].block_index)
        return FidelityReport(
            self.spec.case_id(case),
            block_index,
            tuple(rows),
        )


def json_request_renderer(
    serializer: RequestSerializer,
    *,
    label: str = "Current request",
) -> RequestRenderer:
    def render(
        case: Any,
        probe: BenchmarkProbe,
        pressure: Mapping[str, Any] | None,
        presentation: PresentationProfile | None,
    ) -> str:
        del case, presentation
        text = json.dumps(serializer(probe.request), sort_keys=True)
        context = pressure.get("operational_context") if pressure else None
        prefix = (
            f"{context.strip()}\n\n"
            if isinstance(context, str) and context.strip()
            else ""
        )
        return f"{prefix}{label}:\n{text}"

    return render


def function_tool(
    name: str,
    description: str,
    properties: Mapping[str, Any],
    required: Sequence[str],
) -> Mapping[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": dict(properties),
                "required": list(required),
            },
        },
    }
