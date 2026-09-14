"""A blind sample of judged failures for a human to label, so the Section 6 labels can be checked against a person's reading.

Draws a stratified sample (by majority label and domain) from results/diagnosis/v2, rebuilds for each row exactly what the
judges saw (policy, request, true permission state, memory before, the block's messages, the writer's plan and patches,
memory after), and writes:

  results/diagnosis/human_check/sheet.md   the items, without any judge output
  results/diagnosis/human_check/key.csv    the majority label, agreement, and each judge's label and explanation per item
  results/diagnosis/human_check/labels.csv a template (item, label) to fill in

Score a filled template with scratch/human_check_score.py. Run from the eal-bench root:
  PYTHONIOENCODING=utf-8 uv run python scratch/human_check_sheet.py --n 50 --seed 20260914
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import json
import os
import random
from pathlib import Path
from typing import Any

from domains import get_domain
from experiments.diagnose_formation import CAUSES, args_of, attempts_at, block_text, canonical_chains, candidate_requests, compact, rows, written_for

GROUP_SETTING = {
    "open-seeds": "open loop, procurement memory grid", "memtable-cyber": "open loop, cybersecurity memory grid",
    "memtable-finance": "open loop, finance memory grid", "memtable-seeds": "open loop, mandate baselines at the other seeds",
    "open-generated-v2": "open loop, generated corpus", "mandate-open": "open loop, with the mandate",
    "paper-route-new-writers": "paper writer route, added writers", "onepass": "closed loop, one pass",
    "loop-both": "closed loop, three rounds", "loop-mandate": "closed loop, three rounds, with the mandate",
}


def all_rows() -> list[dict[str, Any]]:
    live = {}
    for d in glob.glob("results/*/2026*__*"):
        if "superseded" not in d:
            b = os.path.basename(d)
            live[b.split("__")[-1]] = b
    out = []
    for f in glob.glob("results/diagnosis/v2/*/*.jsonl"):
        group = os.path.basename(os.path.dirname(f))
        tag = os.path.basename(f)[:-6]
        if tag not in live:
            continue
        for line in open(f, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("run") and r["run"] != live[tag]:
                continue
            r["group"] = group
            r["run"] = r.get("run") or live[tag]  # early rows did not record their run directory; the file is named by its tag
            out.append(r)
    return out


def sample(rows_: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Proportional to each (label, domain) stratum, at least two per non-empty stratum, trimmed from the largest strata."""
    rng = random.Random(seed)
    strata: dict[tuple, list] = collections.defaultdict(list)
    for r in rows_:
        strata[(r.get("consensus_cause") or "no majority", r["domain"])].append(r)
    total = len(rows_)
    alloc = {k: max(2, round(n * len(v) / total)) for k, v in strata.items()}
    while sum(alloc.values()) > n:
        k = max(alloc, key=lambda k: (alloc[k], len(strata[k])))
        alloc[k] -= 1
    while sum(alloc.values()) < n:
        k = max(strata, key=lambda k: len(strata[k]) / alloc[k])
        alloc[k] += 1
    picked = []
    for k, v in sorted(strata.items()):
        picked += rng.sample(v, min(alloc[k], len(v)))
    rng.shuffle(picked)
    return picked


class RunCache:
    def __init__(self) -> None:
        self.runs: dict[str, dict[str, Any]] = {}

    def load(self, row: dict[str, Any]) -> dict[str, Any]:
        name = row["run"]
        if name in self.runs:
            return self.runs[name]
        run = Path("results") / row["domain"] / name
        manifest = json.load(open(run / "manifest.json", encoding="utf-8"))
        domain = get_domain(manifest.get("domain_id") or row["domain"])
        corpus_version = manifest.get("corpus_version") or domain.corpus.default_version
        memories = [m for m in rows(run / "memories.jsonl") if m["architecture"] == "typed"]
        written_back = rows(run / "written_back.jsonl")
        ctx = {
            "domain": domain, "presentation": domain.get_presentation(),
            "cases": {domain.corpus.case_id(c): c for c in domain.corpus.load_cases(corpus_version)},
            "attempts": rows(run / "memory_attempts.jsonl"), "written_back": written_back,
            "chains": canonical_chains(memories, rows(run / "memory_states.jsonl"), written_back),
        }
        self.runs[name] = ctx
        return ctx


def payload_for(row: dict[str, Any], ctx: dict[str, Any]) -> dict[str, str]:
    domain, case = ctx["domain"], ctx["cases"][row["case_id"]]
    mems = sorted(ctx["chains"][row["chain_id"]], key=lambda m: m["block_index"])
    wb, _arm = written_for(ctx["written_back"], row["chain_id"], mems)
    base_max = len(list(domain.corpus.blocks(case))) - 1
    b = row["error_block"]

    def state_at(k: int):
        prior = [m for m in mems if m["block_index"] <= k]
        if not prior:
            return domain.memory.empty_typed()
        return domain.memory.parse_typed({kk: v for kk, v in prior[-1]["payload"].items() if kk != "notes"})

    block_attempts = attempts_at(ctx["attempts"], mems, b, wb)
    plan = "\n---\n".join(f"attempt {a['attempt_index']} ({a['status']}): {args_of(a).get('planned_edits', '')}" for a in block_attempts) or "(no attempt recorded)"
    patches = json.dumps([args_of(a).get("patches") for a in block_attempts])[:6000]
    if row["failure"] == "false_authorization":
        request = json.dumps(row["request"])
        truth = compact(domain.memory.faithful_typed(case, through_block_index=min(b, base_max)))
    else:
        what = ("new record, not present before this block" if row["failure"] == "record_born_from_action"
                else "existing record whose cited sources were replaced by the agent's own action lines")
        request = f"(none; the record itself is the failure) {what}: {row.get('record', row.get('record_id'))}"
        truth = compact(domain.memory.faithful_typed(case))
    return {
        "policy": str(getattr(case, "policy", "") or ""), "request": request, "truth": truth,
        "before": compact(state_at(b - 1) if b > 0 else domain.memory.empty_typed()), "block_index": str(b),
        "block": block_text(domain, case, ctx["presentation"], b, wb, base_max)[:14000], "plan": plan[:6000], "patches": patches,
        "after": compact(state_at(b)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=20260914)
    ap.add_argument("--out", default="results/diagnosis/human_check")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows_ = all_rows()
    picked = sample(rows_, a.n, a.seed)
    cache = RunCache()
    sheet = [
        "# Human check of the judged failures\n",
        f"{len(picked)} of {len(rows_)} judged failures, drawn at random within strata of majority label and domain (seed {a.seed}). "
        "Each item shows what the three judges saw and nothing of what they said. For each, pick the one label that best names the writer's error at this block and enter it in `labels.csv`; "
        "then run `scratch/human_check_score.py` to compare with the judges' majority label in `key.csv`. Read the block's messages against the true permission state before looking at the writer's plan.\n",
        "Labels:\n",
    ] + [f"- `{k}`: {v}" for k, v in CAUSES.items()] + [""]
    policies: dict[str, str] = {}
    key_rows, label_rows = [], []
    for i, r in enumerate(picked, 1):
        ctx = cache.load(r)
        p = payload_for(r, ctx)
        policies.setdefault(r["domain"], p["policy"])
        kind = "request the final memory wrongly authorizes" if r["failure"] == "false_authorization" else "record whose only cited sources are the agent's own action lines"
        sheet += [
            f"## Item {i}\n",
            f"Domain: {r['domain']}. Setting: {GROUP_SETTING.get(r['group'], r['group'])}. Block {p['block_index']}"
            + (" (a written-back action line)" if r.get("loop_block") else "") + f". Failure type: {kind}. Policy: see the {r['domain']} policy at the end.\n",
            f"**Request or record**\n\n```\n{p['request']}\n```\n",
            f"**True permission state after this block**\n\n```\n{p['truth']}\n```\n",
            f"**Memory before this block**\n\n```\n{p['before']}\n```\n",
            f"**Block {p['block_index']} messages**\n\n```\n{p['block']}\n```\n",
            f"**Writer plan**\n\n```\n{p['plan']}\n```\n",
            f"**Writer patches**\n\n```\n{p['patches']}\n```\n",
            f"**Memory after this block**\n\n```\n{p['after']}\n```\n",
        ]
        judges = r.get("judges") or {}
        key_rows.append({
            "item": i, "group": r["group"], "run": r["run"], "domain": r["domain"], "writer": r["writer"], "chain_id": r["chain_id"],
            "error_block": r["error_block"], "loop_block": r.get("loop_block"), "failure": r["failure"], "probe_id": r.get("probe_id") or "",
            "record_id": r.get("record_id") or "", "consensus_cause": r.get("consensus_cause") or "", "agreement": r.get("agreement"),
            **{f"{j}_cause": (v or {}).get("cause", "") for j, v in judges.items()},
            **{f"{j}_explanation": (v or {}).get("explanation", "") for j, v in judges.items()},
        })
        label_rows.append({"item": i, "label": ""})
    sheet.append("## Policies\n")
    for d, pol in sorted(policies.items()):
        sheet += [f"### {d}\n", f"```\n{pol}\n```\n"]
    (out / "sheet.md").write_text("\n".join(sheet), encoding="utf-8", newline="\n")
    with open(out / "key.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in key_rows for k in r}, key=lambda k: (k not in ("item",), k)))
        w.writeheader()
        w.writerows(key_rows)
    with open(out / "labels.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["item", "label"])
        w.writeheader()
        w.writerows(label_rows)
    strata = collections.Counter((r.get("consensus_cause") or "no majority", r["domain"]) for r in picked)
    print(f"{len(picked)} items -> {out}")
    for k, v in sorted(strata.items()):
        print(f"  {k[0]:32s} {k[1]:14s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
