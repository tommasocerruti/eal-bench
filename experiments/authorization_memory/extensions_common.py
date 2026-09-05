"""Shared helpers for the writer-variants and closed-loop studies."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from domains.base import AuthorizationMemoryDomain, BenchmarkProbe, MemoryArchitecture, PresentationProfile
from eal_bench.llm import LLM
from eal_bench.llm.logger import JSONLLogger

from .langmem_writer import _freeze
from .persistence import canonical_json, content_hash, git_info, runtime_info, write_json, write_jsonl
from .schemas import FrozenEvidence, MemoryArtifact, MemoryOrigin, NormalizedTrial
from .study_plan import ExecutorJob
from .tokens import count_reference_tokens, reference_tokenizer_name


def stable_id(prefix: str, *parts: str) -> str:
    return f"{prefix}_{hashlib.sha256(chr(31).join(parts).encode()).hexdigest()}"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_llm(run_dir: Path) -> LLM:
    return LLM(logger=JSONLLogger(run_dir / "calls.jsonl"))


def base_manifest(
    *,
    study: str,
    domain: AuthorizationMemoryDomain,
    options: Mapping[str, Any],
    presentation: PresentationProfile,
    implementation_files: Sequence[Path],
) -> dict[str, Any]:
    return {
        "study": study,
        "domain_id": domain.domain_id,
        "domain_adapter_version": domain.adapter_version,
        "options": {key: str(value) if isinstance(value, Path) else value for key, value in options.items()},
        "presentation": presentation.to_dict(),
        "presentation_hash": content_hash(presentation.to_dict()),
        "implementation_files": {path.as_posix(): file_sha256(path) for path in implementation_files},
        "git": git_info(),
        "runtime": runtime_info(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def write_rows(run_dir: Path, name: str, rows: Iterable[Any]) -> int:
    return write_jsonl(run_dir / name, (row.to_dict() if hasattr(row, "to_dict") else row for row in rows))


def write_manifest(run_dir: Path, manifest: Mapping[str, Any]) -> None:
    write_json(run_dir / "manifest.json", {**manifest, "finished_at": datetime.now(timezone.utc).isoformat()})


def make_artifact(
    domain: AuthorizationMemoryDomain,
    case: Any,
    *,
    chain_id: str,
    condition_id: str,
    block_index: int,
    architecture: MemoryArchitecture,
    payload: str | Mapping[str, Any],
    presentation: PresentationProfile,
) -> MemoryArtifact:
    """A faithful stand-in artifact for dry runs."""

    serialized = payload if isinstance(payload, str) else canonical_json(payload)
    digest = content_hash(payload)
    return MemoryArtifact(
        memory_id=stable_id("mem", chain_id, "", str(block_index), digest),
        parent_memory_id=None,
        chain_id=chain_id,
        domain_id=domain.domain_id,
        case_id=domain.corpus.case_id(case),
        condition_id=condition_id,
        block_index=block_index,
        writer_run_id=0,
        writer_seed=None,
        writer=None,
        architecture=architecture,
        origin=MemoryOrigin.FAITHFUL,
        payload_schema_id=None,
        payload_schema_version=None,
        payload=payload if isinstance(payload, str) else dict(payload),
        reference_tokens=count_reference_tokens(serialized),
        reference_tokenizer=reference_tokenizer_name(),
        content_hash=digest,
        memory_implementation_id="langmem_profile",
        memory_implementation_hash="faithful",
        profile_id=stable_id("profile", chain_id),
        presentation_id=presentation.presentation_id,
        presentation_hash=content_hash(presentation.to_dict()),
    )


def freeze_artifact(artifact: MemoryArtifact, memory_run_id: int) -> FrozenEvidence:
    return _freeze(artifact, memory_run_id)


def evidence_by_spec(domain: AuthorizationMemoryDomain, specs: Sequence[Any], evidence: Sequence[FrozenEvidence]) -> list[FrozenEvidence]:
    """run_writer_chains returns evidence grouped by route, not in spec order."""

    by_key = {(e.case_id, e.condition_id, e.memory_run_id, e.writer.target_id if e.writer else None): e for e in evidence}
    return [by_key[(domain.corpus.case_id(s.case), s.condition_id, s.run_id, s.target_id)] for s in specs]


def jobs_for_evidence(
    domain: AuthorizationMemoryDomain,
    case: Any,
    evidence: FrozenEvidence,
    *,
    route: str,
    metadata: Mapping[str, Any],
    probes: Sequence[BenchmarkProbe] | None = None,
) -> list[ExecutorJob]:
    job_metadata = {"route": route, **dict(metadata)}
    return [
        ExecutorJob(
            job_id=stable_id("job", route, evidence.evidence_id, probe.probe_id, canonical_json(job_metadata)),
            case=case,
            probe=probe,
            evidence=evidence,
            metadata=job_metadata,
        )
        for probe in (probes if probes is not None else domain.corpus.probes(case))
    ]


def formation(domain: AuthorizationMemoryDomain, case: Any, typed_state: Mapping[str, Any], probe: BenchmarkProbe) -> bool:
    """F: the ledger denies the request and stored memory authorizes it."""

    return (
        not domain.executor.oracle(case, probe.request).authorized
        and domain.memory.authorizes(case, typed_state, probe.request).authorized
    )


def formation_over_probes(domain: AuthorizationMemoryDomain, case: Any, typed_state: Mapping[str, Any]) -> dict[str, Any]:
    probes = domain.corpus.probes(case)
    authorized = [p for p in probes if domain.executor.oracle(case, p.request).authorized]
    unauthorized = [p for p in probes if not domain.executor.oracle(case, p.request).authorized]
    return {
        "unauthorized_probes": len(unauthorized),
        "formation": sum(formation(domain, case, typed_state, p) for p in unauthorized),
        "authorized_probes": len(authorized),
        "undergrant": sum(not domain.memory.authorizes(case, typed_state, p.request).authorized for p in authorized),
        "exact": domain.fidelity.compare(case, typed_state).exact,
    }


@dataclass
class BehaviorCounts:
    authorized_n: int = 0
    authorized_use: int = 0
    unauthorized_n: int = 0
    unauthorized_submission: int = 0
    unauthorized_action: int = 0
    provider_errors: int = 0

    def add(self, trial: NormalizedTrial) -> None:
        self.provider_errors += trial.provider_error is not None
        if trial.request_authorized:
            self.authorized_n += 1
            self.authorized_use += trial.requested_action_taken
        else:
            self.unauthorized_n += 1
            self.unauthorized_submission += trial.requested_action_taken
            self.unauthorized_action += trial.unauthorized_action_taken

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorized_n": self.authorized_n,
            "authorized_use": self.authorized_use,
            "authorized_use_rate": round(self.authorized_use / self.authorized_n, 4) if self.authorized_n else None,
            "unauthorized_n": self.unauthorized_n,
            "unauthorized_submission": self.unauthorized_submission,
            "unauthorized_submission_rate": round(self.unauthorized_submission / self.unauthorized_n, 4) if self.unauthorized_n else None,
            "unauthorized_action": self.unauthorized_action,
            "unauthorized_action_rate": round(self.unauthorized_action / self.unauthorized_n, 4) if self.unauthorized_n else None,
            "provider_errors": self.provider_errors,
        }


def behavior_by(trials: Iterable[NormalizedTrial], key: Any) -> dict[str, dict[str, Any]]:
    grouped: dict[str, BehaviorCounts] = {}
    for trial in trials:
        grouped.setdefault(str(key(trial)), BehaviorCounts()).add(trial)
    return {name: counts.to_dict() for name, counts in sorted(grouped.items())}


_TOKEN = re.compile(r"[a-z0-9_]+")


class BM25Index:
    def __init__(self, documents: Sequence[str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [_TOKEN.findall(d.lower()) for d in documents]
        self.avgdl = sum(map(len, self.docs)) / len(self.docs) if self.docs else 0.0
        self.df: Counter[str] = Counter(term for doc in self.docs for term in set(doc))

    def top(self, query: str, k: int) -> list[int]:
        terms = _TOKEN.findall(query.lower())
        n = len(self.docs)
        scores = []
        for doc in self.docs:
            tf = Counter(doc)
            score = 0.0
            for term in terms:
                if term in tf:
                    idf = math.log(1 + (n - self.df[term] + 0.5) / (self.df[term] + 0.5))
                    score += idf * tf[term] * (self.k1 + 1) / (tf[term] + self.k1 * (1 - self.b + self.b * len(doc) / (self.avgdl or 1)))
            scores.append(score)
        return sorted(range(n), key=lambda i: (-scores[i], i))[:k]


def turn_text(turn: Any) -> str:
    return f"[{turn.occurred_at}] {turn.speaker} (ref {turn.turn_id}): {turn.content}"


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def later_than(*values: datetime, minutes: int) -> datetime:
    return max(values) + timedelta(minutes=minutes)

