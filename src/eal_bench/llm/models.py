"""Model roster — short names → Baseten slugs. `resolve_model("glm")` -> "zai-org/GLM-4.7";
full slugs and unknowns pass through unchanged. Source of truth for MODELS.md."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    slug: str
    context_k: int  # context window, K tokens
    max_output_k: int  # max output, K tokens
    reasoning: bool = False  # reasons before answering — give it a generous max_tokens
    aliases: tuple[str, ...] = ()


# All run on the `baseten` provider.
MODELS: list[ModelInfo] = [
    ModelInfo(
        "deepseek-ai/DeepSeek-V4-Pro", 1048, 1048,
        aliases=("deepseek", "deepseek-v4", "ds"),
    ),
    ModelInfo(
        "zai-org/GLM-4.7", 200, 200,
        aliases=("glm", "glm-4.7", "glm47"),
    ),
    ModelInfo(
        "moonshotai/Kimi-K2.6", 262, 262,
        aliases=("kimi", "kimi-k2.6", "k2.6"),
    ),
    ModelInfo(
        "openai/gpt-oss-120b", 128, 128, reasoning=True,
        aliases=("gptoss", "gpt-oss", "oss"),
    ),
    ModelInfo(
        "nvidia/Nemotron-120B-A12B", 202, 202, reasoning=True,
        aliases=("nemotron", "nemotron-super", "super"),
    ),
]


def _build_index() -> dict[str, ModelInfo]:
    index: dict[str, ModelInfo] = {}
    for m in MODELS:
        keys = {m.slug.lower(), m.slug.split("/")[-1].lower(), *(a.lower() for a in m.aliases)}
        for k in keys:
            index[k] = m
    return index


_BY_NAME = _build_index()


def model_info(name: str) -> ModelInfo | None:
    """Look up by short name, bare name, or full slug (case-insensitive)."""
    return _BY_NAME.get(name.strip().lower())


def resolve_model(name: str) -> str:
    """Short name -> full slug; unknowns pass through. Idempotent."""
    info = _BY_NAME.get(name.strip().lower())
    return info.slug if info else name.strip()


def short_names() -> list[str]:
    """Canonical short name per model (first alias), for CLI help."""
    return [m.aliases[0] for m in MODELS if m.aliases]
