from __future__ import annotations

import argparse
import importlib
import json
import re
from pathlib import Path


DOMAIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DOMAINS_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = DOMAINS_DIR / "__init__.py"

_INIT_TEMPLATE = """from .adapter import create_domain

__all__ = ["create_domain"]
"""

_ADAPTER_TEMPLATE = '''from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from domains.base import (
    AuthorizationMemoryDomain,
    BenchmarkProbe,
    CapacityPolicy,
    MemoryArchitecture,
    PresentationProfile,
    PromptPolicy,
    StudyProfile,
)
from domains.toolkit import (
    AuthorizationMemoryProfileBase,
    AuthorizationProfileBase,
    AuthorizationSemantics,
    CanonicalEnvelopeState,
    EnvelopeFidelityAdapter,
    EnvelopeFidelitySpec,
    EnvelopeMemoryAdapter,
    EnvelopeMemorySpec,
    StandardCorpusAdapter,
    StandardCorpusSpec,
    TerminalActionExecutor,
    TerminalActionSpec,
    function_tool,
)


DOMAIN_ID = "{domain_id}"


class ScopeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AuthorizationProfile(AuthorizationProfileBase[ScopeProfile]):
    pass


class MemoryProfile(AuthorizationMemoryProfileBase[AuthorizationProfile]):
    schema_version: Literal["3"]


def _load_cases(version: str) -> Sequence[Any]:
    if version != "fixture_v1":
        raise ValueError(f"unsupported corpus version: {{version!r}}")
    return ()


def _unsupported_case(case: Any) -> None:
    raise ValueError("replace the scaffold case validator")


def _probes(case: Any) -> Sequence[BenchmarkProbe]:
    del case
    return ()


def _render_block(block: Any, presentation: PresentationProfile | None) -> str:
    del presentation
    return str(block)


def _source_files(version: str) -> Sequence[Path]:
    if version != "fixture_v1":
        raise ValueError(f"unsupported corpus version: {{version!r}}")
    return tuple(sorted(Path(__file__).parent.glob("*.py")))


def _canonical(case: Any, through_block_index: int | None) -> Sequence[Any]:
    del case, through_block_index
    return ()


def _record_denial(
    case: Any,
    record: Mapping[str, Any],
    request: Any,
) -> str | None:
    del case, record, request
    return "not_configured"


SEMANTICS = AuthorizationSemantics(record_denial=_record_denial)
CANONICAL_STATE = CanonicalEnvelopeState(_canonical)


def _render_memory(records: Sequence[Mapping[str, Any]]) -> str:
    del records
    return "# Current authorizations"


def _writer_instructions(architecture: MemoryArchitecture) -> str:
    del architecture
    return "Maintain current authorization state."


def _system_prompt(case: Any, presentation: PresentationProfile | None) -> str:
    del case, presentation
    return "Apply the current authorization policy."


def _render_request(
    case: Any,
    probe: BenchmarkProbe,
    pressure: Mapping[str, Any] | None,
    presentation: PresentationProfile | None,
) -> str:
    del case, pressure, presentation
    return str(probe.request)


def _serialize_request(request: Any) -> Mapping[str, Any]:
    return dict(request)


def _request_from_arguments(
    requested: Any,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> tuple[Any | None, str]:
    del requested, tool_name, arguments
    return None, "replace the scaffold argument parser"


def _request_matches(left: Any, right: Any) -> bool:
    return left == right


def _flatten(record: Mapping[str, Any]) -> Mapping[str, Any]:
    return record


def _classify(
    field: str,
    expected: Any,
    actual: Any,
) -> tuple[tuple[str, ...], bool, bool]:
    del field
    return (() if expected == actual else ("contradiction",)), False, False


def create_domain() -> AuthorizationMemoryDomain:
    corpus = StandardCorpusAdapter(
        StandardCorpusSpec(
            versions=("fixture_v1",),
            default_version="fixture_v1",
            capacity_policy=CapacityPolicy(minimum_history_ratio=0),
            load_cases=_load_cases,
            validate_case=_unsupported_case,
            probes=_probes,
            render_block=_render_block,
            source_files=_source_files,
        )
    )
    memory = EnvelopeMemoryAdapter(
        EnvelopeMemorySpec(
            payload_schema_id=f"{{DOMAIN_ID}}/authorization-state/v3",
            typed_profile_model=MemoryProfile,
            canonical_envelopes=CANONICAL_STATE,
            semantics=SEMANTICS,
            render_free_text=_render_memory,
            writer_instructions=_writer_instructions,
        )
    )
    action = function_tool(
        "perform_action",
        "Perform the requested action.",
        {{}},
        (),
    )
    decline = function_tool(
        "decline_action",
        "Decline the requested action.",
        {{"reason": {{"type": "string"}}}},
        ("reason",),
    )
    executor = TerminalActionExecutor(
        TerminalActionSpec(
            tools=(action, decline),
            action_tools=("perform_action",),
            terminal_tools=("perform_action", "decline_action"),
            decline_tool="decline_action",
            escalation_tool="decline_action",
            canonical_envelopes=CANONICAL_STATE,
            semantics=SEMANTICS,
            system_prompt=_system_prompt,
            render_request=_render_request,
            serialize_request=_serialize_request,
            request_from_arguments=_request_from_arguments,
            request_matches=_request_matches,
        )
    )
    presentation = PresentationProfile(
        presentation_id="fixture_v1",
        description="Initial scaffold presentation.",
        prompt_policy_id="dev_prompt_v1",
    )
    return AuthorizationMemoryDomain(
        domain_id=DOMAIN_ID,
        adapter_version="1",
        maturity="development",
        canonical_seed=20260719,
        corpus=corpus,
        memory=memory,
        executor=executor,
        fidelity=EnvelopeFidelityAdapter(
            EnvelopeFidelitySpec(
                memory=memory,
                canonical_envelopes=CANONICAL_STATE,
                flatten=_flatten,
                classify=_classify,
            )
        ),
        studies={{
            "controls": StudyProfile(
                "controls",
                "Fixture route declaration; add a builder before registration.",
            )
        }},
        presentations={{presentation.presentation_id: presentation}},
        default_presentation_id=presentation.presentation_id,
        prompt_policies={{
            "dev_prompt_v1": PromptPolicy("dev_prompt_v1")
        }},
    )
'''


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an unregistered composition-based domain package."
    )
    parser.add_argument("domain_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--register", action="store_true")
    return parser


def _registry_text(domain_id: str, source: str) -> str:
    factory_name = f"_{domain_id}"
    if f'"{domain_id}"' in source or f"def {factory_name}(" in source:
        raise ValueError(f"domain {domain_id!r} is already registered")
    marker = "\n\nDOMAINS: dict[str, DomainFactory] = {"
    if marker not in source:
        raise ValueError("explicit domain registry marker was not found")
    factory = (
        f"\n\ndef {factory_name}() -> AuthorizationMemoryDomain:\n"
        f"    from .{domain_id} import create_domain\n\n"
        f"    return create_domain()\n"
    )
    updated = source.replace(marker, factory + marker, 1)
    registry_line = "DOMAINS: dict[str, DomainFactory] = {\n"
    return updated.replace(
        registry_line,
        registry_line + f'    "{domain_id}": {factory_name},\n',
        1,
    )


def scaffold(
    domain_id: str,
    *,
    dry_run: bool,
    register: bool,
) -> dict[str, object]:
    if not DOMAIN_ID_PATTERN.fullmatch(domain_id):
        raise ValueError(
            "domain_id must use lowercase letters, digits, and underscores"
        )
    package_dir = DOMAINS_DIR / domain_id
    files = {
        package_dir / "__init__.py": _INIT_TEMPLATE,
        package_dir / "adapter.py": _ADAPTER_TEMPLATE.format(domain_id=domain_id),
    }
    if package_dir.exists():
        raise ValueError(f"domain package already exists: {package_dir}")
    registry_source = REGISTRY_PATH.read_text(encoding="utf-8")
    updated_registry = (
        _registry_text(domain_id, registry_source)
        if register
        else registry_source
    )
    result = {
        "status": "dry_run" if dry_run else "created",
        "domain_id": domain_id,
        "registered": register,
        "files": [str(path) for path in files],
        "registry": str(REGISTRY_PATH) if register else None,
    }
    if dry_run:
        return result
    package_dir.mkdir()
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
    if register:
        importlib.invalidate_caches()
        module = importlib.import_module(f"domains.{domain_id}")
        domain = module.create_domain()
        if domain.domain_id != domain_id:
            raise ValueError("scaffold create_domain() returned the wrong domain ID")
        domain.validate()
        temporary = REGISTRY_PATH.with_suffix(".py.tmp")
        temporary.write_text(updated_registry, encoding="utf-8")
        temporary.replace(REGISTRY_PATH)
    return result


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    print(
        json.dumps(
            scaffold(
                args.domain_id,
                dry_run=args.dry_run,
                register=args.register,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
