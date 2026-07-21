from __future__ import annotations

from copy import deepcopy
from typing import Any

from domains.base import AuthorizationMemoryDomain, PresentationProfile


def model_visible_tools(
    domain: AuthorizationMemoryDomain,
    presentation: PresentationProfile,
) -> list[dict[str, Any]]:
    """Apply presentation-owned wording without changing tool semantics."""

    tools = deepcopy(list(domain.executor.tools()))
    overrides = domain.get_prompt_policy(
        presentation
    ).tool_description_overrides
    observed = set()
    for tool in tools:
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str):
            continue
        observed.add(name)
        if name in overrides:
            function["description"] = overrides[name]
    unknown = sorted(set(overrides) - observed)
    if unknown:
        raise ValueError(
            "tool description overrides reference unknown tools: "
            + ", ".join(unknown)
        )
    return tools

