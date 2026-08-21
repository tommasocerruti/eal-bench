from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_PATH = Path("results/primary_writer_replication/phase2_precommit.json")


def validate(path: Path) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise TypeError("phase-2 precommit must be a JSON object")
    _equal(plan.get("schema_version"), "eal_phase2_precommit_v1", "schema")
    _equal(plan.get("status"), "approved_not_started", "status")
    budget = plan["budget_usd"]
    _close(budget["expected_total"], 195.486942, "expected total")
    _close(budget["hard_ceiling"], 292.0, "hard ceiling")
    _close(
        budget["replication"]["hard_ceiling"]
        + budget["finance_replacement"]["hard_ceiling"],
        budget["hard_ceiling"],
        "component ceilings",
    )
    replication = plan["replication"]
    _equal(replication["seeds"], [20260821, 20260822], "replication seeds")
    _equal(
        replication["original_primary_seeds"],
        {"procurement": 20260719, "cybersecurity": 20260812, "finance": 20260816},
        "original primary seeds",
    )
    writers = plan["common_configuration"]["writer_targets"]
    executors = plan["common_configuration"]["executor_targets"]
    _equal(len(writers), 5, "writer target count")
    _equal(len(executors), 2, "executor target count")
    replication_routes = len(replication["seeds"]) * len(
        replication["domains"]
    ) * len(writers)
    _equal(replication_routes, replication["route_count"], "replication routes")
    replication_ceiling = sum(
        sum(domain["route_cost_ceiling_usd"].values())
        for domain in replication["domains"].values()
    ) * len(replication["seeds"])
    _close(replication_ceiling, 212.0, "replication route ceilings")
    replacement = plan["finance_replacement"]
    _equal(replacement["seed"], 20260816, "Finance replacement seed")
    replacement_ceiling = sum(replacement["controls_cost_ceiling_usd"].values())
    replacement_ceiling += sum(replacement["writer_cost_ceiling_usd"].values())
    replacement_ceiling += sum(replacement["pressure_cost_ceiling_usd"].values())
    _close(replacement_ceiling, 80.0, "Finance replacement route ceilings")
    _equal(replacement["route_count"], 12, "Finance replacement routes")
    calls = plan["call_accounting"]
    _equal(
        calls["replication"]["scheduled_maximum"]
        + calls["finance_replacement"]["scheduled_maximum"],
        calls["combined"]["scheduled_maximum"],
        "combined scheduled maximum",
    )
    _equal(
        calls["replication"]["expected_final_call_records"]
        + calls["finance_replacement"]["expected_final_call_records"],
        calls["combined"]["expected_final_call_records"],
        "combined expected call records",
    )
    metric = plan["finance_paper_metric"]
    _equal(metric["request_authorized"], False, "Finance authorization predicate")
    _equal(metric["requested_action_taken"], True, "Finance action predicate")
    _equal(metric["uses_unauthorized_action_taken"], False, "legacy metric exclusion")
    _equal(
        metric["historical_pressure_reference"],
        {"numerator": 127, "denominator": 1280, "rate": 0.09921875},
        "historical pressure reference",
    )
    for raw_path, expected_hash in plan["frozen_files_sha256"].items():
        file_path = Path(raw_path)
        if not file_path.is_file():
            raise ValueError(f"precommitted file is missing: {raw_path}")
        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        _equal(actual_hash, expected_hash, f"file hash {raw_path}")
    commands = build_commands(plan)
    _equal(len(commands), 42, "expanded command count")
    _equal(sum(command["paid"] for command in commands), 42, "paid route count")
    return {
        "status": "passed",
        "precommit": str(path),
        "precommit_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "expanded_routes": len(commands),
        "replication_routes": replication_routes,
        "finance_replacement_routes": replacement["route_count"],
        "expected_cost_usd": budget["expected_total"],
        "hard_ceiling_usd": budget["hard_ceiling"],
        "expected_final_call_records": calls["combined"][
            "expected_final_call_records"
        ],
        "scheduled_calls_maximum": calls["combined"]["scheduled_maximum"],
        "finance_metric": "exact_request_unauthorized_submission",
        "network_calls_made": 0,
    }


def build_commands(plan: dict[str, Any]) -> list[dict[str, Any]]:
    common = plan["common_configuration"]
    commands: list[dict[str, Any]] = []
    slug = plan["target_slugs"]
    replacement = plan["finance_replacement"]
    for target in common["executor_targets"]:
        commands.append(
            _command(
                route_id=f"finance-replacement-controls-{slug[target]}",
                args=[
                    "--domain", "finance",
                    "--corpus-version", common["corpus_version"],
                    "--presentation-version", common["presentation_version"],
                    "--study", "controls",
                    "--executor-targets", target,
                    "--executor-runs", "1",
                    "--seed", str(replacement["seed"]),
                    "--tag", f"phase2-finance-replacement-controls-{slug[target]}",
                    "--estimated-cost-usd",
                    str(replacement["controls_cost_ceiling_usd"][target]),
                ],
            )
        )
    for target in common["writer_targets"]:
        writer_id = f"finance-replacement-writer-{slug[target]}"
        commands.append(
            _command(
                route_id=writer_id,
                args=_writer_args(
                    common,
                    domain="finance",
                    target=target,
                    seed=replacement["seed"],
                    tag=f"phase2-finance-replacement-writer-{slug[target]}",
                    ceiling=replacement["writer_cost_ceiling_usd"][target],
                    batch_size=10,
                ),
            )
        )
        commands.append(
            _command(
                route_id=f"finance-replacement-pressure-{slug[target]}",
                depends_on=writer_id,
                args=[
                    "--domain", "finance",
                    "--corpus-version", common["corpus_version"],
                    "--presentation-version", common["presentation_version"],
                    "--study", "pressure",
                    "--source-run", f"{{run_dir:{writer_id}}}",
                    "--pressure-variant", "frontier_loss_mandate",
                    "--batch-size", "10",
                    "--tag", f"phase2-finance-replacement-pressure-{slug[target]}",
                    "--estimated-cost-usd",
                    str(replacement["pressure_cost_ceiling_usd"][target]),
                ],
            )
        )
    replication = plan["replication"]
    for seed in replication["seeds"]:
        for domain, domain_plan in replication["domains"].items():
            for target in common["writer_targets"]:
                commands.append(
                    _command(
                        route_id=f"replication-{seed}-{domain}-{slug[target]}",
                        args=_writer_args(
                            common,
                            domain=domain,
                            target=target,
                            seed=seed,
                            tag=f"phase2-primary-s{seed}-{domain}-{slug[target]}",
                            ceiling=domain_plan["route_cost_ceiling_usd"][target],
                            batch_size=(10 if domain == "finance" else None),
                        ),
                    )
                )
    return commands


def validate_routes(plan: dict[str, Any], *, workers: int = 4) -> dict[str, Any]:
    commands = build_commands(plan)
    runnable = [command for command in commands if command["depends_on"] is None]
    deferred = [command for command in commands if command["depends_on"] is not None]

    def run(command: dict[str, Any]) -> dict[str, Any]:
        local = [
            sys.executable,
            "-m",
            "experiments.run",
            *command["validate"][5:],
        ]
        completed = subprocess.run(
            local,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ValueError(
                f"{command['route_id']} validation failed:\n{completed.stderr}"
            )
        result = json.loads(completed.stdout)
        _equal(result.get("status"), "passed", f"{command['route_id']} status")
        call_plan = result.get("call_plan")
        if not isinstance(call_plan, dict):
            raise ValueError(f"{command['route_id']} has no call plan")
        if "-controls-" in command["route_id"]:
            _equal(call_plan.get("executor_calls"), 288, "Finance control calls")
            _equal(call_plan.get("scheduled_calls_maximum"), 288, "control maximum")
        else:
            domain = command["live"][command["live"].index("--domain") + 1]
            expected = plan["replication"]["domains"][domain]
            _equal(
                call_plan.get("writer_calls_without_repairs"),
                expected["logical_writer_calls_per_target"],
                f"{command['route_id']} logical writer calls",
            )
            _equal(
                call_plan.get("writer_calls_maximum"),
                expected["writer_calls_maximum_per_target"],
                f"{command['route_id']} maximum writer calls",
            )
            _equal(
                call_plan.get("executor_calls_range"),
                expected["executor_calls_range_per_target"],
                f"{command['route_id']} executor range",
            )
            _equal(
                call_plan.get("scheduled_calls_maximum"),
                expected["scheduled_calls_maximum_per_target"],
                f"{command['route_id']} scheduled maximum",
            )
            _equal(
                result.get("writer_checkpoint", {}).get("status"),
                "passed",
                f"{command['route_id']} checkpoint round trip",
            )
            _equal(
                result.get("writer_checkpoint_resume_fixture", {}).get("status"),
                "passed",
                f"{command['route_id']} resume fixture",
            )
        return {
            "route_id": command["route_id"],
            "scheduled_calls_maximum": call_plan["scheduled_calls_maximum"],
            "status": "passed",
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run, runnable))
    return {
        "status": "passed",
        "validated_routes": len(results),
        "source_bound_pressure_routes_deferred": len(deferred),
        "deferred_route_ids": [command["route_id"] for command in deferred],
        "deferred_policy": (
            "validate each exact pressure source after its writer completes and "
            "before the first pressure call"
        ),
        "validated_scheduled_maximum": sum(
            result["scheduled_calls_maximum"] for result in results
        ),
        "network_calls_made": 0,
        "routes": results,
    }


def _writer_args(
    common: dict[str, Any],
    *,
    domain: str,
    target: str,
    seed: int,
    tag: str,
    ceiling: float,
    batch_size: int | None,
) -> list[str]:
    args = [
        "--domain", domain,
        "--corpus-version", common["corpus_version"],
        "--presentation-version", common["presentation_version"],
        "--study", "writer",
        "--writer-targets", target,
        "--executor-targets", ",".join(common["executor_targets"]),
        "--writer-runs", "1",
        "--executor-runs", "1",
        "--writer-max-attempts", "2",
        "--capacity-tier", "primary",
        "--seed", str(seed),
    ]
    if batch_size is not None:
        args.extend(("--batch-size", str(batch_size)))
    args.extend(("--tag", tag, "--estimated-cost-usd", str(ceiling)))
    return args


def _command(
    *,
    route_id: str,
    args: list[str],
    depends_on: str | None = None,
) -> dict[str, Any]:
    live = ["uv", "run", "python", "-m", "experiments.run", *args]
    return {
        "route_id": route_id,
        "depends_on": depends_on,
        "validate": [*live, "--validate-only"],
        "live": live,
        "paid": True,
    }


def _equal(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        raise ValueError(f"{label} mismatch: {actual!r} != {expected!r}")


def _close(actual: float, expected: float, label: str) -> None:
    if abs(float(actual) - float(expected)) > 1e-9:
        raise ValueError(f"{label} mismatch: {actual!r} != {expected!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--precommit", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--print-commands", action="store_true")
    parser.add_argument("--validate-routes", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    result = validate(args.precommit)
    if args.print_commands:
        plan = json.loads(args.precommit.read_text(encoding="utf-8"))
        result["commands"] = build_commands(plan)
    if args.validate_routes:
        plan = json.loads(args.precommit.read_text(encoding="utf-8"))
        result["route_validation"] = validate_routes(plan, workers=args.workers)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
