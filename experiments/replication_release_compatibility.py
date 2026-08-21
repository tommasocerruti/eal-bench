from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


COMPATIBILITY_SCHEMA = "phase2_completed_release_replication_v1"


def authorize_completed_release_replication(
    options: Mapping[str, Any],
    domain: Any,
    profile: Any,
) -> dict[str, Any] | None:
    """Authorize one exact precommitted route against a completed release."""

    raw_precommit = str(options.get("replication_precommit") or "").strip()
    route_id = str(options.get("replication_route_id") or "").strip()
    if not raw_precommit and not route_id:
        return None
    if not raw_precommit or not route_id:
        raise ValueError(
            "--replication-precommit and --replication-route-id must be used together"
        )
    if domain.domain_id != "finance" or profile.study_id not in {
        "controls",
        "writer",
        "pressure",
    }:
        raise ValueError(
            "completed-release replication compatibility is limited to precommitted "
            "Finance controls, writer, and pressure routes"
        )

    precommit_path = Path(raw_precommit).expanduser().resolve()
    plan = json.loads(precommit_path.read_text(encoding="utf-8"))
    compatibility = plan.get("completed_release_replication_compatibility")
    if not isinstance(compatibility, dict):
        raise ValueError("Phase 2 precommit has no completed-release compatibility record")
    expected_identity = {
        "schema_version": COMPATIBILITY_SCHEMA,
        "enabled": True,
        "domain_id": "finance",
        "accepted_lifecycle_status": "approved_and_completed",
        "ordinary_run_behavior_unchanged": True,
        "provider_visible_behavior_unchanged": True,
    }
    for key, expected in expected_identity.items():
        if compatibility.get(key) != expected:
            raise ValueError(
                f"Phase 2 compatibility {key} mismatch: "
                f"{compatibility.get(key)!r} != {expected!r}"
            )

    expected_path = Path(
        str(compatibility.get("precommit_path") or "")
    ).expanduser().resolve()
    if precommit_path != expected_path:
        raise ValueError("completed-release compatibility precommit path differs")

    from experiments.phase2_precommit import build_commands, validate

    validate(precommit_path)
    command = next(
        (
            item
            for item in build_commands(plan)
            if item["route_id"] == route_id
        ),
        None,
    )
    if command is None:
        raise ValueError(f"route is not in the Phase 2 precommit: {route_id}")
    expected_argv = list(
        command["validate" if bool(options.get("validate_only")) else "live"][5:]
    )
    actual_argv = list(options.get("_raw_argv") or ())
    _validate_exact_command(
        actual_argv,
        expected_argv,
        command=command,
        commands=build_commands(plan),
    )

    scientific_hashes = compatibility.get("scientific_hash_requirements")
    if not isinstance(scientific_hashes, dict) or not scientific_hashes:
        raise ValueError("completed-release compatibility has no scientific hashes")
    for raw_path, expected_hash in scientific_hashes.items():
        path = Path(raw_path)
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(
                f"completed-release scientific hash differs for {raw_path}: "
                f"{actual_hash} != {expected_hash}"
            )

    revision = compatibility.get("new_execution_revision")
    if not isinstance(revision, dict):
        raise ValueError("completed-release execution revision record is missing")
    head = _git("rev-parse", "HEAD")
    expected_head = _git("rev-parse", str(revision.get("git_ref") or ""))
    if revision.get("must_resolve_to_head") is not True or head != expected_head:
        raise ValueError("completed-release execution ref does not resolve to HEAD")
    if revision.get("required_clean_tracked_worktree") is not True:
        raise ValueError(
            "completed-release execution requires a clean tracked worktree"
        )

    release_path = Path("domains/finance/release.json")
    release = json.loads(release_path.read_text(encoding="utf-8"))
    pricing_status = (
        release.get("run_plan", {}).get("pricing_estimate", {}).get("status")
    )
    route_authorized = (
        release.get("run_plan", {})
        .get("route_authorizations", {})
        .get(profile.study_id)
    )
    if (
        release.get("freeze_status") != "claim_frozen"
        or release.get("review", {}).get("status")
        not in {"approved", "approved_with_owner_waiver"}
        or pricing_status != compatibility["accepted_lifecycle_status"]
        or route_authorized is not True
    ):
        raise ValueError(
            "completed-release compatibility requires the exact frozen, reviewed, "
            "route-authorized Finance release"
        )

    cases = tuple(domain.corpus.load_cases(str(options["corpus_version"])))
    release_check = domain.offline_checks.get("release_manifest")
    if release_check is None:
        raise ValueError("Finance domain has no frozen release validator")
    release_validation = release_check(domain, cases, options)
    if release_validation.get("status") != "passed":
        raise ValueError("Finance frozen release validation did not pass")

    return {
        "schema_version": COMPATIBILITY_SCHEMA,
        "precommit_path": str(precommit_path),
        "precommit_sha256": hashlib.sha256(precommit_path.read_bytes()).hexdigest(),
        "route_id": route_id,
        "accepted_lifecycle_status": pricing_status,
        "release_manifest_sha256": hashlib.sha256(release_path.read_bytes()).hexdigest(),
        "frozen_scientific_base_revision": compatibility[
            "frozen_scientific_base_revision"
        ],
        "compatibility_patch_base_revision": compatibility[
            "compatibility_patch_base_revision"
        ],
        "execution_revision": head,
        "execution_revision_ref": revision["git_ref"],
        "provider_visible_behavior_unchanged": True,
    }


def compatibility_validation_options(
    options: Mapping[str, Any],
) -> Mapping[str, Any]:
    if options.get("_completed_release_replication_compatibility") is None:
        return options
    return {**options, "validate_only": True}


def is_completed_release_replication(options: Mapping[str, Any]) -> bool:
    return options.get("_completed_release_replication_compatibility") is not None


def completed_release_execution_options(
    options: Mapping[str, Any],
    plan: Any,
) -> Mapping[str, Any]:
    if not is_completed_release_replication(options) or plan.study_id != "pressure":
        return options
    frozen_targets = []
    for job in plan.jobs:
        if (
            job.executor_target_id is None
            or job.executor_run_id is None
            or job.executor_seed is None
        ):
            raise ValueError(
                "completed-release pressure compatibility requires a fully "
                "frozen executor route on every job"
            )
        if job.executor_target_id not in frozen_targets:
            frozen_targets.append(job.executor_target_id)
    if not frozen_targets:
        raise ValueError("completed-release pressure plan has no frozen executor jobs")
    return {**options, "executor_targets": tuple(frozen_targets)}


def _validate_exact_command(
    actual: list[str],
    expected: list[str],
    *,
    command: Mapping[str, Any],
    commands: Sequence[Mapping[str, Any]],
) -> None:
    expected_source = _flag_value(expected, "--source-run")
    if expected_source and expected_source.startswith("{run_dir:"):
        actual_source = _flag_value(actual, "--source-run")
        if not actual_source:
            raise ValueError("source-bound replication route has no source run")
        dependency_id = str(command.get("depends_on") or "")
        dependency = next(
            (item for item in commands if item["route_id"] == dependency_id),
            None,
        )
        if dependency is None:
            raise ValueError("source-bound replication dependency is not precommitted")
        expected_tag = _flag_value(list(dependency["live"]), "--tag")
        source_path = Path(actual_source).expanduser().resolve()
        manifest_path = source_path / "manifest.json"
        if not manifest_path.is_file() or not source_path.name.endswith(
            f"__{expected_tag}"
        ):
            raise ValueError("pressure source is not the exact precommitted writer run")
        normalized = list(actual)
        normalized[normalized.index("--source-run") + 1] = expected_source
        actual = normalized
    if actual != expected:
        raise ValueError(
            "replication command differs from the exact Phase 2 precommit:\n"
            f"actual={actual!r}\nexpected={expected!r}"
        )


def _flag_value(args: list[str], flag: str) -> str:
    if flag not in args:
        return ""
    index = args.index(flag)
    if index + 1 >= len(args):
        raise ValueError(f"missing value for {flag}")
    return args[index + 1]


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
