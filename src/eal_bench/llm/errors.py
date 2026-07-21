"""Exceptions raised by eal_bench.llm."""


class LLMError(Exception):
    """Base class for all eal_bench.llm errors."""


class ConfigError(LLMError):
    """Raised when config.yaml or the environment is misconfigured."""


class MissingAPIKeyError(ConfigError):
    """Raised when a provider's API key env var is unset."""
