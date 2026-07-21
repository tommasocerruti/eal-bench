"""Shared loading, validation, and aggregation for current analysis artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

TRIAL_SCHEMA_VERSION = 5
SUPPORTED_TRIAL_SCHEMA_VERSIONS = frozenset({TRIAL_SCHEMA_VERSION})
LANGMEM_MEMORY_IMPLEMENTATION_ID = "langmem_profile"
SUPPORTED_MEMORY_ARTIFACT_SCHEMA_VERSIONS = frozenset({4})
DECISIONS = frozenset(
    {
        "execute_requested",
        "execute_other",
        "decline",
        "escalate",
        "no_action",
        "invalid",
        "provider_error",
    }
)

@dataclass(frozen=True)
class LoadedRun:
    """A run loaded without modifying its source artifacts."""

    rows: list[dict[str, Any]]
    manifest: dict[str, Any] | None
    domain_id: str
    source_schema_version: int
    trials_path: Path
    manifest_path: Path | None
    raw_sha256: str
    hash_verified: bool


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL verbatim, with line-aware validation."""

    source = Path(path)
    rows = []
    with source.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {source}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"row at {source}:{line_number} must be a JSON object")
            rows.append(row)
    return rows


def load(
    path: str | Path,
    *,
    domain: str | None = None,
    verify_hashes: bool = True,
) -> list[dict[str, Any]]:
    """Load an artifact, normalizing trial files and leaving other JSONL untouched.

    Existing analysis callers use this function. A JSONL referenced as ``trials`` by
    its sibling manifest is upgraded in memory. Other run artifacts are returned
    verbatim. An orphaned JSONL is treated as trials only when ``domain`` is supplied.
    """

    source = Path(path)
    if source.is_dir() or source.name == "manifest.json":
        return load_run(source, domain=domain, verify_hashes=verify_hashes).rows

    manifest_path = source.parent / "manifest.json"
    if manifest_path.is_file():
        manifest = _load_manifest(manifest_path)
        artifact_kind = _artifact_kind(manifest, source)
        if artifact_kind == "trials":
            return load_run(
                source,
                domain=domain,
                verify_hashes=verify_hashes,
            ).rows
        return load_jsonl(source)

    if domain is None:
        raise ValueError(
            f"{source} has no sibling manifest; pass domain=... to load orphaned trials "
            "or use load_jsonl() for a non-trial artifact"
        )
    return load_run(source, domain=domain, verify_hashes=verify_hashes).rows


def load_run(
    path: str | Path,
    *,
    domain: str | None = None,
    verify_hashes: bool = True,
) -> LoadedRun:
    """Load and normalize one run from a directory, manifest, or trials JSONL."""

    source = Path(path)
    trials_path, manifest_path, manifest = _resolve_run(source)
    manifest_domain = _manifest_domain(manifest) if manifest is not None else None
    if domain is not None and manifest_domain is not None and domain != manifest_domain:
        raise ValueError(
            f"requested domain {domain!r} does not match manifest domain "
            f"{manifest_domain!r}"
        )
    domain_id = domain or manifest_domain
    if domain_id is None:
        raise ValueError(
            f"{trials_path} has no manifest domain; pass domain=... explicitly"
        )

    raw_sha256 = _sha256_file(trials_path)
    declared_hash = (
        _declared_artifact_hash(manifest, "trials", trials_path.name)
        if manifest is not None
        else None
    )
    hash_verified = False
    if verify_hashes and declared_hash is not None:
        if raw_sha256 != declared_hash:
            raise ValueError(
                f"raw trials hash mismatch for {trials_path}: expected "
                f"{declared_hash}, got {raw_sha256}"
            )
        hash_verified = True

    raw_rows = load_jsonl(trials_path)
    declared_rows = (
        _declared_artifact_rows(manifest, "trials")
        if manifest is not None
        else None
    )
    if declared_rows is not None and declared_rows != len(raw_rows):
        raise ValueError(
            f"raw trials row-count mismatch for {trials_path}: expected "
            f"{declared_rows}, got {len(raw_rows)}"
        )
    manifest_version = _manifest_trial_schema_version(manifest)
    row_versions = {
        _coerce_schema_version(row.get("schema_version"))
        for row in raw_rows
        if row.get("schema_version") is not None
    }
    if len(row_versions) > 1:
        raise ValueError(
            f"{trials_path} mixes trial schema versions: {sorted(row_versions)}"
        )
    row_version = next(iter(row_versions), None)
    if (
        manifest_version is not None
        and row_version is not None
        and manifest_version != row_version
    ):
        raise ValueError(
            f"{trials_path} schema version {row_version} does not match manifest "
            f"version {manifest_version}"
        )
    source_schema_version = row_version or manifest_version
    if source_schema_version is None:
        raise ValueError(f"{trials_path} does not declare a trial schema version")
    if source_schema_version not in SUPPORTED_TRIAL_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported trial schema version {source_schema_version} in {trials_path}"
        )

    rows = [
        normalize_trial_row(
            row,
            domain_id=domain_id,
            source_schema_version=source_schema_version,
            manifest_memory_implementation_id=_manifest_memory_implementation_id(
                manifest
            ),
            manifest_memory_implementation_hash=(
                _manifest_memory_implementation_hash(manifest)
            ),
        )
        for row in raw_rows
    ]
    return LoadedRun(
        rows=rows,
        manifest=manifest,
        domain_id=domain_id,
        source_schema_version=source_schema_version,
        trials_path=trials_path,
        manifest_path=manifest_path,
        raw_sha256=raw_sha256,
        hash_verified=hash_verified,
    )


def load_memory_artifacts(
    path: str | Path,
    *,
    domain: str | None = None,
    verify_hashes: bool = True,
) -> list[dict[str, Any]]:
    """Load current memory rows and verify their payload hashes."""

    source = Path(path)
    memories_path, _, manifest = _resolve_artifact(source, "memories")
    manifest_domain = _manifest_domain(manifest) if manifest is not None else None
    if domain is not None and manifest_domain is not None and domain != manifest_domain:
        raise ValueError(
            f"requested domain {domain!r} does not match manifest domain "
            f"{manifest_domain!r}"
        )
    domain_id = domain or manifest_domain
    if domain_id is None:
        raise ValueError(
            f"{memories_path} has no manifest domain; pass domain=... explicitly"
        )

    raw_sha256 = _sha256_file(memories_path)
    declared_hash = (
        _declared_artifact_hash(manifest, "memories", memories_path.name)
        if manifest is not None
        else None
    )
    if verify_hashes and declared_hash is not None and raw_sha256 != declared_hash:
        raise ValueError(
            f"raw memories hash mismatch for {memories_path}: expected "
            f"{declared_hash}, got {raw_sha256}"
        )

    raw_rows = load_jsonl(memories_path)
    declared_rows = (
        _declared_artifact_rows(manifest, "memories")
        if manifest is not None
        else None
    )
    if declared_rows is not None and declared_rows != len(raw_rows):
        raise ValueError(
            f"raw memories row-count mismatch for {memories_path}: expected "
            f"{declared_rows}, got {len(raw_rows)}"
        )
    manifest_artifact_version = _manifest_artifact_schema_version(
        manifest,
        "memories",
    )
    row_versions = {
        _coerce_schema_version(row.get("schema_version"))
        for row in raw_rows
        if row.get("schema_version") is not None
    }
    if len(row_versions) > 1:
        raise ValueError(
            f"{memories_path} mixes memory artifact schema versions: "
            f"{sorted(row_versions)}"
        )
    row_artifact_version = next(iter(row_versions), None)
    if (
        manifest_artifact_version is not None
        and row_artifact_version is not None
        and manifest_artifact_version != row_artifact_version
    ):
        raise ValueError(
            f"{memories_path} schema version {row_artifact_version} does not "
            f"match manifest version {manifest_artifact_version}"
        )
    artifact_version = manifest_artifact_version or row_artifact_version
    if artifact_version is None:
        raise ValueError(
            f"{memories_path} does not declare a memory artifact schema version"
        )
    if artifact_version not in SUPPORTED_MEMORY_ARTIFACT_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported memory artifact schema version {artifact_version}"
        )

    from domains import get_domain

    adapter = get_domain(domain_id)
    return [
        _normalize_memory_artifact(
            row,
            domain_id=domain_id,
            domain=adapter,
            manifest=manifest,
            verify_content_hash=verify_hashes,
            source_schema_version=artifact_version,
            manifest_memory_implementation_id=_manifest_memory_implementation_id(
                manifest
            ),
            manifest_memory_implementation_hash=(
                _manifest_memory_implementation_hash(manifest)
            ),
        )
        for row in raw_rows
    ]


def normalize_trial_row(
    row: Mapping[str, Any],
    *,
    domain_id: str,
    source_schema_version: int | None = None,
    manifest_memory_implementation_id: str | None = None,
    manifest_memory_implementation_hash: str | None = None,
) -> dict[str, Any]:
    """Validate and copy a current trial row."""

    normalized = copy.deepcopy(dict(row))
    row_domain = normalized.get("domain_id") or normalized.get("domain")
    if row_domain is not None and row_domain != domain_id:
        raise ValueError(
            f"trial domain {row_domain!r} does not match run domain {domain_id!r}"
        )

    row_schema = _coerce_schema_version(normalized.get("schema_version"))
    if source_schema_version is not None and row_schema is not None:
        if row_schema != source_schema_version:
            raise ValueError(
                f"row schema version {row_schema} does not match run schema version "
                f"{source_schema_version}"
            )
    if row_schema != TRIAL_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported trial schema version {row_schema!r}; expected "
            f"{TRIAL_SCHEMA_VERSION}"
        )
    _require_v5_outcomes(normalized)

    normalized["schema_version"] = TRIAL_SCHEMA_VERSION
    normalized.setdefault("domain_id", domain_id)
    normalized.setdefault("finish_reason", None)
    normalized.setdefault("provider_error", None)
    normalized.setdefault("response_error", None)
    normalized["metadata"] = _normalize_metadata(normalized.get("metadata"))
    core = normalized["metadata"]["core"]
    if not core.get("presentation_id") or not core.get("presentation_hash"):
        raise ValueError("trial is missing versioned presentation provenance")
    memory_implementation_id = _resolve_memory_implementation_id(
        _row_memory_implementation_id(normalized),
        (
            manifest_memory_implementation_id
            if _has_writer_provenance(normalized)
            else None
        ),
        artifact_label="trial",
    )
    memory_implementation_hash = _resolve_memory_implementation_hash(
        _row_memory_implementation_hash(normalized),
        (
            manifest_memory_implementation_hash
            if _has_writer_provenance(normalized)
            else None
        ),
        artifact_label="trial",
    )
    if (memory_implementation_id is None) != (memory_implementation_hash is None):
        raise ValueError("trial must record both memory implementation ID and hash")
    if memory_implementation_id is not None:
        normalized["memory_implementation_id"] = memory_implementation_id
        normalized["metadata"]["core"][
            "memory_implementation_id"
        ] = memory_implementation_id
        normalized["memory_implementation_hash"] = memory_implementation_hash
        normalized["metadata"]["core"][
            "memory_implementation_hash"
        ] = memory_implementation_hash
    return normalized


def metadata_value(
    row: Mapping[str, Any],
    key: str,
    *,
    namespace: str | None = None,
    default: Any = None,
) -> Any:
    """Read a top-level or current namespaced metadata value."""

    if key in row:
        return row[key]
    metadata = row.get("metadata")
    if not isinstance(metadata, Mapping):
        return default
    if namespace is not None:
        values = metadata.get(namespace)
        if isinstance(values, Mapping) and key in values:
            return values[key]
        return default
    if key in metadata:
        return metadata[key]
    for candidate in ("core", "study", "domain"):
        values = metadata.get(candidate)
        if isinstance(values, Mapping) and key in values:
            return values[key]
    return default


def metadata_namespace(
    row: Mapping[str, Any],
    namespace: str,
) -> Mapping[str, Any]:
    """Return one of the ``core``, ``study``, or ``domain`` metadata namespaces."""

    if namespace not in {"core", "study", "domain"}:
        raise ValueError("namespace must be 'core', 'study', or 'domain'")
    metadata = row.get("metadata")
    if not isinstance(metadata, Mapping):
        return {}
    values = metadata.get(namespace)
    return values if isinstance(values, Mapping) else {}


def analysis_value(
    row: Mapping[str, Any],
    key: str,
    *,
    default: Any = None,
) -> Any:
    """Resolve analysis fields from the v5 provenance envelope."""

    if key in row:
        return row[key]
    dotted = _dotted_value(row, key)
    if dotted is not None:
        return dotted
    if key in {"condition", "condition_id", "scenario"}:
        for candidate in ("condition_id", "condition", "scenario"):
            value = metadata_value(row, candidate)
            if value is not None:
                return value
        return default
    if key in {"domain", "domain_id"}:
        return row.get("domain_id") or row.get("domain") or default
    if key == "target_pair":
        writer = analysis_value(row, "writer_target")
        executor = analysis_value(row, "executor_target")
        if writer is None and executor is None:
            return default
        return f"{writer or 'no-writer'} → {executor or 'unknown-executor'}"
    for role in ("writer", "executor"):
        prefix = f"{role}_"
        if not key.startswith(prefix):
            continue
        field = key.removeprefix(prefix)
        if field == "target":
            field = "target_id"
        if field in {
            "target_id",
            "provider",
            "requested_model",
            "resolved_model",
            "response_model",
            "effective_parameters",
            "model",
        }:
            return _provenance_value(row, role, field, default=default)
    if key == "model":
        return _provenance_value(row, "executor", "model", default=default)
    return metadata_value(row, key, default=default)


def require_single_memory_implementation(
    rows: Iterable[Mapping[str, Any]],
    *,
    context: str = "analysis",
) -> str | None:
    """Reject accidental aggregation across different memory implementations."""

    materialized = list(rows)
    observed = {
        (
            str(implementation_id),
            str(implementation_hash),
        )
        for row in materialized
        if (
            implementation_id := analysis_value(
                row, "memory_implementation_id"
            )
        )
        is not None
        for implementation_hash in (
            analysis_value(row, "memory_implementation_hash"),
        )
        if implementation_hash is not None
    }
    labels = set(observed)
    missing_writer_provenance = sum(
        (
            analysis_value(row, "memory_implementation_id") is None
            or analysis_value(row, "memory_implementation_hash") is None
        )
        and _has_writer_provenance(row)
        for row in materialized
    )
    if missing_writer_provenance:
        labels.add("<unrecorded-writer>")
    if labels == {"<unrecorded-writer>"}:
        raise ValueError(
            f"{context} found writer-produced rows without a recorded memory "
            "implementation"
        )
    if len(labels) > 1:
        raise ValueError(
            f"{context} refuses to pool memory implementations "
            f"{sorted(labels)}; analyze them separately or group by "
            "'memory_implementation_id'"
        )
    selected = next(iter(observed), None)
    return selected[0] if selected is not None else None


def require_single_memory_implementation_per_group(
    rows: Iterable[Mapping[str, Any]],
    by: Iterable[str],
    *,
    context: str = "analysis",
) -> None:
    """Reject implementation pooling within every analysis group."""

    keys = tuple(by)
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(analysis_value(row, key) for key in keys)].append(row)
    for key, group in grouped.items():
        label = dict(zip(keys, key))
        require_single_memory_implementation(
            group,
            context=f"{context} group {label}",
        )


def require_single_model_route(
    rows: Iterable[Mapping[str, Any]],
    *,
    context: str = "analysis",
) -> tuple[str, str] | None:
    """Reject aggregation across writer/executor provider-target treatments."""

    materialized = list(rows)
    writer_routes = {
        route
        for row in materialized
        if (route := _role_route_label(row, "writer", allow_absent=True))
        != "no-writer"
    }
    executor_routes = {
        _role_route_label(row, "executor", allow_absent=False)
        for row in materialized
    }
    if len(writer_routes) > 1 or len(executor_routes) > 1:
        writer_labels = sorted(writer_routes) or ["no-writer"]
        labels = sorted(
            f"{writer} → {executor}"
            for writer in writer_labels
            for executor in executor_routes
        )
        raise ValueError(
            f"{context} refuses to pool model routes {labels}; analyze them "
            "separately or group by 'target_pair'"
        )
    if not materialized:
        return None
    writer = next(iter(writer_routes), "no-writer")
    executor = next(iter(executor_routes))
    return writer, executor


def require_single_model_route_per_group(
    rows: Iterable[Mapping[str, Any]],
    by: Iterable[str],
    *,
    context: str = "analysis",
) -> None:
    """Reject route pooling within every analysis group induced by ``by``."""

    keys = tuple(by)
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(analysis_value(row, key) for key in keys)].append(row)
    for key, group in grouped.items():
        label = dict(zip(keys, key))
        require_single_model_route(group, context=f"{context} group {label}")


def group_by(rows: Iterable[dict], *keys: str) -> dict[tuple, list[dict]]:
    materialized = list(rows)
    out: dict[tuple, list[dict]] = defaultdict(list)
    for row in materialized:
        out[tuple(analysis_value(row, key) for key in keys)].append(row)
    require_single_memory_implementation_per_group(
        materialized,
        keys,
        context="group_by",
    )
    require_single_model_route_per_group(materialized, keys, context="group_by")
    return dict(out)


def outcome_fraction(
    rows: Iterable[Mapping[str, Any]],
    field: str,
    *,
    denominator_field: str | None = None,
    denominator_value: Any = True,
) -> tuple[int, int]:
    """Count a boolean outcome without dropping invalid or no-action trials."""

    materialized = list(rows)
    require_single_memory_implementation(
        materialized,
        context=f"outcome_fraction({field})",
    )
    require_single_model_route(
        materialized,
        context=f"outcome_fraction({field})",
    )
    eligible = [
        row
        for row in materialized
        if denominator_field is None
        or analysis_value(row, denominator_field) == denominator_value
    ]
    return (
        sum(1 for row in eligible if analysis_value(row, field) is True),
        len(eligible),
    )


def outcome_rate(
    rows: Iterable[Mapping[str, Any]],
    field: str,
    *,
    denominator_field: str | None = None,
    denominator_value: Any = True,
) -> float | None:
    """Return an all-trial or explicitly conditioned behavioral rate."""

    numerator, denominator = outcome_fraction(
        rows,
        field,
        denominator_field=denominator_field,
        denominator_value=denominator_value,
    )
    return numerator / denominator if denominator else None


def rate(
    rows: list[dict],
    field: str = "compliant",
    parseable_field: str = "parseable",
) -> float | None:
    """Fraction of parseable rows where ``field`` is true."""

    require_single_memory_implementation(rows, context=f"rate({field})")
    require_single_model_route(rows, context=f"rate({field})")
    ok = [row for row in rows if row.get(parseable_field, True)]
    if not ok:
        return None
    return sum(1 for row in ok if row.get(field)) / len(ok)


def _role_route_label(
    row: Mapping[str, Any],
    role: str,
    *,
    allow_absent: bool,
) -> str:
    target = analysis_value(row, f"{role}_target")
    provider = analysis_value(row, f"{role}_provider")
    resolved = analysis_value(row, f"{role}_resolved_model")
    requested = analysis_value(row, f"{role}_requested_model")
    response = analysis_value(row, f"{role}_response_model")
    if all(
        value is None
        for value in (
            target,
            provider,
            resolved,
            requested,
            response,
        )
    ):
        return "no-writer" if allow_absent else "<unrecorded-executor>"
    route = target or "<unrecorded-target>"
    if requested is not None and resolved is not None and requested != resolved:
        model = f"{requested}=>{resolved}"
    else:
        model = resolved or requested or response or "<unrecorded-model>"
    return f"{provider or '<unrecorded-provider>'}:{route}:{model}"


def _dotted_value(row: Mapping[str, Any], key: str) -> Any:
    if "." not in key:
        return None
    value: Any = row
    for component in key.split("."):
        if not isinstance(value, Mapping) or component not in value:
            return None
        value = value[component]
    return value


def _provenance_value(
    row: Mapping[str, Any],
    role: str,
    field: str,
    *,
    default: Any,
) -> Any:
    provenance = row.get(role)
    if isinstance(provenance, Mapping):
        candidates = (
            ("response_model", "resolved_model", "requested_model")
            if field == "model"
            else (field,)
        )
        for candidate in candidates:
            value = provenance.get(candidate)
            if value is not None:
                return value
    return default


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(
        p * (1 - p) / n + z * z / (4 * n * n)
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def _resolve_run(
    source: Path,
) -> tuple[Path, Path | None, dict[str, Any] | None]:
    return _resolve_artifact(source, "trials")


def _resolve_artifact(
    source: Path,
    kind: str,
) -> tuple[Path, Path | None, dict[str, Any] | None]:
    if source.is_dir():
        manifest_path = source / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"run directory has no manifest.json: {source}")
        manifest = _load_manifest(manifest_path)
        artifact_path = _artifact_path(manifest, manifest_path.parent, kind)
        return artifact_path, manifest_path, manifest
    if source.name == "manifest.json":
        if not source.is_file():
            raise FileNotFoundError(source)
        manifest = _load_manifest(source)
        artifact_path = _artifact_path(manifest, source.parent, kind)
        return artifact_path, source, manifest
    if not source.is_file():
        raise FileNotFoundError(source)
    manifest_path = source.parent / "manifest.json"
    if not manifest_path.is_file():
        return source, None, None
    manifest = _load_manifest(manifest_path)
    declared_artifact = _artifact_path(manifest, source.parent, kind)
    if source.resolve() != declared_artifact.resolve():
        raise ValueError(
            f"{source} is not the {kind} artifact declared by {manifest_path}"
        )
    return source, manifest_path, manifest


def _load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        manifest = json.load(file)
    if not isinstance(manifest, dict):
        raise ValueError(f"manifest must be a JSON object: {path}")
    return manifest


def _artifact_path(manifest: Mapping[str, Any], directory: Path, kind: str) -> Path:
    files = manifest.get("files")
    entry = files.get(kind) if isinstance(files, Mapping) else None
    if isinstance(entry, str):
        relative = entry
    elif isinstance(entry, Mapping):
        relative = entry.get("path") or entry.get("file") or entry.get("name")
    else:
        artifacts = manifest.get("artifacts")
        artifact = artifacts.get(kind) if isinstance(artifacts, Mapping) else None
        if isinstance(artifact, str):
            relative = artifact
        elif isinstance(artifact, Mapping):
            relative = (
                artifact.get("path") or artifact.get("file") or artifact.get("name")
            )
        else:
            relative = None
    relative = relative or f"{kind}.jsonl"
    path = directory / str(relative)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _artifact_kind(manifest: Mapping[str, Any], source: Path) -> str | None:
    for container_key in ("files", "artifacts"):
        container = manifest.get(container_key)
        if not isinstance(container, Mapping):
            continue
        for kind, entry in container.items():
            if isinstance(entry, str):
                relative = entry
            elif isinstance(entry, Mapping):
                relative = entry.get("path") or entry.get("file") or entry.get("name")
            else:
                continue
            if relative and Path(str(relative)).name == source.name:
                return str(kind)
    return "trials" if source.name == "trials.jsonl" else None


def _manifest_domain(manifest: Mapping[str, Any] | None) -> str | None:
    if manifest is None:
        return None
    value = manifest.get("domain_id") or manifest.get("domain")
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("manifest domain must be a non-empty string")
    return value


def _manifest_trial_schema_version(
    manifest: Mapping[str, Any] | None,
) -> int | None:
    if manifest is None:
        return None
    versions = manifest.get("artifact_schema_versions")
    value = versions.get("trials") if isinstance(versions, Mapping) else None
    if value is None:
        value = manifest.get("trial_schema_version")
    return _coerce_schema_version(value)


def _manifest_artifact_schema_version(
    manifest: Mapping[str, Any] | None,
    kind: str,
) -> int | None:
    if manifest is None:
        return None
    versions = manifest.get("artifact_schema_versions")
    value = versions.get(kind) if isinstance(versions, Mapping) else None
    return _coerce_schema_version(value)


def _manifest_memory_implementation_id(
    manifest: Mapping[str, Any] | None,
) -> str | None:
    if manifest is None:
        return None
    candidates: list[Any] = [manifest.get("memory_implementation_id")]
    for section_name in ("memory", "writer"):
        section = manifest.get(section_name)
        if not isinstance(section, Mapping):
            continue
        candidates.extend(
            (
                section.get("memory_implementation_id"),
                section.get("implementation_id"),
            )
        )
    return _unique_memory_implementation_id(
        candidates,
        artifact_label="manifest",
    )


def _manifest_memory_implementation_hash(
    manifest: Mapping[str, Any] | None,
) -> str | None:
    if manifest is None:
        return None
    candidates: list[Any] = [manifest.get("memory_implementation_hash")]
    for section_name in ("memory", "writer"):
        section = manifest.get(section_name)
        if isinstance(section, Mapping):
            candidates.append(section.get("memory_implementation_hash"))
    return _unique_memory_implementation_hash(
        candidates,
        artifact_label="manifest",
    )


def _coerce_schema_version(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("trial schema version must be an integer")
    try:
        version = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid trial schema version: {value!r}") from exc
    return version


def _declared_artifact_hash(
    manifest: Mapping[str, Any],
    kind: str,
    filename: str,
) -> str | None:
    for container_key in ("files", "artifacts"):
        container = manifest.get(container_key)
        entry = container.get(kind) if isinstance(container, Mapping) else None
        if isinstance(entry, Mapping):
            value = entry.get("sha256")
            if isinstance(value, str):
                return value
    for key in (
        "artifact_sha256",
        "artifacts_sha256",
        "file_sha256",
        "files_sha256",
        "raw_file_sha256",
    ):
        hashes = manifest.get(key)
        if not isinstance(hashes, Mapping):
            continue
        value = hashes.get(kind) or hashes.get(filename)
        if isinstance(value, str):
            return value
        if isinstance(value, Mapping) and isinstance(value.get("sha256"), str):
            return value["sha256"]
    hashes = manifest.get("hashes")
    if isinstance(hashes, Mapping):
        for candidate in (kind, filename):
            value = hashes.get(candidate)
            if isinstance(value, str):
                return value
            if isinstance(value, Mapping) and isinstance(value.get("sha256"), str):
                return value["sha256"]
    return None


def _declared_artifact_rows(
    manifest: Mapping[str, Any],
    kind: str,
) -> int | None:
    for container_key in ("files", "artifacts"):
        container = manifest.get(container_key)
        entry = container.get(kind) if isinstance(container, Mapping) else None
        if not isinstance(entry, Mapping) or "rows" not in entry:
            continue
        value = entry["rows"]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"manifest {kind!r} row count must be non-negative")
        return value
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_v5_outcomes(row: Mapping[str, Any]) -> None:
    required = {
        "request_authorized",
        "decision",
        "requested_action_taken",
        "unauthorized_action_taken",
        "action_mismatch",
    }
    missing = sorted(required - row.keys())
    if missing:
        raise ValueError(f"v5 trial row is missing required fields: {missing}")
    if row["decision"] not in DECISIONS:
        raise ValueError(f"invalid v5 decision: {row['decision']!r}")
    for key in required - {"decision"}:
        if not isinstance(row[key], bool):
            raise ValueError(f"v5 trial field {key!r} must be a boolean")


def _normalize_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("trial metadata must be an object")
    normalized = copy.deepcopy(dict(value))
    if set(normalized) != {"core", "study", "domain"} or not all(
        isinstance(normalized[name], Mapping)
        for name in ("core", "study", "domain")
    ):
        raise ValueError(
            "trial metadata must contain exactly core, study, and domain namespaces"
        )
    return normalized


def _normalize_memory_artifact(
    row: Mapping[str, Any],
    *,
    domain_id: str,
    domain: Any,
    manifest: Mapping[str, Any] | None,
    verify_content_hash: bool,
    source_schema_version: int,
    manifest_memory_implementation_id: str | None,
    manifest_memory_implementation_hash: str | None,
) -> dict[str, Any]:
    row_version = _coerce_schema_version(row.get("schema_version"))
    if row_version is not None and row_version != source_schema_version:
        raise ValueError(
            f"memory row schema version {row_version} does not match manifest "
            f"version {source_schema_version}"
        )
    source_version = row_version or source_schema_version
    if source_version not in SUPPORTED_MEMORY_ARTIFACT_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported memory artifact schema version {source_version}"
        )
    row_domain = row.get("domain_id") or row.get("domain")
    if row_domain is not None and row_domain != domain_id:
        raise ValueError(
            f"memory domain {row_domain!r} does not match run domain {domain_id!r}"
        )

    architecture = row.get("architecture")
    if architecture not in {"free_text", "typed"}:
        raise ValueError(f"unsupported memory architecture: {architecture!r}")
    payload = row.get("payload")
    source_content_hash = row.get("content_hash")
    if not isinstance(source_content_hash, str) or not source_content_hash:
        raise ValueError("memory artifact content_hash must be a non-empty string")
    computed_source_hash = _payload_sha256(payload)
    content_hash_verified = computed_source_hash == source_content_hash
    if verify_content_hash and not content_hash_verified:
        memory_id = row.get("memory_id", "<unknown>")
        raise ValueError(
            f"memory payload hash mismatch for {memory_id}: expected "
            f"{source_content_hash}, got {computed_source_hash}"
        )

    if architecture == "typed":
        if not isinstance(payload, Mapping):
            raise ValueError("typed memory payload must be an object")
        declared_schema_id = row.get("payload_schema_id")
        if declared_schema_id != domain.memory.payload_schema_id:
            raise ValueError(
                f"memory payload schema {declared_schema_id!r} does not match "
                f"domain schema {domain.memory.payload_schema_id!r}"
            )
        normalized_payload = dict(domain.memory.parse_typed(payload))
        payload_schema_id = domain.memory.payload_schema_id
        payload_schema_version = str(
            normalized_payload.get("schema_version", "3")
        )
    else:
        if not isinstance(payload, str):
            raise ValueError("free-text memory payload must be a string")
        normalized_payload = payload
        payload_schema_id = None
        payload_schema_version = None

    required = (
        "memory_id",
        "chain_id",
        "case_id",
        "condition_id",
        "block_index",
        "origin",
        "reference_tokens",
        "reference_tokenizer",
    )
    missing = [key for key in required if key not in row]
    if missing:
        raise ValueError(f"memory artifact is missing fields: {missing}")
    memory_implementation_id = _resolve_memory_implementation_id(
        _row_memory_implementation_id(row),
        (
            manifest_memory_implementation_id
            if row.get("origin") == "writer"
            or _has_writer_provenance(row)
            else None
        ),
        artifact_label=f"memory artifact {row['memory_id']}",
    )
    memory_implementation_hash = _resolve_memory_implementation_hash(
        _row_memory_implementation_hash(row),
        (
            manifest_memory_implementation_hash
            if row.get("origin") == "writer"
            or _has_writer_provenance(row)
            else None
        ),
        artifact_label=f"memory artifact {row['memory_id']}",
    )
    if (memory_implementation_id is None) != (memory_implementation_hash is None):
        raise ValueError(
            f"memory artifact {row['memory_id']} must record both implementation ID and hash"
        )
    framework = row.get("framework", {})
    if not isinstance(framework, Mapping):
        raise ValueError("memory artifact framework must be an object")
    framework_run_ids = row.get("framework_run_ids", ())
    if not isinstance(framework_run_ids, (list, tuple)) or any(
        not isinstance(run_id, str) or not run_id
        for run_id in framework_run_ids
    ):
        raise ValueError("memory artifact framework_run_ids must be strings")
    source_attempt_id = row.get("source_attempt_id")
    if source_attempt_id is not None and (
        not isinstance(source_attempt_id, str) or not source_attempt_id
    ):
        raise ValueError("memory artifact source_attempt_id must be a string")
    manifest_presentation = (
        manifest.get("presentation") if isinstance(manifest, Mapping) else None
    )
    presentation_id = row.get("presentation_id")
    if presentation_id is None and isinstance(manifest_presentation, Mapping):
        presentation_id = manifest_presentation.get("presentation_id")
    if not isinstance(presentation_id, str) or not presentation_id:
        raise ValueError("memory artifact presentation_id must be a non-empty string")
    presentation_hash = row.get("presentation_hash")
    if presentation_hash is None and isinstance(manifest, Mapping):
        presentation_hash = manifest.get("presentation_hash")
    if presentation_hash is not None and (
        not isinstance(presentation_hash, str) or not presentation_hash
    ):
        raise ValueError("memory artifact presentation_hash must be a string")
    return {
        "schema_version": 4,
        "memory_id": row["memory_id"],
        "parent_memory_id": row.get("parent_memory_id"),
        "chain_id": row["chain_id"],
        "domain_id": domain_id,
        "case_id": row["case_id"],
        "condition_id": row["condition_id"],
        "block_index": row["block_index"],
        "writer_run_id": row.get("writer_run_id"),
        "writer_seed": row.get("writer_seed"),
        "writer": _normalize_memory_writer(row, manifest),
        "architecture": architecture,
        "origin": row["origin"],
        "memory_implementation_id": memory_implementation_id,
        "memory_implementation_hash": memory_implementation_hash,
        "profile_id": row.get("profile_id"),
        "source_attempt_id": source_attempt_id,
        "framework_run_ids": list(framework_run_ids),
        "framework": copy.deepcopy(dict(framework)),
        "presentation_id": presentation_id,
        "presentation_hash": presentation_hash,
        "payload_schema_id": payload_schema_id,
        "payload_schema_version": payload_schema_version,
        "payload": normalized_payload,
        "reference_tokens": row["reference_tokens"],
        "reference_tokenizer": row["reference_tokenizer"],
        "content_hash": source_content_hash,
        "normalized_content_hash": _payload_sha256(normalized_payload),
        "content_hash_verified": content_hash_verified,
    }


def _row_memory_implementation_id(row: Mapping[str, Any]) -> str | None:
    candidates: list[Any] = [row.get("memory_implementation_id")]
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        candidates.append(metadata.get("memory_implementation_id"))
        core = metadata.get("core")
        if isinstance(core, Mapping):
            candidates.append(core.get("memory_implementation_id"))
    return _unique_memory_implementation_id(
        candidates,
        artifact_label="row",
    )


def _row_memory_implementation_hash(row: Mapping[str, Any]) -> str | None:
    candidates: list[Any] = [row.get("memory_implementation_hash")]
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        core = metadata.get("core")
        if isinstance(core, Mapping):
            candidates.append(core.get("memory_implementation_hash"))
    return _unique_memory_implementation_hash(
        candidates,
        artifact_label="row",
    )


def _has_writer_provenance(row: Mapping[str, Any]) -> bool:
    writer = row.get("writer")
    if isinstance(writer, Mapping):
        return any(value is not None for value in writer.values())
    if writer is not None:
        return True
    return False


def _resolve_memory_implementation_id(
    row_value: str | None,
    manifest_value: str | None,
    *,
    artifact_label: str,
) -> str | None:
    value = _unique_memory_implementation_id(
        (row_value, manifest_value),
        artifact_label=artifact_label,
    )
    if value is not None and value != LANGMEM_MEMORY_IMPLEMENTATION_ID:
        raise ValueError(
            f"{artifact_label} uses unsupported memory implementation {value!r}"
        )
    return value


def _resolve_memory_implementation_hash(
    row_value: str | None,
    manifest_value: str | None,
    *,
    artifact_label: str,
) -> str | None:
    return _unique_memory_implementation_hash(
        (row_value, manifest_value),
        artifact_label=artifact_label,
    )


def _unique_memory_implementation_id(
    values: Iterable[Any],
    *,
    artifact_label: str,
) -> str | None:
    normalized: set[str] = set()
    for value in values:
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{artifact_label} memory_implementation_id must be a "
                "non-empty string"
            )
        normalized.add(value)
    if len(normalized) > 1:
        raise ValueError(
            f"{artifact_label} has conflicting memory implementations: "
            f"{sorted(normalized)}"
        )
    return next(iter(normalized), None)


def _unique_memory_implementation_hash(
    values: Iterable[Any],
    *,
    artifact_label: str,
) -> str | None:
    normalized: set[str] = set()
    for value in values:
        if value is None:
            continue
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise ValueError(
                f"{artifact_label} memory_implementation_hash must be lowercase sha256"
            )
        normalized.add(value)
    if len(normalized) > 1:
        raise ValueError(
            f"{artifact_label} has conflicting memory implementation hashes: "
            f"{sorted(normalized)}"
        )
    return next(iter(normalized), None)


def _normalize_memory_writer(
    row: Mapping[str, Any],
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    del manifest
    writer = row.get("writer")
    if isinstance(writer, Mapping):
        effective_parameters = writer.get("effective_parameters", {})
        if not isinstance(effective_parameters, Mapping):
            raise ValueError(
                "memory artifact writer effective_parameters must be an object"
            )
        return {
            "target_id": writer.get("target_id"),
            "provider": writer.get("provider"),
            "requested_model": writer.get("requested_model"),
            "resolved_model": writer.get("resolved_model"),
            "response_model": writer.get("response_model"),
            "effective_parameters": copy.deepcopy(
                dict(effective_parameters)
            ),
        }
    if "writer" in row:
        if writer is None:
            return None
        raise ValueError("memory artifact writer must be an object or null")
    raise ValueError("memory artifact must declare writer provenance")


def _payload_sha256(payload: Any) -> str:
    if isinstance(payload, str):
        serialized = payload
    elif isinstance(payload, (Mapping, list)):
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    else:
        raise ValueError(
            f"memory payload must be a string or JSON object, got "
            f"{type(payload).__name__}"
        )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
