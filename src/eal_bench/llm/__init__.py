"""eal_bench.llm — the provider-aware EAL-Bench LLM client.

Public API:
    LLM             — the client (complete / acomplete / batch / abatch)
    run_tool_loop   — optional helper that drives a full tool-calling loop
    load_config     — load config.yaml into a Config (rarely needed directly)
"""

from .client import LLM, run_tool_loop
from .config import (
    Config,
    ModelTargetConfig,
    ResolvedModelTarget,
    TaskConfig,
    load_config,
)
from .errors import ConfigError, MissingAPIKeyError, LLMError
from .langchain_models import LangChainCallLogger, create_langchain_chat_model
from .models import MODELS, ModelInfo, model_info, resolve_model, short_names

__all__ = [
    "LLM",
    "run_tool_loop",
    "load_config",
    "Config",
    "TaskConfig",
    "ModelTargetConfig",
    "ResolvedModelTarget",
    "LLMError",
    "ConfigError",
    "MissingAPIKeyError",
    "create_langchain_chat_model",
    "LangChainCallLogger",
    "resolve_model",
    "model_info",
    "short_names",
    "MODELS",
    "ModelInfo",
]
