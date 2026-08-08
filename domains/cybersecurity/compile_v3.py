"""Compile compact Cybersecurity v3 sources into deterministic case specifications."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


PACKAGE_DIR = Path(__file__).parent
SOURCE_DIR = PACKAGE_DIR / "corpus_v3"
DATA_DIR = PACKAGE_DIR / "data"
SOURCE_VERSIONS = ("calibration_v3", "difficulty_dev_v3", "benchmark_v1_base")
ARCHETYPES = {
    "containment_handoff",
    "patch_rollback",
    "credential_rotation",
    "tenant_recovery",
}
_ACTIONS = {
    "isolate_host",
    "block_indicator",
    "deploy_patch",
    "rotate_key",
    "disable_service_token",
    "capture_memory",
    "restrict_network",
    "restart_service",
}
_REQUIRED_ASSETS = {"b_keep", "b_removed", "d_current", "a_decoy"}
_REQUIRED_ACTIONS = {"b", "c_obsolete", "d_current", "a_decoy"}
_REQUIRED_VULNERABILITIES = {"b", "d_current", "a_decoy"}
_REQUIRED_ENVIRONMENTS = {"b", "d"}
_REQUIRED_PRESSURE = {"impact", "deadline", "recovery_advantage", "escalation_delay"}


def compile_version(version: str) -> dict[str, Any]:
    if version not in SOURCE_VERSIONS:
        raise ValueError(f"unsupported v3 source version: {version!r}")
    source_path = SOURCE_DIR / f"{version}.yaml"
    source = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(source, dict) or source.get("schema_version") != "cybersecurity_source_v3":
        raise ValueError(f"{source_path}: invalid source schema")
    if source.get("corpus_version") != version or not isinstance(source.get("cases"), list):
        raise ValueError(f"{source_path}: corpus identity is invalid")
    rows = [_normalize_case(dict(row), version) for row in source["cases"]]
    case_ids = [row["case_id"] for row in rows]
    families = [row["family"] for row in rows]
    if len(case_ids) != len(set(case_ids)) or len(families) != len(set(families)):
        raise ValueError(f"{source_path}: case IDs and families must be disjoint")
    expected_count = (
        16
        if version == "benchmark_v1_base"
        else 8
        if version == "difficulty_dev_v3"
        else 4
    )
    if len(rows) != expected_count:
        raise ValueError(f"{version} must contain exactly {expected_count} families")
    counts = Counter(row["archetype"] for row in rows)
    expected_per_archetype = (
        4
        if version == "benchmark_v1_base"
        else 2
        if version == "difficulty_dev_v3"
        else 1
    )
    if set(counts) != ARCHETYPES or set(counts.values()) != {expected_per_archetype}:
        raise ValueError(f"{version}: lifecycle archetypes are not balanced")
    return {
        "schema_version": "cybersecurity_compiled_v3",
        "corpus_version": version,
        "split": str(source["split"]),
        "cases": rows,
    }


def compile_all(*, check: bool = False) -> dict[str, str]:
    results = {}
    for version in SOURCE_VERSIONS:
        rendered = json.dumps(compile_version(version), indent=2, sort_keys=True) + "\n"
        destination = DATA_DIR / f"{version}.json"
        if check:
            if not destination.is_file() or destination.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"{destination}: generated artifact is stale")
        else:
            destination.write_text(rendered, encoding="utf-8")
        results[version] = str(destination)
    return results


def _normalize_case(row: dict[str, Any], version: str) -> dict[str, Any]:
    required = {
        "case_id",
        "family",
        "archetype",
        "organization",
        "system_name",
        "tenant_id",
        "incident_id",
        "start_at",
        "grants",
        "assets",
        "environments",
        "actions",
        "vulnerabilities",
        "pressure",
    }
    if set(row) != required:
        raise ValueError(f"{row.get('case_id', '<unknown>')}: source fields differ from v3 schema")
    row["start_at"] = _parse_timestamp(row["start_at"])
    _exact_keys(row, "grants", {"a", "b", "c", "d", "e"})
    _exact_keys(row, "assets", _REQUIRED_ASSETS)
    _exact_keys(row, "environments", _REQUIRED_ENVIRONMENTS)
    _exact_keys(row, "actions", _REQUIRED_ACTIONS)
    _exact_keys(row, "vulnerabilities", _REQUIRED_VULNERABILITIES)
    _exact_keys(row, "pressure", _REQUIRED_PRESSURE)
    if row["archetype"] not in ARCHETYPES:
        raise ValueError(f"{row['case_id']}: unsupported lifecycle archetype")
    scalar_values = [
        row[key]
        for key in (
            "case_id",
            "family",
            "archetype",
            "organization",
            "system_name",
            "tenant_id",
            "incident_id",
        )
    ]
    nested_values = [
        value
        for key in (
            "grants",
            "assets",
            "environments",
            "actions",
            "vulnerabilities",
            "pressure",
        )
        for value in row[key].values()
    ]
    if any(not isinstance(value, str) or not value.strip() for value in (*scalar_values, *nested_values)):
        raise ValueError(f"{row['case_id']}: source values must be non-empty strings")
    for field in ("grants", "assets", "environments", "vulnerabilities"):
        if len(set(row[field].values())) != len(row[field]):
            raise ValueError(f"{row['case_id']}: {field} values must be unique")
    if not set(row["actions"].values()) <= _ACTIONS:
        raise ValueError(f"{row['case_id']}: unsupported response action")
    normalized = json.loads(json.dumps(row, sort_keys=True))
    normalized["corpus_version"] = version
    normalized["lifecycle_template"] = "four_operation_state_swap_v3"
    return normalized


def _exact_keys(row: dict[str, Any], field: str, expected: set[str]) -> None:
    value = row.get(field)
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{row.get('case_id', '<unknown>')}: {field} keys differ from v3 schema")


def _parse_timestamp(value: Any) -> str:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("start_at must include a timezone")
    return parsed.isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(compile_all(check=args.check), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
