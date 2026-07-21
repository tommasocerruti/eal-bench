from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).parent
RELEASE_PATH = PACKAGE_DIR / "release.json"
RELEASE_ID = "procurement_v1"
BENCHMARK_CORPUS_VERSION = "benchmark_v1"
CALIBRATION_CORPUS_VERSION = "calibration_v1"
PRESENTATION_ID = "naturalistic_v1"
PRESSURE_PROFILE_ID = "pressure_v1"
CANONICAL_SEED = 20260719

_ACTIVE_SUFFIXES = {
    ".json",
    ".jsonl",
    ".lock",
    ".md",
    ".py",
    ".toml",
    ".yaml",
    ".yml",
}
_FORBIDDEN_ACTIVE_IDENTITIES = (
    re.compile(r"soar[_-]llm", re.IGNORECASE),
    re.compile(r"langmem_profile_v[12]"),
    re.compile("_".join(("custom", "replace", "memory", "v1"))),
    re.compile(r"claim[_ -](?:bearing|ready)", re.IGNORECASE),
    re.compile("_".join(("dev", "v1"))),
    re.compile(r"pilot_v[0-9]+"),
    re.compile(r"naturalistic_v[23]"),
    re.compile("_".join(("cue", "reduced", "v1"))),
    re.compile("_".join(("strong", "business", "pressure", "v1"))),
    re.compile("_".join(("procurement", "scoped", "approvals"))),
)


def _is_active_release_path(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if path.suffix not in _ACTIVE_SUFFIXES:
        return False
    if any(
        part in {
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "build",
            "dist",
            "logs",
            "results",
            "tommaso-local",
        }
        for part in relative.parts
    ):
        return False
    corpus_root = Path("domains/procurement/corpus")
    if relative.is_relative_to(corpus_root):
        return relative.is_relative_to(corpus_root / BENCHMARK_CORPUS_VERSION) or (
            relative.is_relative_to(corpus_root / CALIBRATION_CORPUS_VERSION)
        )
    data_root = Path("domains/procurement/data")
    if relative.is_relative_to(data_root):
        return relative.name in {
            f"{BENCHMARK_CORPUS_VERSION}.jsonl",
            f"{CALIBRATION_CORPUS_VERSION}.jsonl",
        }
    return True


def validate_active_tree() -> dict[str, Any]:
    root = PACKAGE_DIR.parents[1]
    violations: list[str] = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _is_active_release_path(path, root):
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            for pattern in _FORBIDDEN_ACTIVE_IDENTITIES:
                if pattern.search(line):
                    violations.append(
                        f"{path.relative_to(root)}:{line_number}: {pattern.pattern}"
                    )
    if violations:
        raise ValueError(
            "obsolete identities remain in the active release tree:\n"
            + "\n".join(violations)
        )
    return {"status": "passed", "files_scanned": scanned}


def load_release() -> dict[str, Any]:
    value = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("procurement release manifest must be an object")
    return value


def validate_release(domain: Any) -> dict[str, Any]:
    from experiments.authorization_memory.langmem_writer import (
        memory_implementation_manifest,
    )

    active_tree = validate_active_tree()
    release = load_release()
    if set(release) != {
        "schema_version",
        "release_id",
        "domain_id",
        "maturity",
        "freeze_status",
        "canonical_seed",
        "corpus",
        "presentation",
        "pressure",
        "capacity",
        "memory",
        "review",
    }:
        raise ValueError("procurement release manifest fields changed")
    review_path = PACKAGE_DIR / "reviews" / "benchmark_v1.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    expected = {
        "schema_version": "1",
        "release_id": RELEASE_ID,
        "domain_id": "procurement",
        "maturity": review["maturity"],
        "freeze_status": review["freeze_status"],
        "canonical_seed": CANONICAL_SEED,
    }
    if any(release.get(key) != value for key, value in expected.items()):
        raise ValueError("procurement release identity or review status changed")
    files = {
        "benchmark_sha256": PACKAGE_DIR / "data" / "benchmark_v1.jsonl",
        "calibration_sha256": PACKAGE_DIR / "data" / "calibration_v1.jsonl",
        "presentation_sha256": (
            PACKAGE_DIR / "presentations" / "naturalistic_v1.json"
        ),
        "challenge_module_sha256": PACKAGE_DIR / "challenge.py",
        "challenge_data_sha256": PACKAGE_DIR / "challenge_data.py",
        "capacity_sha256": PACKAGE_DIR / "capacity_calibration.json",
        "review_sha256": review_path,
    }
    observed = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in files.items()
    }
    corpus = release["corpus"]
    presentation = release["presentation"]
    pressure = release["pressure"]
    capacity = release["capacity"]
    review_release = release["review"]
    if corpus != {
        "benchmark_version": BENCHMARK_CORPUS_VERSION,
        "benchmark_sha256": observed["benchmark_sha256"],
        "calibration_version": CALIBRATION_CORPUS_VERSION,
        "calibration_sha256": observed["calibration_sha256"],
    }:
        raise ValueError("procurement release corpus hashes changed")
    if presentation != {
        "presentation_id": PRESENTATION_ID,
        "sha256": observed["presentation_sha256"],
    }:
        raise ValueError("procurement release presentation changed")
    if pressure != {
        "profile_id": PRESSURE_PROFILE_ID,
        "challenge_module_sha256": observed["challenge_module_sha256"],
        "challenge_data_sha256": observed["challenge_data_sha256"],
    }:
        raise ValueError("procurement release pressure profile changed")
    if capacity != {
        "artifact_sha256": observed["capacity_sha256"],
        "primary_tokens": 572,
        "tight_tokens": 358,
        "minimum_history_ratio": 8,
    }:
        raise ValueError("procurement release capacity calibration changed")
    if review_release != {
        "status": (
            "complete" if review["freeze_status"] == "frozen" else "pending"
        ),
        "manifest_sha256": observed["review_sha256"],
        "approval_mode": "maintainer",
        "approver_role": review["maintainer_approval"]["approver_role"],
    }:
        raise ValueError("procurement release review declaration changed")
    implementation = memory_implementation_manifest(domain)
    if release["memory"] != {
        "implementation_id": implementation["memory_implementation_id"],
        "implementation_hash": implementation["memory_implementation_hash"],
    }:
        raise ValueError("procurement release memory implementation changed")
    if domain.corpus.default_version != BENCHMARK_CORPUS_VERSION:
        raise ValueError("procurement release is not the default corpus")
    if domain.default_presentation_id != PRESENTATION_ID:
        raise ValueError("procurement release is not the default presentation")
    return {
        "status": "passed",
        "release_id": RELEASE_ID,
        "maturity": release["maturity"],
        "freeze_status": release["freeze_status"],
        "memory_implementation_hash": implementation[
            "memory_implementation_hash"
        ],
        "manifest_sha256": hashlib.sha256(RELEASE_PATH.read_bytes()).hexdigest(),
        "active_tree": active_tree,
    }


if __name__ == "__main__":
    print(json.dumps(validate_active_tree(), indent=2, sort_keys=True))
