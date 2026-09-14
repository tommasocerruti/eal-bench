"""Bounded event sourcing: validation."""

from __future__ import annotations

import copy
import json


from collections import defaultdict

from collections.abc import Mapping, Sequence

from dataclasses import replace


from pathlib import Path

from tempfile import TemporaryDirectory

from typing import Any


from domains.base import (
    AuthorizationMemoryDomain,
)

from experiments.authorization_memory.leakage import validate_model_context_leakage

from experiments.authorization_memory.persistence import (
    canonical_json,
    content_hash,
)


from experiments.authorization_memory.schemas import (
    ModelContext,
    ModelProvenance,
)


from experiments.authorization_memory.tokens import count_reference_tokens, reference_tokenizer_name


from .core import (
    EVENT_CONDITION_ID,
    EVENT_SCHEMA_VERSION,
    EVENT_TOOL_NAME,
    PublicEventReducer,
    _block_source_ids,
    _canonical_event,
    _canonical_events_by_block,
    _capacity_tokens,
    _forced_tool_choice,
    _raw_event_block_index,
    _raw_events,
    _stable_id,
    _summary,
    event_tool,
    event_writer_instruction,
    event_writer_messages,
    validate_event_arguments,
)

from .runtime import (
    _Trajectory,
    _empty_checkpoint,
    _load_checkpoint,
    _restore_trajectories,
    _save_checkpoint,
)


def validate_options(options: Mapping[str, Any]) -> None:
    if str(options.get("writer_architecture") or "all") not in {"all", "typed"}:
        raise ValueError("event sourcing uses the domain typed current-state representation")
    if str(options.get("writer_strategy") or "all") not in {"all", "incremental"}:
        raise ValueError("event sourcing is incremental by definition")
    if int(options.get("writer_runs", 1)) != 1:
        raise ValueError("event sourcing requires exactly one writer run per seed")
    if int(options.get("executor_runs", 1)) != 1:
        raise ValueError("event sourcing requires exactly one executor run per seed")
    if int(options.get("writer_max_attempts", 2)) != 2:
        raise ValueError("event sourcing requires exactly two structural attempts")
    if str(options.get("capacity_tier") or "primary") != "primary":
        raise ValueError("event sourcing uses the primary typed-memory capacity")

    unsupported = (
        "stop_after_writer_checkpoint",
        "retry_provider_errors",
        "expected_missing_calls",
        "ttc_review_only",
        "ttc_oracle_only",
        "reviewer_target",
        "intervention_stage",
        "cue_level",
        "pressure_variant",
        "reference_run",
        "match_manifest",
        "memory_annotations",
    )
    for key in unsupported:
        if options.get(key) not in (None, False, "", (), []):
            raise ValueError(f"event sourcing does not support --{key.replace('_', '-')}")
    if int(options.get("writer_route_timeout_seconds", 3600)) != 3600:
        raise ValueError("event sourcing does not support custom writer route timeouts")
    estimate = options.get("estimated_cost_usd")
    if estimate is not None:
        import math

        if not math.isfinite(float(estimate)) or float(estimate) <= 0:
            raise ValueError("event sourcing requires a finite positive cost estimate")


def validate_event_sourcing_offline(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    options: Mapping[str, Any],
) -> dict[str, Any]:
    """Run every zero-cost construction and oracle-reducer gate."""

    validate_options(options)
    if domain.event_sourcing is None:
        raise ValueError(f"domain {domain.domain_id} has no event-sourcing lifecycle specification")
    if not cases:
        raise ValueError("event sourcing requires at least one case")
    plan = validate_run_inputs(domain, cases, options)
    presentation = domain.get_presentation(str(options.get("presentation_version") or "") or None)
    capacity_tokens = _capacity_tokens(domain, str(options["corpus_version"]))
    feasibility = validate_bounded_references(domain, cases, presentation.presentation_id)
    reducer = validate_oracle_reducer(domain, cases)
    batch_validation = validate_oracle_event_batches(
        domain,
        cases,
        presentation.presentation_id,
        capacity_tokens,
    )
    fairness = projected_fairness(
        domain, cases, presentation.presentation_id, capacity_tokens=capacity_tokens
    )
    leakage = validate_event_writer_leakage(
        domain,
        cases,
        presentation.presentation_id,
        capacity_tokens,
    )
    resume_fixture = validate_checkpoint_resume_fixture(domain, cases)
    tool = event_tool(domain)
    if EVENT_TOOL_NAME != tool["function"]["name"]:
        raise AssertionError("event tool construction failed")
    return {
        "status": "passed",
        "run_plan": plan,
        "domain_id": domain.domain_id,
        "case_count": len(cases),
        "capacity_tokens": capacity_tokens,
        "bounded_reference_feasibility": feasibility,
        "oracle_reducer": reducer,
        "oracle_event_batches": batch_validation,
        "projected_fairness": fairness,
        "model_visible_leakage": leakage,
        "checkpoint_resume_fixture": resume_fixture,
        "failed_baseline_fixture": validate_failed_baseline_fixture(domain, cases),
        "event_schema_version": EVENT_SCHEMA_VERSION,
        "event_tool_hash": content_hash(tool),
        "writer_instruction_hashes": {
            domain.corpus.case_id(case): content_hash(
                event_writer_instruction(
                    domain,
                    case,
                    capacity_tokens=capacity_tokens,
                    presentation_id=presentation.presentation_id,
                )
            )
            for case in cases
        },
        "reference_index": {"fields": [], "tokens": 0, "required": False},
        "cumulative_event_log_model_visible": False,
    }


def validate_checkpoint_resume_fixture(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
) -> dict[str, Any]:
    """Round-trip an interrupted writer and one-missing-executor fixture."""

    case = cases[0]
    case_id = domain.corpus.case_id(case)
    target = "offline-resume-target"
    seed = 314159
    manifest = {
        "domain_id": domain.domain_id,
        "case_ids": [case_id],
        "seed": seed,
        "writer": {"targets": [target]},
        "executor": {"targets": ["offline-executor"]},
        "memory_implementation_hash": "0" * 64,
        "precommit": {"sha256": "1" * 64},
    }
    checkpoint = _empty_checkpoint(manifest)
    trajectory = _Trajectory(
        case=case,
        target_id=target,
        seed=seed,
        reducer=PublicEventReducer(domain),
    )
    first_block = domain.corpus.blocks(case)[0]
    first_index = int(first_block.block_index)
    events = _canonical_events_by_block(domain, case).get(first_index, ())
    trajectory.reducer.apply_batch(events)
    trajectory.completed_blocks.add(first_index)
    trajectory.current_memory_id = "offline-memory-after-first-block"
    with TemporaryDirectory(prefix="event-sourcing-resume-") as raw_directory:
        path = Path(raw_directory) / "event_writer_checkpoint.json"
        _save_checkpoint(path, checkpoint, [trajectory])
        restored_checkpoint = _load_checkpoint(path, manifest)
        restored = _restore_trajectories(
            domain,
            [case],
            [target],
            seed,
            restored_checkpoint,
        )[0]
        if restored.completed_blocks != {first_index}:
            raise AssertionError("resume fixture lost completed writer blocks")
        if restored.current_memory_id != trajectory.current_memory_id:
            raise AssertionError("resume fixture lost current memory identity")
        if canonical_json(restored.reducer.records) != canonical_json(trajectory.reducer.records):
            raise AssertionError("resume fixture changed reduced state")
        if [event.to_dict() for event in restored.reducer.event_log] != [
            event.to_dict() for event in trajectory.reducer.event_log
        ]:
            raise AssertionError("resume fixture changed the immutable event prefix")
        tampered = copy.deepcopy(manifest)
        tampered["precommit"]["sha256"] = "2" * 64
        try:
            _load_checkpoint(path, tampered)
        except ValueError as exc:
            if "identity" not in str(exc):
                raise
        else:
            raise AssertionError("resume fixture accepted a mismatched precommit")

    executor_resume = _validate_executor_resume_fixture(domain, case)
    attempt_resume = _validate_attempt_resume_fixture(domain, case)
    return {
        "status": "passed",
        "writer_prefix_round_trip": True,
        "completed_blocks_not_regenerated": 1,
        "checkpoint_identity_tamper_rejected": True,
        "executor_resume": executor_resume,
        "attempt_resume": attempt_resume,
    }


def validate_bounded_references(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    presentation_id: str,
) -> dict[str, Any]:
    """Prove lifecycle targets are addressable from bounded state plus new block."""

    presentation = domain.get_presentation(presentation_id)
    operations = defaultdict(int)
    checked = 0
    missing: list[dict[str, Any]] = []
    for case in cases:
        previous_ids: set[str] = set()
        by_block = _canonical_events_by_block(domain, case)
        for block in domain.corpus.blocks(case):
            block_index = int(block.block_index)
            block_text = domain.corpus.render_block(block, presentation)
            available = set(previous_ids)
            for event in by_block.get(block_index, ()):
                operations[event.event_type] += 1
                checked += 1
                target = event.target_authorization_id
                if event.event_type in {"patch", "revoke", "replace"}:
                    if target not in available and (target is None or target not in block_text):
                        missing.append(
                            {
                                "case_id": domain.corpus.case_id(case),
                                "block_index": block_index,
                                "event_type": event.event_type,
                                "target_authorization_id": target,
                            }
                        )
                    if target not in available:
                        available.add(str(target))
                if event.record is not None:
                    available.add(str(event.record["authorization_id"]))
            state = domain.memory.faithful_typed(case, through_block_index=block_index)
            previous_ids = {str(record["authorization_id"]) for record in state["authorizations"]}
    if missing:
        raise ValueError(
            "bounded current state plus new block cannot address every lifecycle target: "
            + canonical_json(missing[0])
        )
    return {
        "status": "passed",
        "events_checked": checked,
        "operations": dict(sorted(operations.items())),
        "unaddressable_operations": 0,
        "bounded_reference_index_required": False,
        "available_inputs": ["compact_previous_state", "new_raw_history_block"],
    }


def validate_oracle_reducer(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
) -> dict[str, Any]:
    """Require exact agreement with canonical state after every true event."""

    reducer_mismatches: list[dict[str, Any]] = []
    transitions = 0
    for case in cases:
        reducer = PublicEventReducer(domain)
        prefix: list[Any] = []
        block_positions = {
            str(block.block_id): int(block.block_index) for block in domain.corpus.blocks(case)
        }
        for raw_event in _raw_events(domain, case):
            prefix.append(raw_event)
            normalized = _canonical_event(
                domain,
                case,
                raw_event,
                event_index=0,
                block_positions=block_positions,
            )
            reducer.apply(normalized)
            block_index = _raw_event_block_index(raw_event, block_positions)
            prefix_case = replace(case, events=tuple(prefix))
            expected = domain.memory.serialize_typed(
                domain.memory.faithful_typed(
                    prefix_case,
                    through_block_index=block_index,
                )
            )
            actual = domain.memory.serialize_typed(reducer.visible_state())
            transitions += 1
            if canonical_json(actual) != canonical_json(expected):
                reducer_mismatches.append(
                    {
                        "case_id": domain.corpus.case_id(case),
                        "event_id": str(raw_event.event_id),
                        "block_index": block_index,
                        "expected_hash": content_hash(expected),
                        "actual_hash": content_hash(actual),
                    }
                )
                break
    if reducer_mismatches:
        raise ValueError("oracle reducer mismatch: " + canonical_json(reducer_mismatches[0]))
    return {
        "status": "passed",
        "cases_tested": len(cases),
        "transitions_tested": transitions,
        "mismatches": 0,
        "first_mismatch": None,
        "exact_agreement": 1.0,
    }


def validate_oracle_event_batches(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    presentation_id: str,
    capacity_tokens: int,
) -> dict[str, Any]:
    """Pass canonical deltas through the same structural batch gate used live."""

    del presentation_id
    updates = 0
    events = 0
    for case in cases:
        reducer = PublicEventReducer(domain)
        grouped = _canonical_events_by_block(domain, case)
        for block in domain.corpus.blocks(case):
            previous = reducer.visible_state()
            batch = grouped.get(int(block.block_index), ())
            arguments = {
                "events": [
                    {
                        "event_type": event.event_type,
                        "target_authorization_id": event.target_authorization_id,
                        "source_turn_ids": list(event.source_turn_ids),
                        "record": copy.deepcopy(event.record),
                        "changes": copy.deepcopy(event.changes),
                    }
                    for event in batch
                ]
            }
            visible_sources = frozenset(
                set(domain.memory.referenced_source_ids(previous))
                | set(_block_source_ids(domain, case, block))
            )
            result = validate_event_arguments(
                domain,
                reducer=reducer,
                arguments=arguments,
                visible_source_ids=visible_sources,
                addressable_authorization_ids=frozenset(
                    record_id
                    for record_id in reducer.records
                    if record_id in domain.corpus.render_block(block)
                ),
                logical_update_id=_stable_id(
                    "oracle-event-batch",
                    domain.domain_id,
                    domain.corpus.case_id(case),
                    str(block.block_index),
                ),
                capacity_tokens=capacity_tokens,
            )
            reducer = result.reducer
            expected = domain.memory.serialize_typed(
                domain.memory.faithful_typed(
                    case,
                    through_block_index=int(block.block_index),
                )
            )
            if canonical_json(result.reduced_state) != canonical_json(expected):
                raise ValueError(
                    f"canonical event batch mismatch for {domain.corpus.case_id(case)} "
                    f"block {block.block_index}"
                )
            updates += 1
            events += len(batch)
    return {
        "status": "passed",
        "updates_tested": updates,
        "events_tested": events,
        "atomic_batch_mismatches": 0,
        "exact_agreement": 1.0,
    }


def projected_fairness(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    presentation_id: str,
    *,
    capacity_tokens: int | None = None,
) -> dict[str, Any]:
    """Measure canonical bounded state/block surfaces before live generation."""

    presentation = domain.get_presentation(presentation_id)
    capacity_tokens = capacity_tokens or _capacity_tokens(domain, domain.corpus.default_version)
    tool = event_tool(domain)
    rows = []
    for case in cases:
        previous = domain.memory.empty_typed()
        for block in domain.corpus.blocks(case):
            state_text = canonical_json(previous)
            block_text = domain.corpus.render_block(block, presentation)
            messages = event_writer_messages(
                domain,
                case,
                previous_state=previous,
                block_text=block_text,
                capacity_tokens=capacity_tokens,
                presentation_id=presentation.presentation_id,
            )
            total_surface = canonical_json(
                {
                    "messages": messages,
                    "tools": [tool],
                    "tool_choice": _forced_tool_choice(),
                }
            )
            reduced = domain.memory.faithful_typed(
                case,
                through_block_index=int(block.block_index),
            )
            rows.append(
                {
                    "case_id": domain.corpus.case_id(case),
                    "block_index": int(block.block_index),
                    "previous_state_tokens": count_reference_tokens(state_text),
                    "reference_index_tokens": 0,
                    "new_block_tokens": count_reference_tokens(block_text),
                    "event_writer_total_surface_tokens": count_reference_tokens(total_surface),
                    "reduced_state_tokens": count_reference_tokens(canonical_json(reduced)),
                }
            )
            previous = reduced
    return {
        "reference_tokenizer": reference_tokenizer_name(),
        "updates": len(rows),
        "capacity_tokens": capacity_tokens,
        "persistent_state_identical_to_typed_baseline": True,
        "raw_block_identical_to_typed_baseline": True,
        "reference_index_tokens": 0,
        "previous_state_tokens": _summary(row["previous_state_tokens"] for row in rows),
        "new_block_tokens": _summary(row["new_block_tokens"] for row in rows),
        "event_writer_total_surface_tokens": _summary(
            row["event_writer_total_surface_tokens"] for row in rows
        ),
        "reduced_state_tokens": _summary(row["reduced_state_tokens"] for row in rows),
    }


def validate_event_writer_leakage(
    domain: AuthorizationMemoryDomain,
    cases: Sequence[Any],
    presentation_id: str,
    capacity_tokens: int,
) -> dict[str, Any]:
    """Apply the repository leak gate to every projected event-writer surface."""

    presentation = domain.get_presentation(presentation_id)
    presentation_hash = content_hash(presentation.to_dict())
    tool = event_tool(domain)
    choice = _forced_tool_choice()
    model = ModelProvenance(
        target_id="offline-event-writer",
        provider="offline",
        requested_model="offline",
        resolved_model="offline",
        effective_parameters={
            "temperature": 1.0,
            "max_tokens": 4096,
            "seed": 0,
        },
    )
    surfaces = 0
    for case in cases:
        previous = domain.memory.empty_typed()
        for block in domain.corpus.blocks(case):
            messages = event_writer_messages(
                domain,
                case,
                previous_state=previous,
                block_text=domain.corpus.render_block(block, presentation),
                capacity_tokens=capacity_tokens,
                presentation_id=presentation_id,
            )
            digest = content_hash({"messages": messages, "tools": [tool], "tool_choice": choice})
            context = ModelContext(
                context_id=_stable_id(
                    "offline-event-context",
                    domain.corpus.case_id(case),
                    str(block.block_index),
                ),
                content_hash=digest,
                stage="writer",
                domain_id=domain.domain_id,
                case_id=domain.corpus.case_id(case),
                condition_id=EVENT_CONDITION_ID,
                block_index=int(block.block_index),
                probe_id=None,
                writer_run_id=0,
                executor_run_id=None,
                memory_id=None,
                memory_attempt_id=None,
                evidence_id=None,
                trial_id=None,
                call_id=_stable_id("offline-event-call", digest),
                framework_run_id=None,
                messages=tuple(messages),
                tools=(tool,),
                tool_choice=choice,
                model=model,
                presentation_id=presentation_id,
                presentation_hash=presentation_hash,
                metadata={
                    "cumulative_event_log_model_visible": False,
                    "reference_index_tokens": 0,
                },
            )
            validate_model_context_leakage(domain, case, context)
            previous = domain.memory.faithful_typed(
                case,
                through_block_index=int(block.block_index),
            )
            surfaces += 1
    return {
        "status": "passed",
        "surfaces_checked": surfaces,
        "cumulative_event_log_model_visible": False,
        "hidden_canonical_events_model_visible": False,
        "future_history_model_visible": False,
    }


def validate_run_inputs(
    domain: AuthorizationMemoryDomain, cases: Sequence[Any], options: Mapping[str, Any]
) -> dict[str, Any]:
    from eal_bench.llm import load_config
    from .study import (
        _baseline_executor_jobs,
        _event_manifest,
        _targets,
        _validate_resume_manifest,
        _verify_frozen_files,
        event_sourcing_implementation,
        validate_routes,
        validate_selected_sources,
    )

    config = load_config(load_env=False)
    routes = validate_routes(config, options)
    sources = (
        validate_selected_sources(domain, cases, options, config=config)
        if options.get("source_runs")
        else []
    )
    updates = sum(len(domain.corpus.blocks(case)) for case in cases) * len(routes["writer"])
    probes = sum(len(domain.corpus.probes(case)) for case in cases) * len(routes["writer"])
    result = {
        "routes": routes,
        "sources": [
            {
                "writer_target_id": source["writer_target_id"],
                "manifest_sha256": source["manifest_sha256"],
            }
            for source in sources
        ],
        "source_compatibility": "verified" if sources else "fixtures_only_no_baseline_sources",
        "writer_logical_updates": updates,
        "writer_calls_maximum": 2 * updates,
        "event_and_baseline_executor_calls": 2 * probes * len(routes["executor"]),
        "oracle_residual_executor_calls_maximum": probes * len(routes["executor"]),
        "baseline_replay": "fresh_current_executor_on_original_final_typed_evidence",
    }
    if sources:
        baseline_jobs, _, _ = _baseline_executor_jobs(domain, cases, sources)
        result["frozen_baseline_jobs"] = len(baseline_jobs)
        presentation = domain.get_presentation(
            str(options.get("presentation_version") or "") or None
        )
        manifest = _event_manifest(
            domain,
            cases,
            options,
            config,
            presentation_id=presentation.presentation_id,
            writer_targets=_targets(options.get("writer_targets")),
            executor_targets=_targets(options.get("executor_targets")),
            capacity_tokens=_capacity_tokens(domain, str(options["corpus_version"])),
            implementation=event_sourcing_implementation(
                domain,
                cases,
                presentation.presentation_id,
                corpus_version=str(options["corpus_version"]),
            ),
            baseline_sources=sources,
        )
        result["run_plan_sha256"] = manifest["run_plan_sha256"]
        if options.get("resume_run"):
            run_dir = Path(str(options["resume_run"])).expanduser().resolve()
            saved = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            _validate_resume_manifest(saved, manifest)
            _verify_frozen_files(run_dir, saved)
            checkpoint_path = run_dir / "event_writer_checkpoint.json"
            if not checkpoint_path.is_file():
                raise ValueError("resume validation requires an existing writer checkpoint")
            checkpoint = _load_checkpoint(checkpoint_path, saved)
            _restore_trajectories(
                domain,
                cases,
                _targets(options.get("writer_targets")),
                int(options["seed"]),
                checkpoint,
            )
            result["resume_compatibility"] = "verified"
    elif options.get("resume_run"):
        raise ValueError("event-sourcing resume validation requires matching baseline sources")
    return result


def _validate_executor_resume_fixture(
    domain: AuthorizationMemoryDomain, case: Any
) -> dict[str, Any]:
    from types import SimpleNamespace
    from eal_bench.llm import load_config
    from experiments.authorization_memory.schemas import FrozenEvidence
    from experiments.authorization_memory.study_plan import ExecutorJob
    from .runtime import (
        _logged_chat_completion,
        _read_checkpoint,
        _run_resumable_executor_jobs,
        _write_checkpoint,
    )

    config = load_config(load_env=False)
    target = config.task("executor").default_target
    presentation = domain.get_presentation()
    payload = domain.memory.serialize_typed(domain.memory.faithful_typed(case))
    evidence = FrozenEvidence(
        evidence_id="offline-resume-evidence",
        domain_id=domain.domain_id,
        case_id=domain.corpus.case_id(case),
        condition_id=EVENT_CONDITION_ID,
        memory_run_id=0,
        writer_seed=314159,
        writer=None,
        architecture=None,
        memory_id="offline-resume-memory",
        payload=payload,
        source_history=None,
        content_hash=content_hash(payload),
        presentation_id=presentation.presentation_id,
        presentation_hash=content_hash(presentation.to_dict()),
    )
    jobs = [
        ExecutorJob(job_id=f"offline-resume-job-{index}", case=case, probe=probe, evidence=evidence)
        for index, probe in enumerate(domain.corpus.probes(case)[:3])
    ]
    if len(jobs) != 3:
        raise ValueError("executor resume fixture requires three domain probes")
    requested = []
    record = {
        "resolved_model": config.resolve_target("executor", target=target).resolved_model,
        "response": {"content": "", "tool_calls": [], "finish_reason": "stop"},
    }

    def batch(task: str, messages: Any, **kwargs: Any) -> list[Any]:
        del task, messages
        requested.extend(kwargs["call_ids"])
        return [
            _logged_chat_completion({**record, "call_id": call_id})
            for call_id in kwargs["call_ids"]
        ]

    with TemporaryDirectory(prefix="event-executor-resume-") as directory:
        run_dir = Path(directory)
        calls_path = run_dir / "calls.jsonl"
        llm = SimpleNamespace(config=config, logger=SimpleNamespace(path=calls_path), batch=batch)
        kwargs = dict(
            run_dir=run_dir,
            executor_task="executor",
            executor_targets=[target],
            batch_size=3,
            seed=314159,
            presentation=presentation,
        )
        original, original_contexts = _run_resumable_executor_jobs(llm, domain, jobs, **kwargs)
        if len(requested) != 3:
            raise AssertionError("executor fixture did not make three local fake calls")
        path = run_dir / "executor_checkpoint.json"
        checkpoint = _read_checkpoint(path)
        missing_id = original[-1]["metadata"]["core"]["trial_id"]
        missing_call = original[-1]["metadata"]["core"]["call_id"]
        del checkpoint["trials"][missing_id]
        del checkpoint["contexts"][missing_id]
        _write_checkpoint(path, checkpoint)
        requested.clear()
        resumed, contexts = _run_resumable_executor_jobs(llm, domain, jobs, **kwargs)
        if requested != [missing_call] or resumed != original or contexts != original_contexts:
            raise AssertionError(
                "executor recovery changed completed trials or regenerated saved calls"
            )
        checkpoint = _read_checkpoint(path)
        del checkpoint["trials"][missing_id]
        del checkpoint["contexts"][missing_id]
        _write_checkpoint(path, checkpoint)
        calls_path.write_text(
            json.dumps({**record, "call_id": missing_call}) + "\n", encoding="utf-8"
        )
        requested.clear()
        recovered, recovered_contexts = _run_resumable_executor_jobs(llm, domain, jobs, **kwargs)
        if requested or recovered != original or recovered_contexts != original_contexts:
            raise AssertionError(
                "logged executor recovery repeated a paid call or changed its outcome"
            )
        checkpoint = json.loads(path.read_text())
        checkpoint["trials"][missing_id]["response_text"] = "tampered"
        path.write_text(json.dumps(checkpoint), encoding="utf-8")
        try:
            _run_resumable_executor_jobs(llm, domain, jobs, **kwargs)
        except ValueError as exc:
            if "hash" not in str(exc):
                raise
        else:
            raise AssertionError("executor checkpoint content tampering was accepted")
    return {
        "saved_trials_preserved": 2,
        "only_missing_call_generated": True,
        "logged_call_recovered_without_regeneration": True,
        "content_tamper_rejected": True,
    }


def _validate_attempt_resume_fixture(
    domain: AuthorizationMemoryDomain, case: Any
) -> dict[str, Any]:
    from .runtime import _attempt_input, _record_attempt_rows

    presentation = domain.get_presentation()
    trajectory = _Trajectory(
        case=case, target_id="offline-writer", seed=314159, reducer=PublicEventReducer(domain)
    )
    block = domain.corpus.blocks(case)[0]
    attempt = _attempt_input(
        domain,
        trajectory,
        block,
        attempt_index=0,
        repair_of_attempt_id=None,
        presentation_id=presentation.presentation_id,
        capacity_tokens=_capacity_tokens(domain, domain.corpus.default_version),
        repair_detail=None,
    )
    checkpoint = {"event_attempts": [], "writer_contexts": [], "writer_resources": []}
    writer = ModelProvenance(
        target_id="offline-writer",
        provider="offline",
        requested_model="offline",
        resolved_model="offline",
        effective_parameters={"temperature": 1.0},
    )
    kwargs = dict(
        presentation_hash=content_hash(presentation.to_dict()),
        implementation_hash="0" * 64,
        terminal=True,
        writer=writer,
        presentation_id=presentation.presentation_id,
    )
    for _ in range(2):
        _record_attempt_rows(
            domain, checkpoint, attempt, RuntimeError("fixture"), "fixture", **kwargs
        )
    if any(len(rows) != 1 for rows in checkpoint.values()):
        raise AssertionError("interrupted writer recovery duplicates persisted attempt rows")
    return {"interrupted_wave_attempts_deduplicated": True}


def validate_failed_baseline_fixture(
    domain: AuthorizationMemoryDomain, cases: Sequence[Any]
) -> dict[str, Any]:
    from analysis.event_sourcing import (
        _baseline_representation,
        _enrich_rows,
        _paired_behavior,
        _summary_row,
    )
    from experiments.authorization_memory.persistence import write_jsonl
    from experiments.authorization_memory.pipeline import _study_job_messages
    from experiments.authorization_memory.schemas import FrozenEvidence
    from experiments.authorization_memory.study_plan import ExecutorJob
    from experiments.authorization_memory.surfaces import model_visible_tools
    from .sources import _validate_baseline_surfaces

    case = cases[0]
    case_id = domain.corpus.case_id(case)
    presentation = domain.get_presentation()
    payload = domain.memory.serialize_typed(domain.memory.empty_typed())
    writer = ModelProvenance(
        target_id="offline-writer",
        provider="offline",
        requested_model="offline",
        resolved_model="offline",
        effective_parameters={"temperature": 1.0},
    )
    item = FrozenEvidence(
        evidence_id="offline-failed-evidence",
        domain_id=domain.domain_id,
        case_id=case_id,
        condition_id="incremental_typed",
        memory_run_id=0,
        writer_seed=314159,
        writer=writer,
        architecture=None,
        memory_id="offline-empty-fallback",
        payload=payload,
        source_history=None,
        content_hash=content_hash(payload),
        presentation_id=presentation.presentation_id,
        presentation_hash=content_hash(presentation.to_dict()),
        source_attempt_id=None,
    )
    memory = {**item.to_dict(), "memory_id": item.memory_id}
    states = [
        {
            "condition_id": "incremental_typed",
            "case_id": case_id,
            "block_index": int(block.block_index),
            "current_memory_id": None,
        }
        for block in domain.corpus.blocks(case)
    ]
    manifest = {
        "domain_id": domain.domain_id,
        "corpus_version": domain.corpus.default_version,
        "case_ids": [case_id],
        "seed": 314159,
        "writer": {"targets": [writer.target_id]},
    }
    trials, contexts = [], []
    for index, probe in enumerate(domain.corpus.probes(case)):
        trial_id = f"offline-failed-trial-{index}"
        trials.append(
            {
                "evidence_id": item.evidence_id,
                "condition_id": item.condition_id,
                "probe_id": probe.probe_id,
                "request_authorized": domain.executor.oracle(case, probe.request).authorized,
                "metadata": {
                    "study": {"evidence_role": "generated_final"},
                    "core": {"trial_id": trial_id},
                },
            }
        )
        job = ExecutorJob(job_id=trial_id, case=case, probe=probe, evidence=item)
        surface = {
            "messages": _study_job_messages(domain, job, presentation=presentation, pressure=None),
            "tools": model_visible_tools(domain, presentation),
            "tool_choice": "auto",
        }
        contexts.append(
            {
                **surface,
                "stage": "executor",
                "trial_id": trial_id,
                "content_hash": content_hash(surface),
            }
        )
    rows = {
        "trials": trials,
        "model_contexts": contexts,
        "memory_states": states,
        "memories": [memory],
        "evidence": [item.to_dict()],
    }
    with TemporaryDirectory(prefix="event-failed-baseline-") as directory:
        files = {}
        for name, values in rows.items():
            path = Path(directory) / f"{name}.jsonl"
            write_jsonl(path, values)
            files[name] = {"path": str(path)}
        _validate_baseline_surfaces(domain, manifest, files, [item.to_dict()], presentation)
    representation = _baseline_representation(
        {"manifest": manifest, "rows": rows, "run_dir": "offline-failed-baseline"}
    )
    if len([row for row in representation if row["row_type"] == "state_transition"]) != len(states):
        raise AssertionError(
            "failed initial writer states disappeared from representation denominators"
        )
    base = {
        "domain_id": domain.domain_id,
        "case_id": case_id,
        "target_id": "offline-writer",
        "writer_seed": 314159,
        "executor_target_id": "offline-executor",
        "probe_id": "offline-probe",
        "request_authorized": False,
        "requested_action_taken": False,
    }
    manifest["presentation"] = presentation.to_dict()
    manifest["presentation_hash"] = content_hash(presentation.to_dict())
    manifest["writer"]["target_routes"] = [{**writer.to_dict(), "request_parameters": {}}]
    executor = {**writer.to_dict(), "target_id": "offline-executor"}
    fixture_run = {"manifest": manifest}
    pairs = _paired_behavior(
        _enrich_rows(
            [
                {
                    **base,
                    "provider_error": "fixture",
                    "executor": {**executor, "response_model": None},
                }
            ],
            fixture_run,
        ),
        _enrich_rows(
            [
                {
                    **base,
                    "provider_error": None,
                    "executor": {**executor, "response_model": "offline"},
                }
            ],
            fixture_run,
        ),
    )
    summary = _summary_row(
        "unauthorized_submission", pairs, stratum="fixture", stratum_value="offline", draws=10
    )
    if (
        summary["paired_observations"] != 1
        or summary["baseline_provider_errors"] != 1
        or summary["typed_incremental"]["denominator"] != 0
    ):
        raise AssertionError("one-sided provider failure was dropped or counted as valid behavior")
    invalid_pairs = _paired_behavior(
        [{**base, "decision": "invalid"}], [{**base, "decision": "no_action"}]
    )
    invalid_summary = _summary_row(
        "unauthorized_submission",
        invalid_pairs,
        stratum="fixture",
        stratum_value="offline",
        draws=10,
    )
    if invalid_summary["typed_incremental"]["denominator"] != 1:
        raise AssertionError(
            "invalid or no-action response disappeared from behavioral denominators"
        )
    return {
        "initial_failed_states_retained": len(states),
        "empty_final_fallback_accepted": True,
        "one_sided_provider_failure_reported_separately": True,
        "invalid_and_no_action_in_behavioral_denominators": True,
    }
