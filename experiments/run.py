#!/usr/bin/env python3
"""Run the domain-neutral authorization-memory benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from eal_bench.llm import load_config

from domains import get_domain, list_domains
from experiments.authorization_memory.evaluation_awareness import (
    AWARENESS_STUDY_ID,
    shared_study_profile,
    validate_protocol_fixture,
)
from experiments.authorization_memory.evaluation_awareness_fixture import (
    validate_core_gate_fixture,
    validate_smoke_bundles,
)
from experiments.authorization_memory.challenges import (
    validate_challenge_construction,
)
from experiments.authorization_memory.conformance import (
    validate_domain_conformance,
)
from experiments.authorization_memory.leakage import (
    validate_model_visible_leakage,
)
from experiments.authorization_memory.persistence import content_hash, file_hash
from experiments.authorization_memory.resume import (
    prepare_provider_error_resume,
    resume_executor_only_study_plan,
    resume_writer_checkpoint_study_plan,
    validate_executor_only_resume,
    validate_writer_checkpoint_resume,
    validate_writer_checkpoint_resume_fixture,
)
from experiments.authorization_memory.study_engine import (
    run_study_plan,
    validate_study_plan,
)
from experiments.authorization_memory.validation import (
    validate_langmem_writer_behaviors,
    validate_shared_domain_boundaries,
)
from experiments.replication_release_compatibility import (
    authorize_completed_release_replication,
    compatibility_validation_options,
    is_completed_release_replication,
)


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domain",
        default="procurement",
        choices=list_domains(),
    )
    parser.add_argument(
        "--study",
        default="controls",
        help="behavioral route or validity analysis; use --list-studies",
    )
    parser.add_argument("--list-domains", action="store_true")
    parser.add_argument("--list-corpus-versions", action="store_true")
    parser.add_argument("--list-studies", action="store_true")
    parser.add_argument("--list-presentations", action="store_true")
    parser.add_argument("--list-targets", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument(
        "--all-domains",
        action="store_true",
        help="with --validate-only, validate every registered domain",
    )
    parser.add_argument("--corpus-version", default="")
    parser.add_argument(
        "--presentation-version",
        default="",
        help="domain presentation profile; defaults to the domain's current profile",
    )
    parser.add_argument("--case-ids", default="")
    parser.add_argument(
        "--writer-architecture",
        choices=("all", "typed", "free_text"),
        default="all",
    )
    parser.add_argument(
        "--writer-strategy",
        choices=("all", "one_shot", "incremental"),
        default="all",
    )
    parser.add_argument("--writer-task", default="writer")
    parser.add_argument("--executor-task", default="executor")
    parser.add_argument("--reviewer-task", default="memory_selector")
    parser.add_argument(
        "--reviewer-target",
        default="",
        help="independent selector target for writer_ttc review-only reuse",
    )
    parser.add_argument(
        "--writer-targets",
        default="",
        help="comma-separated provider-aware model target IDs",
    )
    parser.add_argument(
        "--executor-targets",
        default="",
        help="comma-separated provider-aware model target IDs",
    )
    parser.add_argument("--writer-runs", type=int, default=1)
    parser.add_argument(
        "--ttc-review-only",
        action="store_true",
        help="reuse a completed writer_ttc pool without generating candidates",
    )
    parser.add_argument(
        "--ttc-oracle-only",
        action="store_true",
        help=(
            "reuse a completed writer_ttc pool and execute the deterministic "
            "typed oracle-best candidates without writer or reviewer calls"
        ),
    )
    parser.add_argument("--executor-runs", type=int, default=1)
    parser.add_argument(
        "--writer-max-attempts",
        type=int,
        choices=(1, 2),
        default=2,
    )
    parser.add_argument(
        "--writer-route-timeout-seconds",
        type=int,
        default=3600,
        help=(
            "writer-route wall-time limit; values above the canonical "
            "3600-second default are recorded as runtime overrides"
        ),
    )
    parser.add_argument(
        "--capacity-tier",
        choices=("primary", "tight"),
        default="primary",
    )
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument(
        "--estimated-cost-usd",
        type=float,
        default=None,
        help="documented upper-bound estimate required before a live paid route",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="random seed; defaults to the selected domain release seed",
    )
    parser.add_argument(
        "--source-run",
        action="append",
        default=[],
        help=(
            "source run directory; repeat only for studies that explicitly "
            "support multiple frozen sources"
        ),
    )
    parser.add_argument(
        "--intervention-stage",
        choices=("writer", "executor"),
        default="",
    )
    parser.add_argument(
        "--cue-level",
        choices=("l0", "l1", "l2"),
        default="",
    )
    parser.add_argument(
        "--pressure-variant",
        default="",
        help="domain-registered pressure variant; defaults to the release profile",
    )
    parser.add_argument(
        "--resume-run",
        default="",
        help=(
            "continue missing calls from an executor-only run or a frozen "
            "post-writer executor checkpoint"
        ),
    )
    parser.add_argument(
        "--retry-provider-errors",
        action="store_true",
        help="derive a continuation that retries only provider-error calls",
    )
    parser.add_argument(
        "--expected-missing-calls",
        type=int,
        default=None,
        help="fail before execution unless an interrupted run has this many missing calls",
    )
    parser.add_argument("--reference-run", default="")
    parser.add_argument("--match-manifest", default="")
    parser.add_argument("--memory-annotations", default="")
    parser.add_argument(
        "--awareness-protocol",
        default="",
        help="domain-registered awareness protocol; defaults to the first registered protocol",
    )
    parser.add_argument("--tag", default=None)
    parser.add_argument(
        "--replication-precommit",
        default="",
        help="explicit precommit for a narrowly authorized completed-release rerun",
    )
    parser.add_argument(
        "--replication-route-id",
        default="",
        help="exact route ID in the completed-release replication precommit",
    )
    return parser


def _domain_listing() -> list[dict[str, Any]]:
    return [
        {
            "domain_id": domain_id,
            "adapter_version": (domain := get_domain(domain_id)).adapter_version,
            "maturity": domain.maturity,
            "default_corpus": domain.corpus.default_version,
            "corpus_versions": list(domain.corpus_versions),
            "default_presentation": domain.default_presentation_id,
            "presentations": list(domain.presentation_ids),
            "studies": [
                *domain.study_ids,
                *((AWARENESS_STUDY_ID,) if domain.awareness_protocols else ()),
            ],
            "awareness_protocols": [
                {
                    "protocol_id": protocol.protocol_id,
                    "description": protocol.description,
                    "core_protocol": protocol.core_protocol,
                    "expected_contexts": protocol.expected_contexts,
                    "expected_jobs": protocol.expected_jobs,
                    "benchmark_corpus_version": (
                        protocol.benchmark_corpus_version
                    ),
                    "presentation_id": protocol.presentation_id,
                }
                for protocol in domain.awareness_protocols.values()
            ],
        }
        for domain_id in list_domains()
    ]


def _target_listing() -> list[dict[str, Any]]:
    config = load_config()
    return [
        {
            "target_id": target_id,
            "provider": target.provider,
            "requested_model": target.requested_model,
            "resolved_model": target.model,
            "capabilities": sorted(target.capabilities),
            "request_parameters": dict(target.request_parameters),
            "max_concurrency": target.max_concurrency,
        }
        for target_id, target in sorted(config.model_targets.items())
    ]


def _corpus_listing(domain_id: str) -> dict[str, Any]:
    domain = get_domain(domain_id)
    return {
        "domain_id": domain_id,
        "default_corpus": domain.corpus.default_version,
        "corpus_versions": list(domain.corpus_versions),
    }


def _study_listing(domain_id: str) -> dict[str, Any]:
    domain = get_domain(domain_id)
    profiles = [
        *domain.studies.values(),
        *(
            (shared_study_profile(domain),)
            if domain.awareness_protocols
            else ()
        ),
    ]
    return {
        "domain_id": domain_id,
        "behavioral_routes": [
            {
                "study_id": profile.study_id,
                "description": profile.description,
                "required_capabilities": list(profile.required_capabilities),
            }
            for profile in profiles
            if profile.category == "behavioral"
        ],
        "validity_analyses": [
            {
                "study_id": profile.study_id,
                "description": profile.description,
                "required_capabilities": list(profile.required_capabilities),
            }
            for profile in profiles
            if profile.category == "validity"
        ],
    }


def _presentation_listing(domain_id: str) -> dict[str, Any]:
    domain = get_domain(domain_id)
    return {
        "domain_id": domain_id,
        "default_presentation": domain.default_presentation_id,
        "presentations": [
            profile.to_dict() for profile in domain.presentations.values()
        ],
    }


def _format_study_listing(domain_id: str) -> str:
    listing = _study_listing(domain_id)
    lines = ["Behavioral routes:"]
    lines.extend(
        f"  {row['study_id']}"
        for row in listing["behavioral_routes"]
    )
    lines.extend(("", "Validity analyses:"))
    lines.extend(
        f"  {row['study_id']}"
        for row in listing["validity_analyses"]
    )
    return "\n".join(lines)


def _default_target(task_name: str) -> str:
    task = load_config().task(task_name)
    return task.default_target


def _study_profile(domain: Any, study_id: str) -> Any:
    if study_id == AWARENESS_STUDY_ID:
        return shared_study_profile(domain)
    return domain.get_study(study_id)


def _validate(args: argparse.Namespace) -> None:
    domain_ids = list_domains() if args.all_domains else (args.domain,)
    results = []
    for domain_id in domain_ids:
        if args.study == AWARENESS_STUDY_ID and args.presentation_version:
            raise ValueError(
                "--presentation-version applies to behavioral source runs, not the "
                "evaluation-awareness child study"
            )
        domain = get_domain(domain_id)
        profile = _study_profile(domain, args.study)
        options = _route_options(args, domain, profile)
        requested_cases = args.case_ids or ",".join(
            options.get("_source_case_ids", ())
        )
        cases = _selected_cases(
            domain,
            str(options["corpus_version"]),
            requested_cases,
        )
        if profile.offline_validator is not None:
            profile.validate_offline(domain, cases, options)
            result = {
                "status": "passed",
                "domain_id": domain_id,
                "study_id": profile.study_id,
            }
        elif profile.builder is not None:
            plan = profile.build_jobs(domain, cases, options)
            result = validate_study_plan(
                domain, cases, plan, options, config=load_config()
            )
            if plan.writer_chains:
                result["writer_checkpoint_resume_fixture"] = (
                    validate_writer_checkpoint_resume_fixture(
                        domain,
                        cases,
                        plan,
                        options,
                        config=load_config(),
                    )
                )
            if args.retry_provider_errors:
                raise ValueError("--retry-provider-errors is a live continuation operation")
            if args.resume_run:
                result["resume"] = (
                    validate_writer_checkpoint_resume(
                        domain,
                        cases,
                        plan,
                        options,
                        config=load_config(),
                    )
                    if plan.writer_chains
                    else validate_executor_only_resume(
                        domain,
                        cases,
                        plan,
                        options,
                        config=load_config(),
                    )
                ).to_dict()
            result["domain_id"] = domain_id
            if profile.study_id == "writer":
                result["langmem_writer_behaviors"] = (
                    validate_langmem_writer_behaviors(
                        domain,
                        corpus_version=str(options["corpus_version"]),
                    )
                )
        else:
            raise NotImplementedError(
                f"study {args.study!r} has no offline validator or plan builder"
            )
        if profile.category == "behavioral":
            presentation = domain.get_presentation(
                str(options.get("presentation_version") or "") or None
            )
            result.update(
                {
                    "source_files": {
                        str(path): file_hash(path)
                        for path in domain.corpus.source_files(
                            str(options["corpus_version"])
                        )
                    },
                    "corpus_provenance": dict(
                        domain.corpus.provenance(
                            str(options["corpus_version"])
                        )
                    ),
                    "presentation": presentation.to_dict(),
                    "presentation_hash": content_hash(
                        presentation.to_dict()
                    ),
                    "model_visible_leakage": (
                        validate_model_visible_leakage(
                            domain,
                            cases,
                            presentation,
                        )
                    ),
                    "conformance": validate_domain_conformance(
                        domain,
                        cases,
                    ),
                    "challenges": validate_challenge_construction(
                        domain,
                        tuple(cases),
                    ),
                    "domain_offline_checks": {
                        check_id: check(domain, cases, options)
                        for check_id, check in domain.offline_checks.items()
                    },
                }
            )
        results.append(result)
    if len(results) == 1 and not args.all_domains:
        print(json.dumps(results[0], indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "status": "passed",
                    "domains": results,
                    "shared_boundary_validation": (
                        validate_shared_domain_boundaries()
                    ),
                    "validity_fixtures": {
                        "protocol": validate_protocol_fixture(),
                        "core_gates": validate_core_gate_fixture(),
                        "smoke_bundles": validate_smoke_bundles(),
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )


def _route_options(
    args: argparse.Namespace,
    domain: Any,
    profile: Any,
) -> dict[str, Any]:
    provided = set(getattr(args, "_provided_flags", ()))
    if profile.study_id != "writer_ttc":
        forbidden_ttc = sorted(
            provided
            & {
                "--reviewer-task",
                "--reviewer-target",
                "--ttc-review-only",
                "--ttc-oracle-only",
            }
        )
        if forbidden_ttc:
            raise ValueError(
                "TTC review options require --study writer_ttc: "
                + ", ".join(forbidden_ttc)
            )
    source_runs = tuple(
        str(value).strip()
        for value in (args.source_run or ())
        if str(value).strip()
    )
    if profile.study_id != "evaluation_cue" and len(source_runs) > 1:
        raise ValueError(
            "repeatable --source-run is supported only by --study evaluation_cue"
        )
    if profile.study_id != "evaluation_cue":
        forbidden_cue = sorted(
            provided & {"--intervention-stage", "--cue-level"}
        )
        if forbidden_cue:
            raise ValueError(
                "evaluation-cue options require --study evaluation_cue: "
                + ", ".join(forbidden_cue)
            )
    if (
        profile.study_id
        not in {
            "writer",
            "writer_ttc",
            "evaluation_cue",
            "capacity_nonbinding_writer",
            "capacity_writer_visible_nonbinding",
        }
        and "--writer-route-timeout-seconds" in provided
    ):
        raise ValueError(
            "--writer-route-timeout-seconds applies only to writer studies"
        )
    pressure_source = _pressure_source_manifest(args, profile)
    corpus_version = args.corpus_version or (
        str(pressure_source.get("corpus_version") or "")
        if pressure_source is not None
        else ""
    ) or domain.corpus.default_version
    options = {
        **vars(args),
        "source_run": source_runs[0] if source_runs else "",
        "source_runs": source_runs,
        "corpus_version": corpus_version,
        "seed": args.seed if args.seed is not None else domain.canonical_seed,
        "command": "python -m experiments.run " + " ".join(sys.argv[1:]),
    }
    if profile.category == "behavioral":
        source_presentation = (
            pressure_source.get("presentation")
            if pressure_source is not None
            else None
        )
        source_presentation_id = (
            str(source_presentation.get("presentation_id") or "")
            if isinstance(source_presentation, dict)
            else ""
        )
        options["presentation_version"] = domain.get_presentation(
            args.presentation_version
            or source_presentation_id
            or domain.default_presentation_id
        ).presentation_id
    if pressure_source is not None:
        source_case_ids = pressure_source.get("case_ids")
        if not isinstance(source_case_ids, list) or not all(
            isinstance(case_id, str) and case_id
            for case_id in source_case_ids
        ):
            raise ValueError(
                "pressure source manifest has invalid case_ids"
            )
        options["_source_case_ids"] = tuple(source_case_ids)
    if profile.study_id == "controls":
        options["writer_targets"] = ()
        options["executor_targets"] = _csv(args.executor_targets) or (
            _default_target(args.executor_task),
        )
    elif profile.study_id in {"writer", "writer_ttc"}:
        options["writer_targets"] = _csv(args.writer_targets) or (
            _default_target(args.writer_task),
        )
        options["executor_targets"] = _csv(args.executor_targets) or (
            _default_target(args.executor_task),
        )
        if profile.study_id == "writer_ttc":
            options["reviewer_target"] = (
                args.reviewer_target or options["writer_targets"][0]
            )
            options["reviewer_seed"] = (
                int(options["seed"]) + 10_000 + int(args.writer_runs)
            )
            options["reviewer_max_tokens"] = (
                1536 if int(args.writer_runs) == 8 else 768
            )
    elif profile.study_id in {
        "capacity_nonbinding_writer",
        "capacity_writer_visible_nonbinding",
    }:
        options["writer_targets"] = _csv(args.writer_targets)
        options["executor_targets"] = ()
    elif profile.study_id in {
        "capacity_nonbinding_replay",
        "capacity_writer_visible_nonbinding_replay",
    }:
        options["writer_targets"] = ()
        options["executor_targets"] = _csv(args.executor_targets) or (
            "gptoss_baseten",
        )
    elif profile.study_id == "evaluation_cue":
        if args.intervention_stage == "writer":
            options["writer_targets"] = _csv(args.writer_targets) or (
                _default_target(args.writer_task),
            )
            options["executor_targets"] = _csv(args.executor_targets) or (
                _default_target(args.executor_task),
            )
        else:
            options["writer_targets"] = ()
            options["executor_targets"] = _csv(args.executor_targets) or (
                "gptoss_baseten",
                "deepseek_baseten",
            )
    elif profile.study_id == "pressure":
        forbidden = sorted(
            provided
            & {
                "--executor-task",
                "--executor-runs",
                "--seed",
                "--writer-task",
                "--writer-runs",
                "--writer-max-attempts",
                "--writer-route-timeout-seconds",
                "--writer-architecture",
                "--writer-strategy",
            }
        )
        if forbidden:
            raise ValueError(
                "pressure inherits its frozen writer/executor route and does "
                "not accept: " + ", ".join(forbidden)
            )
        if args.writer_targets:
            raise ValueError("pressure does not accept --writer-targets")
        if args.executor_targets:
            raise ValueError(
                "pressure inherits the executor target from its writer source"
            )
        options["writer_targets"] = ()
        options["executor_targets"] = ()
    compatibility = authorize_completed_release_replication(
        options,
        domain,
        profile,
    )
    if compatibility is not None:
        options["_completed_release_replication_compatibility"] = compatibility
    profile.validate_options(compatibility_validation_options(options))
    return options


def _pressure_source_manifest(
    args: argparse.Namespace,
    profile: Any,
) -> dict[str, Any] | None:
    if profile.study_id != "pressure":
        return None
    source_values = tuple(args.source_run or ())
    if len(source_values) > 1:
        raise ValueError("pressure accepts exactly one --source-run")
    source_value = str(source_values[0] if source_values else "").strip()
    if not source_value:
        return None
    manifest_path = Path(source_value).expanduser().resolve() / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            f"pressure source run has no manifest: {manifest_path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("pressure source manifest is not an object")
    return manifest


def _run(args: argparse.Namespace) -> Path:
    domain = get_domain(args.domain)
    profile = _study_profile(domain, args.study)
    if args.study == AWARENESS_STUDY_ID and args.presentation_version:
        raise ValueError(
            "--presentation-version applies to behavioral source runs, not the "
            "evaluation-awareness child study"
        )
    options = _route_options(args, domain, profile)
    requested_cases = args.case_ids or ",".join(
        options.get("_source_case_ids", ())
    )
    cases = _selected_cases(
        domain,
        str(options["corpus_version"]),
        requested_cases,
    )
    if profile.runner is not None:
        if is_completed_release_replication(options):
            assert profile.runner is not None
            return Path(profile.runner(domain, cases, options))
        return profile.run(domain, cases, options)
    if profile.builder is None:
        raise NotImplementedError(
            f"study {args.study!r} does not provide a runner or job builder"
        )
    if is_completed_release_replication(options):
        assert profile.builder is not None
        plan = profile.builder(domain, cases, options)
    else:
        plan = profile.build_jobs(domain, cases, options)
    validation = validate_study_plan(
        domain, cases, plan, options, config=load_config()
    )
    if plan.writer_chains:
        validation["writer_checkpoint_resume_fixture"] = (
            validate_writer_checkpoint_resume_fixture(
                domain,
                cases,
                plan,
                options,
                config=load_config(),
            )
        )
    if args.retry_provider_errors and not args.resume_run:
        raise ValueError("--retry-provider-errors requires --resume-run")
    if args.retry_provider_errors:
        continuation = prepare_provider_error_resume(
            domain,
            cases,
            plan,
            options,
            config=load_config(),
        )
        options = {**options, "resume_run": str(continuation)}
    if args.resume_run:
        resume_validation = (
            validate_writer_checkpoint_resume(
                domain,
                cases,
                plan,
                options,
                config=load_config(),
            )
            if plan.writer_chains
            else validate_executor_only_resume(
                domain,
                cases,
                plan,
                options,
                config=load_config(),
            )
        )
        validation["resume"] = resume_validation.to_dict()
    print(
        json.dumps(
            {
                "study_id": plan.study_id,
                "call_plan": validation["call_plan"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    maximum_calls = int(
        validation["call_plan"]["scheduled_calls_maximum"]
    )
    if maximum_calls and args.estimated_cost_usd is None:
        raise ValueError(
            "live routes require --estimated-cost-usd after reviewing the "
            "printed call plan"
        )
    if args.resume_run:
        if plan.writer_chains:
            return resume_writer_checkpoint_study_plan(
                domain, cases, plan, options
            )
        return resume_executor_only_study_plan(domain, cases, plan, options)
    return run_study_plan(domain, cases, plan, options)


def _selected_cases(
    domain: Any,
    corpus_version: str,
    requested: str,
) -> tuple[Any, ...]:
    cases = tuple(domain.corpus.load_cases(corpus_version))
    requested_ids = _csv(requested)
    if not requested_ids:
        return cases
    by_id = {domain.corpus.case_id(case): case for case in cases}
    unknown = sorted(set(requested_ids) - set(by_id))
    if unknown:
        raise ValueError("unknown case IDs: " + ", ".join(unknown))
    return tuple(by_id[case_id] for case_id in requested_ids)


def main(argv: list[str] | None = None) -> None:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(raw_argv)
    args._raw_argv = tuple(raw_argv)
    args._provided_flags = tuple(
        item.split("=", 1)[0]
        for item in raw_argv
        if item.startswith("--")
    )
    if args.list_domains:
        print(json.dumps(_domain_listing(), indent=2))
        return
    if args.list_corpus_versions:
        print(json.dumps(_corpus_listing(args.domain), indent=2))
        return
    if args.list_studies:
        print(_format_study_listing(args.domain))
        return
    if args.list_presentations:
        print(json.dumps(_presentation_listing(args.domain), indent=2))
        return
    if args.list_targets:
        print(json.dumps(_target_listing(), indent=2))
        return
    if args.all_domains and not args.validate_only:
        raise ValueError("--all-domains requires --validate-only")
    if args.batch_size is not None and args.batch_size < 1:
        raise ValueError("--batch-size must be positive")
    if args.writer_runs < 1 or args.executor_runs < 1:
        raise ValueError("writer and executor runs must be positive")
    if not 3600 <= args.writer_route_timeout_seconds <= 21600:
        raise ValueError(
            "--writer-route-timeout-seconds must be between 3600 and 21600"
        )
    if args.seed is not None and args.seed < 0:
        raise ValueError("--seed must be non-negative")
    if args.expected_missing_calls is not None and args.expected_missing_calls < 1:
        raise ValueError("--expected-missing-calls must be positive")
    if (
        args.estimated_cost_usd is not None
        and args.estimated_cost_usd < 0
    ):
        raise ValueError("--estimated-cost-usd must be non-negative")
    if args.validate_only:
        _validate(args)
        return
    run_dir = _run(args)
    print(f"Run saved to {run_dir}")


if __name__ == "__main__":
    main()
