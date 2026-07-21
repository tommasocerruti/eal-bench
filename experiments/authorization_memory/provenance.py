from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from .schemas import ModelProvenance


def effective_behavioral_parameters(
    config: Any,
    task: str,
    *,
    overrides: Mapping[str, Any],
    tools: Sequence[Mapping[str, Any]],
    required_capabilities: Sequence[str],
) -> dict[str, Any]:
    params = {
        **copy.deepcopy(dict(config.task(task).params)),
        **copy.deepcopy(dict(overrides)),
    }
    params.pop("model", None)
    params.pop("tools", None)
    if tools:
        params["tool_names"] = [
            str(tool["function"]["name"])
            for tool in tools
        ]
    params["required_capabilities"] = sorted(set(required_capabilities))
    return params


def resolve_model_provenance(
    config: Any,
    task: str,
    target_id: str,
    *,
    effective_parameters: Mapping[str, Any],
) -> ModelProvenance:
    resolved = config.resolve_target(task, target=target_id)
    parameters = {
        **copy.deepcopy(dict(resolved.request_parameters)),
        **copy.deepcopy(dict(effective_parameters)),
    }
    return ModelProvenance(
        target_id=resolved.target_id,
        provider=resolved.provider,
        requested_model=resolved.requested_model,
        resolved_model=resolved.resolved_model,
        effective_parameters=parameters,
    )


def with_response_model(
    provenance: ModelProvenance,
    response_model: str | None,
) -> ModelProvenance:
    return ModelProvenance(
        target_id=provenance.target_id,
        provider=provenance.provider,
        requested_model=provenance.requested_model,
        resolved_model=provenance.resolved_model,
        response_model=response_model,
        effective_parameters=copy.deepcopy(provenance.effective_parameters),
    )


def target_route_manifest(
    config: Any,
    task: str,
    target_id: str,
    *,
    call_profiles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    resolved = config.resolve_target(task, target=target_id)
    rate_limit = {
        "max_rate": resolved.rate_limit.max_rate,
        "period_seconds": resolved.rate_limit.period_seconds,
    }
    return {
        "target_id": resolved.target_id,
        "provider": resolved.provider,
        "requested_model": resolved.requested_model,
        "resolved_model": resolved.resolved_model,
        "response_model": None,
        "response_models_observed": [],
        "capabilities": sorted(resolved.capabilities),
        "request_parameters": copy.deepcopy(
            dict(resolved.request_parameters)
        ),
        "max_concurrency": resolved.max_concurrency,
        "rate_limit": rate_limit,
        "call_profiles": copy.deepcopy(list(call_profiles)),
    }
