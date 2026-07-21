"""Load config.yaml + .env into typed dataclasses. The config holds only the *name* of each
provider's key env var; the secret is resolved lazily from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .errors import ConfigError, MissingAPIKeyError
from .models import resolve_model


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str

    def resolve_api_key(self) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise MissingAPIKeyError(
                f"Provider '{self.name}' needs ${self.api_key_env}, but it is unset. "
                f"Add it to your .env (see .env.example)."
            )
        return key


@dataclass(frozen=True)
class RateLimit:
    """Either rpm or rph (requests per minute / hour). None means unlimited."""

    max_rate: float | None = None
    period_seconds: float = 60.0

    @classmethod
    def from_dict(cls, d: dict | None) -> RateLimit:
        if not d:
            return cls(max_rate=None)
        if "rpm" in d and "rph" in d:
            raise ConfigError("rate_limit cannot set both 'rpm' and 'rph'.")
        if "rpm" in d:
            return cls(max_rate=float(d["rpm"]), period_seconds=60.0)
        if "rph" in d:
            return cls(max_rate=float(d["rph"]), period_seconds=3600.0)
        raise ConfigError("rate_limit must contain 'rpm' or 'rph'.")


@dataclass(frozen=True)
class TaskConfig:
    name: str
    provider: str
    model: str
    params: dict = field(default_factory=dict)
    rate_limit: RateLimit = field(default_factory=RateLimit)
    max_concurrency: int = 8
    max_retries: int = 5
    default_target: str = ""


@dataclass(frozen=True)
class ModelTargetConfig:
    """A stable, provider-aware route to one model."""

    name: str
    provider: str
    requested_model: str
    model: str
    capabilities: frozenset[str] = field(default_factory=frozenset)
    request_parameters: dict = field(default_factory=dict)
    rate_limit: RateLimit = field(default_factory=RateLimit)
    max_concurrency: int = 8


@dataclass(frozen=True)
class ResolvedModelTarget:
    """The effective route for one call, including same-provider model overrides."""

    target_id: str
    provider: str
    requested_model: str
    resolved_model: str
    capabilities: frozenset[str]
    request_parameters: dict
    rate_limit: RateLimit
    max_concurrency: int
    configured_target_id: str = ""

    @property
    def gate_key(self) -> str:
        return f"{self.provider}:{self.target_id}"


@dataclass(frozen=True)
class Config:
    providers: dict[str, ProviderConfig]
    tasks: dict[str, TaskConfig]
    log_path: str
    batch_size: int = 20  # default concurrent wave size for llm.batch()
    model_targets: dict[str, ModelTargetConfig] = field(default_factory=dict)

    def task(self, name: str) -> TaskConfig:
        try:
            return self.tasks[name]
        except KeyError:
            known = ", ".join(sorted(self.tasks)) or "(none)"
            raise ConfigError(f"Unknown task '{name}'. Defined tasks: {known}.") from None

    def provider(self, name: str) -> ProviderConfig:
        try:
            return self.providers[name]
        except KeyError:
            known = ", ".join(sorted(self.providers)) or "(none)"
            raise ConfigError(
                f"Unknown provider '{name}'. Defined providers: {known}."
            ) from None

    def target(self, name: str) -> ModelTargetConfig:
        try:
            return self.model_targets[name]
        except KeyError:
            known = ", ".join(sorted(self.model_targets)) or "(none)"
            raise ConfigError(
                f"Unknown model target '{name}'. Defined targets: {known}."
            ) from None

    def resolve_target(
        self,
        task_name: str,
        *,
        target: str | None = None,
        model: str | None = None,
    ) -> ResolvedModelTarget:
        """Resolve a task plus optional target/model override without contacting an API."""
        task = self.task(task_name)
        if target is not None and model is not None:
            raise ConfigError(
                "Pass either target= (provider-aware) or model= "
                "(same-provider override), not both."
            )

        target_id = task.default_target if target is None else target
        configured = self.target(target_id)
        requested_model = configured.requested_model if model is None else str(model)
        return ResolvedModelTarget(
            target_id=configured.name,
            provider=configured.provider,
            requested_model=requested_model,
            resolved_model=resolve_model(requested_model),
            capabilities=configured.capabilities,
            request_parameters=dict(configured.request_parameters),
            rate_limit=configured.rate_limit,
            max_concurrency=configured.max_concurrency,
            configured_target_id=configured.name,
        )


def load_config(
    path: str | os.PathLike = "config.yaml",
    *,
    load_env: bool = True,
) -> Config:
    """Read config.yaml (and .env) into a validated Config."""
    if load_env:
        load_dotenv()  # won't override vars already in the environment

    cfg_path = Path(path)
    if not cfg_path.exists():
        raise ConfigError(f"Config file not found: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text()) or {}
    defaults = raw.get("defaults", {}) or {}
    default_max_retries = int(defaults.get("max_retries", 3))
    default_max_concurrency = int(defaults.get("max_concurrency", 20))
    batch_size = int(defaults.get("batch_size", 20))
    log_path = str(defaults.get("log_path", "logs/calls.jsonl"))

    providers: dict[str, ProviderConfig] = {}
    for name, p in (raw.get("providers") or {}).items():
        if "base_url" not in p or "api_key_env" not in p:
            raise ConfigError(
                f"Provider '{name}' must define 'base_url' and 'api_key_env'."
            )
        providers[name] = ProviderConfig(
            name=name, base_url=p["base_url"], api_key_env=p["api_key_env"]
        )

    if not providers:
        raise ConfigError("No providers defined in config.")

    model_targets: dict[str, ModelTargetConfig] = {}
    for name, target in (raw.get("model_targets") or {}).items():
        if not isinstance(target, dict):
            raise ConfigError(f"Model target '{name}' must be a mapping.")
        if "provider" not in target or "model" not in target:
            raise ConfigError(
                f"Model target '{name}' must define 'provider' and 'model'."
            )
        provider_name = str(target["provider"])
        if provider_name not in providers:
            raise ConfigError(
                f"Model target '{name}' references unknown provider '{provider_name}'."
            )
        raw_capabilities = target.get("capabilities", []) or []
        if not isinstance(raw_capabilities, list) or not all(
            isinstance(capability, str) and capability.strip()
            for capability in raw_capabilities
        ):
            raise ConfigError(
                f"Model target '{name}' capabilities must be a list of non-empty strings."
            )
        requested_model = str(target["model"]).strip()
        if not requested_model:
            raise ConfigError(f"Model target '{name}' must define a non-empty model.")
        max_concurrency = int(
            target.get("max_concurrency", default_max_concurrency)
        )
        if max_concurrency < 1:
            raise ConfigError(
                f"Model target '{name}' max_concurrency must be at least 1."
            )
        request_parameters = target.get("request_parameters", {}) or {}
        if not isinstance(request_parameters, dict):
            raise ConfigError(
                f"Model target '{name}' request_parameters must be a mapping."
            )
        model_targets[name] = ModelTargetConfig(
            name=name,
            provider=provider_name,
            requested_model=requested_model,
            model=resolve_model(requested_model),
            capabilities=frozenset(
                capability.strip() for capability in raw_capabilities
            ),
            request_parameters=dict(request_parameters),
            rate_limit=RateLimit.from_dict(target.get("rate_limit")),
            max_concurrency=max_concurrency,
        )

    tasks: dict[str, TaskConfig] = {}
    for name, t in (raw.get("tasks") or {}).items():
        if not isinstance(t, dict):
            raise ConfigError(f"Task '{name}' must be a mapping.")
        default_target = t.get("default_target")
        if "provider" in t or "model" in t:
            raise ConfigError(
                f"Task '{name}' must select a model target with 'default_target'; "
                "direct provider/model task routes are unsupported."
            )
        if default_target is None:
            raise ConfigError(f"Task '{name}' must define 'default_target'.")
        if "rate_limit" in t or "max_concurrency" in t:
            raise ConfigError(
                f"Task '{name}' uses a model target; configure rate_limit and "
                "max_concurrency on that target."
            )
        try:
            configured_target = model_targets[str(default_target)]
        except KeyError:
            known = ", ".join(sorted(model_targets)) or "(none)"
            raise ConfigError(
                f"Task '{name}' references unknown model target "
                f"'{default_target}'. Defined targets: {known}."
            ) from None
        provider_name = configured_target.provider
        model = configured_target.model
        rate_limit = configured_target.rate_limit
        max_concurrency = configured_target.max_concurrency
        tasks[name] = TaskConfig(
            name=name,
            provider=provider_name,
            model=model,
            params=t.get("params", {}) or {},
            rate_limit=rate_limit,
            max_concurrency=max_concurrency,
            max_retries=int(t.get("max_retries", default_max_retries)),
            default_target=str(default_target),
        )

    if not tasks:
        raise ConfigError("No tasks defined in config.")

    return Config(
        providers=providers,
        tasks=tasks,
        log_path=log_path,
        batch_size=batch_size,
        model_targets=model_targets,
    )
