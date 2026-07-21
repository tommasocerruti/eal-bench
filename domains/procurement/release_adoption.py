from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from domains import get_domain
from domains.base import BenchmarkProbe
from experiments.authorization_memory.challenges import (
    prepare_challenge,
    prepare_challenge_context,
)
from experiments.authorization_memory.langmem_writer import (
    memory_implementation_manifest,
)
from experiments.authorization_memory.persistence import (
    content_hash,
    file_hash,
    write_json,
    write_jsonl,
)
from experiments.authorization_memory.pipeline import _study_job_messages
from experiments.authorization_memory.study_plan import ExecutorJob
from experiments.authorization_memory.surfaces import model_visible_tools

from .cases import load_cases, render_full_history
from .challenge import (
    BASELINE_PRESSURE_ID,
    intervention_challenge_context,
    writer_pressure_context,
)
from .release import load_release, validate_release
from .schemas import Transaction
from .studies.routes import _evidence_from_row, _memory_from_row


ADOPTION_SCHEMA_VERSION = "release_adoption_v1"
ADOPTED_RUNS = {
    "controls": "procurement_v1__adopted__gptoss-controls",
    "writer": "procurement_v1__adopted__gptoss-writer",
    "alternate_controls": "procurement_v1__adopted__deepseek-controls",
}


def adopt_release_runs(
    *,
    controls_run: Path,
    writer_run: Path,
    alternate_controls_run: Path,
    output_root: Path,
) -> dict[str, Any]:
    domain = get_domain("procurement")
    release_validation = validate_release(domain)
    release = load_release()
    presentation = domain.get_presentation(domain.default_presentation_id)
    implementation = memory_implementation_manifest(domain)
    sources = {
        "controls": controls_run.expanduser().resolve(),
        "writer": writer_run.expanduser().resolve(),
        "alternate_controls": alternate_controls_run.expanduser().resolve(),
    }
    expected = {
        "controls": ("controls", "gptoss_baseten"),
        "writer": ("writer", "gptoss_baseten"),
        "alternate_controls": ("controls", "deepseek_baseten"),
    }
    adopted: dict[str, Any] = {}
    for role, source in sources.items():
        study, target = expected[role]
        destination = output_root / ADOPTED_RUNS[role]
        adopted[role] = _adopt_run(
            domain=domain,
            release=release,
            release_validation=release_validation,
            presentation=presentation,
            implementation=implementation,
            source=source,
            destination=destination,
            role=role,
            expected_study=study,
            expected_executor_target=target,
        )
    summary = {
        "schema_version": ADOPTION_SCHEMA_VERSION,
        "status": "passed",
        "network_request_made": False,
        "release_id": release["release_id"],
        "release_manifest_sha256": release_validation["manifest_sha256"],
        "runs": adopted,
    }
    write_json(output_root / "procurement_v1__adoption.json", summary)
    return summary


def load_adopted_pressure_source(
    *,
    domain: Any,
    cases: Sequence[Any],
    source_path: Path,
    options: Mapping[str, Any],
    presentation: Any,
) -> dict[str, Any]:
    adopted_manifest_path = source_path / "manifest.json"
    adopted_manifest = _load_json(adopted_manifest_path)
    adoption = adopted_manifest.get("release_adoption")
    if not isinstance(adoption, Mapping) or adoption.get("role") != "writer":
        raise ValueError("pressure adoption source is not a writer run")
    implementation = memory_implementation_manifest(domain)
    if (
        adopted_manifest.get("status") != "completed"
        or adopted_manifest.get("study") != "writer"
        or adopted_manifest.get("domain_id") != domain.domain_id
        or adopted_manifest.get("corpus_version") != options["corpus_version"]
        or adopted_manifest.get("presentation_hash")
        != content_hash(presentation.to_dict())
        or adopted_manifest.get("memory_implementation_id")
        != implementation["memory_implementation_id"]
        or adopted_manifest.get("memory_implementation_hash")
        != implementation["memory_implementation_hash"]
    ):
        raise ValueError("adopted writer source differs from the active release")
    source = source_path / "source"
    original_manifest_path = source / "manifest.json"
    original_manifest = _load_json(original_manifest_path)
    if file_hash(original_manifest_path) != adoption["source_manifest_sha256"]:
        raise ValueError("adopted writer source manifest changed")
    _validate_source_files(source, original_manifest)
    if adoption["source_files"] != _validate_source_files(
        source, original_manifest
    ):
        raise ValueError("adopted writer source inventory changed")
    _validate_source_files(source_path, adopted_manifest)

    raw_trials = _artifact_rows(source, original_manifest, "trials")
    adopted_trials = _artifact_rows(
        source_path,
        adopted_manifest,
        "trials",
    )
    case_map, probe_map = _adopted_trial_maps(
        domain,
        cases,
        raw_trials,
        adopted_trials,
    )
    case_by_id = {case.case_id: case for case in cases}
    raw_memories = _artifact_rows(source, original_manifest, "memories")
    raw_evidence = _artifact_rows(source, original_manifest, "evidence")
    raw_contexts = _artifact_rows(source, original_manifest, "model_contexts")
    raw_pressure = _artifact_rows(
        source,
        original_manifest,
        "pressure_source_jobs",
    )
    contexts = {
        str(row["trial_id"]): row
        for row in raw_contexts
        if row.get("stage") == "executor" and row.get("trial_id") is not None
    }
    trials = {
        str(row["metadata"]["core"]["trial_id"]): row for row in raw_trials
    }
    current_presentation_hash = content_hash(presentation.to_dict())
    memories = {}
    for row in raw_memories:
        item = _memory_from_adoption_row(
            row,
            case_id=case_map[str(row["case_id"])],
            presentation_id=presentation.presentation_id,
            presentation_hash=current_presentation_hash,
            implementation=implementation,
        )
        memories[item.memory_id] = item
    evidence = {}
    for row in raw_evidence:
        item = _adopt_evidence(
            row,
            case_id=case_map[str(row["case_id"])],
            presentation_id=presentation.presentation_id,
            presentation_hash=current_presentation_hash,
            implementation=implementation,
        )
        evidence[item.evidence_id] = item

    writer_baseline_rows = []
    for trial_id, trial in sorted(trials.items()):
        study = trial["metadata"]["study"]
        if study.get("evidence_role") != "generated_final":
            continue
        source_case_id = str(trial["case_id"])
        case = case_by_id[case_map[source_case_id]]
        probe = probe_map[(source_case_id, str(trial["probe_id"]))]
        item = evidence[str(trial["evidence_id"])]
        memory = memories[str(item.memory_id)]
        context = contexts[trial_id]
        _validate_adopted_surface(
            domain=domain,
            presentation=presentation,
            case=case,
            probe=probe,
            evidence=item,
            source_context=context,
        )
        baseline = prepare_challenge(
            domain,
            case,
            probe,
            pressure_id=BASELINE_PRESSURE_ID,
        )
        writer_baseline_rows.append(
            {
                "writer_baseline_source_id": content_hash(
                    {"kind": "adopted_writer_baseline", "trial_id": trial_id}
                ),
                "case_id": case.case_id,
                "probe_id": probe.probe_id,
                "pair_id": probe.pair_id,
                "dimension": probe.dimension,
                "request_scope": probe.request_scope,
                "request_authorized": bool(trial["request_authorized"]),
                "condition_id": str(trial["condition_id"]),
                "evidence_id": item.evidence_id,
                "evidence_hash": item.content_hash,
                "memory_id": memory.memory_id,
                "memory_hash": memory.content_hash,
                "baseline_job_id": str(study["job_id"]),
                "baseline_trial_id": trial_id,
                "baseline_call_id": str(trial["metadata"]["core"]["call_id"]),
                "baseline_context_id": str(context["context_id"]),
                "baseline_context_hash": str(context["content_hash"]),
                "baseline_challenge_text": baseline.rendered_text,
                "baseline_challenge_hash": baseline.rendered_sha256,
                "choice_set_hash": baseline.choice_set_sha256,
                "executor_target_id": str(trial["executor"]["target_id"]),
                "executor_run_id": int(trial["executor_run_id"]),
                "executor_seed": int(trial["seed"]),
                "executor_provider": str(trial["executor"]["provider"]),
                "executor_requested_model": str(
                    trial["executor"]["requested_model"]
                ),
                "executor_resolved_model": str(
                    trial["executor"]["resolved_model"]
                ),
                "executor_effective_parameters": dict(
                    trial["executor"]["effective_parameters"]
                ),
            }
        )

    current_provenance = dict(
        domain.corpus.provenance(str(options["corpus_version"]))
    )
    pressure_rows = []
    for row in raw_pressure:
        adapted = copy.deepcopy(row)
        adapted["case_id"] = case_map[str(row["case_id"])]
        adapted["corpus_version"] = options["corpus_version"]
        adapted["corpus_provenance"] = current_provenance
        adapted["presentation_id"] = presentation.presentation_id
        adapted["presentation_hash"] = current_presentation_hash
        adapted["memory_implementation_id"] = implementation[
            "memory_implementation_id"
        ]
        adapted["memory_implementation_hash"] = implementation[
            "memory_implementation_hash"
        ]
        case = case_by_id[str(adapted["case_id"])]
        request = Transaction.from_dict(dict(adapted["witness_request"]))
        baseline = prepare_challenge_context(
            domain,
            writer_pressure_context(
                case,
                request,
                candidate_id=str(adapted["candidate_id"]),
            ),
            pressure_id=BASELINE_PRESSURE_ID,
        )
        if (
            baseline.rendered_text != row["baseline_challenge_text"]
            or baseline.rendered_sha256 != row["baseline_challenge_hash"]
            or baseline.choice_set_sha256 != row["choice_set_hash"]
        ):
            raise ValueError("adopted natural-error challenge changed")
        adapted["baseline_challenge_text"] = baseline.rendered_text
        adapted["baseline_challenge_hash"] = baseline.rendered_sha256
        adapted["choice_set_hash"] = baseline.choice_set_sha256
        adapted["objective_framing"] = baseline.pressure.objective_framing
        adapted["operational_stakes"] = baseline.pressure.operational_stakes
        adapted["alternative_disadvantage"] = (
            baseline.pressure.alternative_disadvantage
        )
        item = evidence[str(adapted["evidence_id"])]
        if (
            item.memory_implementation_id
            != adapted["memory_implementation_id"]
            or item.memory_implementation_hash
            != adapted["memory_implementation_hash"]
        ):
            raise ValueError("adopted natural-error memory lineage changed")
        pressure_rows.append(adapted)
    return {
        "manifest": adopted_manifest,
        "manifest_sha256": file_hash(adopted_manifest_path),
        "pressure_source_jobs": pressure_rows,
        "writer_baseline_jobs": tuple(writer_baseline_rows),
        "memories": memories,
        "evidence": evidence,
    }


def _adopt_run(
    *,
    domain: Any,
    release: Mapping[str, Any],
    release_validation: Mapping[str, Any],
    presentation: Any,
    implementation: Mapping[str, Any],
    source: Path,
    destination: Path,
    role: str,
    expected_study: str,
    expected_executor_target: str,
) -> dict[str, Any]:
    source_manifest_path = source / "manifest.json"
    source_manifest = _load_json(source_manifest_path)
    _validate_source_manifest(
        source,
        source_manifest,
        expected_study=expected_study,
        expected_executor_target=expected_executor_target,
    )
    source_files = _validate_source_files(source, source_manifest)
    source_cases = load_cases(str(source_manifest["corpus_version"]))
    current_cases = domain.corpus.load_cases(domain.corpus.default_version)
    case_map = _case_map(source_cases, current_cases)
    probe_map = _probe_map(domain, source_cases, current_cases, case_map)
    source_trials = _load_jsonl(source / source_manifest["files"]["trials"]["path"])
    source_contexts = _load_jsonl(
        source / source_manifest["files"]["model_contexts"]["path"]
    )
    contexts_by_trial = {
        str(row["trial_id"]): row
        for row in source_contexts
        if row.get("stage") == "executor" and row.get("trial_id") is not None
    }
    source_evidence = {
        str(row["evidence_id"]): row
        for row in _load_jsonl(
            source / source_manifest["files"]["evidence"]["path"]
        )
    }
    pressure_rows = _pressure_rows(source, source_manifest)
    pressure_by_trial = {
        str(row["baseline_trial_id"]): row for row in pressure_rows
    }
    current_presentation_hash = content_hash(presentation.to_dict())
    current_case_by_id = {case.case_id: case for case in current_cases}
    tools = list(model_visible_tools(domain, presentation))
    normalized_trials: list[dict[str, Any]] = []
    exact_surfaces = 0
    oracle_rescored = 0
    action_rescored = 0
    for source_trial in source_trials:
        normalized, current_case, current_probe, block_index = _normalize_trial(
            domain=domain,
            presentation=presentation,
            presentation_hash=current_presentation_hash,
            implementation=implementation,
            source_trial=source_trial,
            source_context=contexts_by_trial[str(
                source_trial["metadata"]["core"]["trial_id"]
            )],
            source_evidence=source_evidence[str(source_trial["evidence_id"])],
            pressure_row=pressure_by_trial.get(
                str(source_trial["metadata"]["core"]["trial_id"])
            ),
            case_map=case_map,
            probe_map=probe_map,
            current_case_by_id=current_case_by_id,
            tools=tools,
        )
        oracle_rescored += 1
        if _verify_action_score(
            domain,
            current_case,
            current_probe,
            source_trial,
            through_block_index=block_index,
        ):
            action_rescored += 1
        exact_surfaces += 1
        normalized_trials.append(normalized)

    adopted_manifest = _adopted_manifest(
        source_manifest=source_manifest,
        source_manifest_sha256=file_hash(source_manifest_path),
        source_files=source_files,
        release=release,
        release_validation=release_validation,
        presentation=presentation,
        presentation_hash=current_presentation_hash,
        implementation=implementation,
        case_ids=[case.case_id for case in current_cases],
        role=role,
        exact_surfaces=exact_surfaces,
        oracle_rescored=oracle_rescored,
        action_rescored=action_rescored,
    )
    _persist_adopted_run(
        destination=destination,
        source=source,
        source_manifest=source_manifest,
        adopted_manifest=adopted_manifest,
        trials=normalized_trials,
    )
    return {
        "role": role,
        "path": str(destination.resolve()),
        "manifest_sha256": file_hash(destination / "manifest.json"),
        "source_manifest_sha256": file_hash(source_manifest_path),
        "source_seed": source_manifest["seed"],
        "trials": len(normalized_trials),
        "provider_visible_surfaces_verified": exact_surfaces,
        "oracle_labels_rescored": oracle_rescored,
        "terminal_actions_rescored": action_rescored,
    }


def _normalize_trial(
    *,
    domain: Any,
    presentation: Any,
    presentation_hash: str,
    implementation: Mapping[str, Any],
    source_trial: Mapping[str, Any],
    source_context: Mapping[str, Any],
    source_evidence: Mapping[str, Any],
    pressure_row: Mapping[str, Any] | None,
    case_map: Mapping[str, str],
    probe_map: Mapping[tuple[str, str], BenchmarkProbe],
    current_case_by_id: Mapping[str, Any],
    tools: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], Any, BenchmarkProbe, int | None]:
    source_case_id = str(source_trial["case_id"])
    current_case = current_case_by_id[case_map[source_case_id]]
    block_index: int | None = None
    challenge_context = None
    if pressure_row is None:
        current_probe = probe_map.get(
            (source_case_id, str(source_trial["probe_id"]))
        )
        if current_probe is None:
            current_probe = _probe_from_context(
                domain,
                current_case,
                source_trial,
                source_context,
            )
            challenge_context = _intervention_context_from_trial(
                current_case,
                current_probe,
                source_trial,
            )
        prepared = (
            prepare_challenge_context(
                domain,
                challenge_context,
                pressure_id=BASELINE_PRESSURE_ID,
            )
            if challenge_context is not None
            else prepare_challenge(
                domain,
                current_case,
                current_probe,
                pressure_id=BASELINE_PRESSURE_ID,
            )
        )
    else:
        request = Transaction.from_dict(dict(pressure_row["witness_request"]))
        current_probe = BenchmarkProbe(
            probe_id=f"adopted:{pressure_row['candidate_id']}:{pressure_row['evidence_role']}",
            pair_id=str(pressure_row["candidate_id"]),
            dimension=str(pressure_row.get("witness_dimension") or "natural_overgrant"),
            request_scope="out_of_scope",
            request=request,
        )
        block_index = int(pressure_row["oracle_block_index"])
        challenge_context = writer_pressure_context(
            current_case,
            request,
            candidate_id=str(pressure_row["candidate_id"]),
        )
        prepared = prepare_challenge_context(
            domain,
            challenge_context,
            pressure_id=BASELINE_PRESSURE_ID,
        )
    current_authorized = domain.executor.oracle(
        current_case,
        current_probe.request,
        through_block_index=block_index,
    ).authorized
    if current_authorized is not bool(source_trial["request_authorized"]):
        raise ValueError("release adoption changed an oracle label")

    evidence = _adopt_evidence(
        source_evidence,
        case_id=current_case.case_id,
        presentation_id=presentation.presentation_id,
        presentation_hash=presentation_hash,
        implementation=implementation,
    )
    job = ExecutorJob(
        job_id=str(source_trial["metadata"]["study"]["job_id"]),
        case=current_case,
        probe=current_probe,
        evidence=evidence,
        oracle_block_index=block_index,
        challenge_context=challenge_context,
    )
    messages = _study_job_messages(
        domain,
        job,
        presentation=presentation,
        pressure=None,
    )
    if (
        messages != source_context["messages"]
        or list(tools) != source_context["tools"]
        or source_context["tool_choice"] != "auto"
    ):
        raise ValueError(
            f"provider-visible executor surface changed for "
            f"{source_trial['metadata']['core']['trial_id']} "
            f"({source_trial['metadata']['study'].get('evidence_role')}): "
            f"messages={content_hash(messages)}/"
            f"{content_hash(source_context['messages'])}, "
            f"tools={content_hash(list(tools))}/"
            f"{content_hash(source_context['tools'])}"
        )

    normalized = copy.deepcopy(dict(source_trial))
    normalized["case_id"] = current_case.case_id
    normalized["probe_id"] = current_probe.probe_id
    normalized["request_authorized"] = current_authorized
    normalized["domain_adapter_version"] = domain.adapter_version
    core = normalized["metadata"]["core"]
    core["pair_id"] = current_probe.pair_id
    core["dimension"] = current_probe.dimension
    core["request_scope"] = current_probe.request_scope
    core["presentation_id"] = presentation.presentation_id
    core["presentation_hash"] = presentation_hash
    core["presentation"] = presentation.to_dict()
    if normalized.get("writer") is not None:
        normalized["memory_implementation_id"] = implementation[
            "memory_implementation_id"
        ]
        normalized["memory_implementation_hash"] = implementation[
            "memory_implementation_hash"
        ]
        core["memory_implementation_id"] = implementation[
            "memory_implementation_id"
        ]
        core["memory_implementation_hash"] = implementation[
            "memory_implementation_hash"
        ]
    challenge = prepared.metadata()
    normalized["metadata"]["domain"]["challenge"] = challenge
    return normalized, current_case, current_probe, block_index


def _probe_from_context(
    domain: Any,
    case: Any,
    trial: Mapping[str, Any],
    context: Mapping[str, Any],
) -> BenchmarkProbe:
    user_messages = [
        str(message.get("content") or "")
        for message in context["messages"]
        if message.get("role") == "user"
    ]
    if len(user_messages) != 1 or "Current transaction:\n" not in user_messages[0]:
        raise ValueError("source executor context has no unique transaction")
    serialized = user_messages[0].split("Current transaction:\n", 1)[1]
    serialized = serialized.split("\n</CURRENT_REQUEST>", 1)[0].strip()
    request_data = json.loads(serialized)
    request_data["transaction_id"] = content_hash(request_data)
    request = Transaction.from_dict(request_data)
    core = trial["metadata"]["core"]
    return BenchmarkProbe(
        probe_id=f"adopted:{content_hash({'request': request_data, 'core': core})}",
        pair_id=str(trial["metadata"]["study"]["intervention_id"]),
        dimension=str(core["dimension"]),
        request_scope=str(core["request_scope"]),
        request=request,
    )


def _intervention_context_from_trial(
    case: Any,
    probe: BenchmarkProbe,
    trial: Mapping[str, Any],
) -> Any:
    challenge = trial["metadata"]["domain"]["challenge"]
    rendered = str(challenge["rendered_text"])
    match = re.search(
        r"^- Option 1: Place (.+?) with (.+?) for ([A-Z]{3}) "
        r"([0-9,]+) at ([^;]+);",
        rendered,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError("source intervention challenge has no parseable preferred order")
    category, vendor, currency, amount, action_time = match.groups()
    preferred = Transaction(
        transaction_id=content_hash(
            {
                "candidate": trial["metadata"]["study"]["intervention_id"],
                "course": "preferred",
            }
        ),
        grantee=probe.request.grantee,
        action=probe.request.action,
        vendor=vendor,
        category=category,
        amount=int(amount.replace(",", "")),
        currency=currency,
        action_time=action_time,
    )
    if all(
        getattr(preferred, field) == getattr(probe.request, field)
        for field in (
            "grantee",
            "action",
            "vendor",
            "category",
            "amount",
            "currency",
            "action_time",
        )
    ):
        preferred = probe.request
    return intervention_challenge_context(
        case,
        requested_transaction=probe.request,
        preferred_transaction=preferred,
        candidate_id=str(trial["metadata"]["study"]["intervention_id"]),
    )


def _verify_action_score(
    domain: Any,
    case: Any,
    probe: BenchmarkProbe,
    trial: Mapping[str, Any],
    *,
    through_block_index: int | None,
) -> bool:
    if (
        trial.get("provider_error") is not None
        or trial.get("raw_tool_name") is None
        or trial.get("tool_call_count") != 1
        or trial.get("terminal_call_count") != 1
    ):
        return False
    score = domain.executor.score_tool_call(
        case,
        probe.request,
        str(trial["raw_tool_name"]),
        dict(trial["raw_tool_arguments"]),
        through_block_index=through_block_index,
    )
    expected = {
        "decision": score.decision.value,
        "requested_action_taken": score.decision.value == "execute_requested",
        "unauthorized_action_taken": (
            score.decision.value in {"execute_requested", "execute_other"}
            and score.action_authorized is False
        ),
        "action_mismatch": score.decision.value == "execute_other",
        "compliant": score.compliant,
        "parseable": score.valid_arguments,
    }
    observed = {key: trial.get(key) for key in expected}
    if observed != expected:
        raise ValueError("release adoption changed normalized action scoring")
    return True


def _adopt_evidence(
    row: Mapping[str, Any],
    *,
    case_id: str,
    presentation_id: str,
    presentation_hash: str,
    implementation: Mapping[str, Any],
) -> Any:
    evidence = _evidence_from_row(row)
    generated = evidence.writer is not None
    return replace(
        evidence,
        case_id=case_id,
        presentation_id=presentation_id,
        presentation_hash=presentation_hash,
        memory_implementation_id=(
            implementation["memory_implementation_id"]
            if generated
            else evidence.memory_implementation_id
        ),
        memory_implementation_hash=(
            implementation["memory_implementation_hash"]
            if generated
            else evidence.memory_implementation_hash
        ),
    )


def _memory_from_adoption_row(
    row: Mapping[str, Any],
    *,
    case_id: str,
    presentation_id: str,
    presentation_hash: str,
    implementation: Mapping[str, Any],
) -> Any:
    memory = _memory_from_row(row)
    generated = memory.writer is not None
    return replace(
        memory,
        case_id=case_id,
        presentation_id=presentation_id,
        presentation_hash=presentation_hash,
        memory_implementation_id=(
            implementation["memory_implementation_id"]
            if generated
            else memory.memory_implementation_id
        ),
        memory_implementation_hash=(
            implementation["memory_implementation_hash"]
            if generated
            else memory.memory_implementation_hash
        ),
    )


def _validate_adopted_surface(
    *,
    domain: Any,
    presentation: Any,
    case: Any,
    probe: BenchmarkProbe,
    evidence: Any,
    source_context: Mapping[str, Any],
) -> None:
    job = ExecutorJob(
        job_id="adopted_surface_check",
        case=case,
        probe=probe,
        evidence=evidence,
    )
    messages = _study_job_messages(
        domain,
        job,
        presentation=presentation,
        pressure=None,
    )
    tools = list(model_visible_tools(domain, presentation))
    if (
        messages != source_context["messages"]
        or tools != source_context["tools"]
        or source_context["tool_choice"] != "auto"
    ):
        raise ValueError("adopted writer baseline surface changed")


def _artifact_rows(
    source: Path,
    manifest: Mapping[str, Any],
    name: str,
) -> list[dict[str, Any]]:
    entry = manifest["files"].get(name)
    if not isinstance(entry, Mapping):
        raise ValueError(f"adopted writer source lacks {name!r}")
    return _load_jsonl(source / str(entry["path"]))


def _adopted_manifest(
    *,
    source_manifest: Mapping[str, Any],
    source_manifest_sha256: str,
    source_files: Mapping[str, Any],
    release: Mapping[str, Any],
    release_validation: Mapping[str, Any],
    presentation: Any,
    presentation_hash: str,
    implementation: Mapping[str, Any],
    case_ids: Sequence[str],
    role: str,
    exact_surfaces: int,
    oracle_rescored: int,
    action_rescored: int,
) -> dict[str, Any]:
    manifest = copy.deepcopy(dict(source_manifest))
    manifest.update(
        {
            "domain_id": release["domain_id"],
            "domain_maturity": release["maturity"],
            "corpus_version": release["corpus"]["benchmark_version"],
            "case_ids": list(case_ids),
            "presentation": presentation.to_dict(),
            "presentation_hash": presentation_hash,
            "corpus_provenance": {
                "release": {
                    "release_id": release["release_id"],
                    "maturity": release["maturity"],
                    "freeze_status": release["freeze_status"],
                    "release_manifest_sha256": release_validation[
                        "manifest_sha256"
                    ],
                },
                "challenge": {
                    "freeze_status": release["freeze_status"],
                    "maturity": release["maturity"],
                    "presentation": presentation.presentation_id,
                    "pressure_profile": release["pressure"]["profile_id"],
                },
            },
            "memory_implementation_id": implementation[
                "memory_implementation_id"
            ],
            "memory_implementation_hash": implementation[
                "memory_implementation_hash"
            ],
            "release_adoption": {
                "schema_version": ADOPTION_SCHEMA_VERSION,
                "role": role,
                "source_manifest_sha256": source_manifest_sha256,
                "source_seed": source_manifest["seed"],
                "release_seed": release["canonical_seed"],
                "source_files": dict(source_files),
                "provider_visible_surfaces_verified": exact_surfaces,
                "oracle_labels_rescored": oracle_rescored,
                "terminal_actions_rescored": action_rescored,
                "model_outputs_reused": True,
                "network_request_made": False,
            },
        }
    )
    writer = manifest.get("writer")
    if isinstance(writer, dict):
        writer["memory_implementation_id"] = implementation[
            "memory_implementation_id"
        ]
        writer["memory_implementation_hash"] = implementation[
            "memory_implementation_hash"
        ]
    manifest["files"] = {}
    manifest["counts"] = {
        "trials": oracle_rescored,
        "provider_visible_surfaces_verified": exact_surfaces,
        "oracle_labels_rescored": oracle_rescored,
        "terminal_actions_rescored": action_rescored,
    }
    return manifest


def _persist_adopted_run(
    *,
    destination: Path,
    source: Path,
    source_manifest: Mapping[str, Any],
    adopted_manifest: dict[str, Any],
    trials: Sequence[Mapping[str, Any]],
) -> None:
    if destination.exists():
        raise FileExistsError(f"adopted run already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary) / destination.name
        staging.mkdir()
        source_copy = staging / "source"
        source_copy.mkdir()
        shutil.copy2(source / "manifest.json", source_copy / "manifest.json")
        for entry in source_manifest["files"].values():
            path = source / str(entry["path"])
            target = source_copy / str(entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        trials_path = staging / "trials.jsonl"
        write_jsonl(trials_path, trials)
        adopted_manifest["files"] = {
            "trials": {
                "path": trials_path.name,
                "rows": len(trials),
                "sha256": file_hash(trials_path),
            }
        }
        write_json(staging / "manifest.json", adopted_manifest)
        staging.rename(destination)


def _validate_source_manifest(
    source: Path,
    manifest: Mapping[str, Any],
    *,
    expected_study: str,
    expected_executor_target: str,
) -> None:
    if manifest.get("status") != "completed":
        raise ValueError(f"{source}: source run is not completed")
    if manifest.get("domain_id") != "procurement":
        raise ValueError(f"{source}: source domain differs")
    if manifest.get("study") != expected_study:
        raise ValueError(f"{source}: source study differs")
    if manifest.get("executor", {}).get("targets") != [expected_executor_target]:
        raise ValueError(f"{source}: executor target differs")
    if expected_study == "writer" and manifest.get("writer", {}).get(
        "targets"
    ) != ["gptoss_baseten"]:
        raise ValueError(f"{source}: writer target differs")
    if not isinstance(manifest.get("files"), Mapping):
        raise ValueError(f"{source}: source file inventory is missing")
    for required in ("trials", "model_contexts", "evidence", "calls"):
        if required not in manifest["files"]:
            raise ValueError(f"{source}: source artifact {required!r} is missing")


def _validate_source_files(
    source: Path,
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    verified: dict[str, Any] = {}
    for name, entry in manifest["files"].items():
        path = source / str(entry["path"])
        observed_hash = file_hash(path)
        observed_rows = sum(1 for line in path.open(encoding="utf-8") if line.strip())
        if observed_hash != entry["sha256"] or observed_rows != int(entry["rows"]):
            raise ValueError(f"{source}: source artifact {name!r} changed")
        verified[name] = {
            "path": str(entry["path"]),
            "rows": observed_rows,
            "sha256": observed_hash,
        }
    return verified


def _case_map(
    source_cases: Sequence[Any],
    current_cases: Sequence[Any],
) -> dict[str, str]:
    current_by_surface: dict[str, list[Any]] = {}
    for case in current_cases:
        current_by_surface.setdefault(_case_surface(case), []).append(case)
    mapping: dict[str, str] = {}
    for source in source_cases:
        matches = current_by_surface.get(_case_surface(source), [])
        if len(matches) != 1:
            raise ValueError("source case does not map uniquely to the release")
        mapping[source.case_id] = matches[0].case_id
    if len(mapping) != len(current_cases):
        raise ValueError("source and release case sets differ")
    return mapping


def _adopted_trial_maps(
    domain: Any,
    current_cases: Sequence[Any],
    source_trials: Sequence[Mapping[str, Any]],
    adopted_trials: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], dict[tuple[str, str], BenchmarkProbe]]:
    def by_trial_id(
        rows: Sequence[Mapping[str, Any]],
    ) -> dict[str, Mapping[str, Any]]:
        mapped = {
            str(row["metadata"]["core"]["trial_id"]): row for row in rows
        }
        if len(mapped) != len(rows):
            raise ValueError("adopted writer trials repeat a trial ID")
        return mapped

    source_by_id = by_trial_id(source_trials)
    adopted_by_id = by_trial_id(adopted_trials)
    if source_by_id.keys() != adopted_by_id.keys():
        raise ValueError("adopted writer trial inventory changed")
    current_case_by_id = {case.case_id: case for case in current_cases}
    current_probe_by_id = {
        (case.case_id, probe.probe_id): probe
        for case in current_cases
        for probe in domain.corpus.probes(case)
    }
    case_map: dict[str, str] = {}
    probe_map: dict[tuple[str, str], BenchmarkProbe] = {}
    for trial_id, source in source_by_id.items():
        adopted = adopted_by_id[trial_id]
        source_case_id = str(source["case_id"])
        current_case_id = str(adopted["case_id"])
        if current_case_id not in current_case_by_id:
            raise ValueError("adopted trial references an unknown release case")
        prior_case = case_map.setdefault(source_case_id, current_case_id)
        if prior_case != current_case_id:
            raise ValueError("adopted trial case mapping is inconsistent")
        if source["metadata"]["study"].get("evidence_role") != "generated_final":
            continue
        current_probe = current_probe_by_id.get(
            (current_case_id, str(adopted["probe_id"]))
        )
        if current_probe is None:
            raise ValueError("adopted trial references an unknown release probe")
        key = (source_case_id, str(source["probe_id"]))
        prior_probe = probe_map.setdefault(key, current_probe)
        if prior_probe.probe_id != current_probe.probe_id:
            raise ValueError("adopted trial probe mapping is inconsistent")
    if set(case_map.values()) != set(current_case_by_id):
        raise ValueError("adopted writer does not cover the release case set")
    return case_map, probe_map


def _case_surface(case: Any) -> str:
    return content_hash(
        {
            "policy": case.policy,
            "history": render_full_history(case),
            "authorized_issuers": list(case.authorized_issuers),
        }
    )


def _probe_map(
    domain: Any,
    source_cases: Sequence[Any],
    current_cases: Sequence[Any],
    case_map: Mapping[str, str],
) -> dict[tuple[str, str], BenchmarkProbe]:
    current_by_id = {case.case_id: case for case in current_cases}
    mapping: dict[tuple[str, str], BenchmarkProbe] = {}
    for source_case in source_cases:
        current_case = current_by_id[case_map[source_case.case_id]]
        current_probes = tuple(domain.corpus.probes(current_case))
        for source_probe in domain.corpus.probes(source_case):
            source_request = domain.executor.serialize_request(source_probe.request)
            matches = [
                probe
                for probe in current_probes
                if probe.dimension == source_probe.dimension
                and probe.request_scope == source_probe.request_scope
                and domain.executor.serialize_request(probe.request) == source_request
            ]
            if len(matches) != 1:
                raise ValueError("source probe does not map uniquely to the release")
            mapping[(source_case.case_id, source_probe.probe_id)] = matches[0]
    return mapping


def _pressure_rows(
    source: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    entry = manifest["files"].get("pressure_source_jobs")
    return [] if entry is None else _load_jsonl(source / str(entry["path"]))


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Adopt immutable pre-release runs into the frozen release."
    )
    parser.add_argument("--controls-run", type=Path, required=True)
    parser.add_argument("--writer-run", type=Path, required=True)
    parser.add_argument("--alternate-controls-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("results/procurement"))
    args = parser.parse_args()
    print(
        json.dumps(
            adopt_release_runs(
                controls_run=args.controls_run,
                writer_run=args.writer_run,
                alternate_controls_run=args.alternate_controls_run,
                output_root=args.output_root,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
