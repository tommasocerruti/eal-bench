"""Pool every extension study over all seven writers from the completed runs. Writes scratch/iclr_seven/parity_pool.json.
Rerunnable: missing runs are reported, not invented. Numbers here feed apply_parity.py (paper) and the figure scripts."""
import collections
import csv
import glob
import json
import os
import sys

sys.path.insert(0, ".")
from analysis.plot_mitigation_frontier import latest_completed  # noqa: E402

W7 = ["glm_5_2_baseten", "kimi_baseten", "nemotron_3_ultra_baseten", "inkling_baseten", "deepseek_v4_1_flash_baseten", "grok_4_3_openrouter", "qwen_plus_0728_openrouter"]
NEWWRITER = {"inkling_baseten", "deepseek_v4_1_flash_baseten", "grok_4_3_openrouter", "qwen_plus_0728_openrouter"}  # procurement runs tagged newwriter-s<seed>-<w>
SEEDS = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
DOMS = list(SEEDS)
out = {"missing": []}


def base_pattern(dom, seed, w):
    if dom == "procurement":
        return f"results/procurement/*__{'newwriter-s' if w in NEWWRITER else 'seeds-'}{seed}-{w}"
    return f"results/{dom}/*__memtable-{dom}-{w}" if seed == SEEDS[dom][0] else f"results/{dom}/*__memtable-s{seed}-{dom}-{w}"


def mandate_pattern(dom, seed, w):
    return f"results/{dom}/*__mandate-{dom}-{w}" if seed == SEEDS[dom][0] else f"results/{dom}/*__mandate-s{seed}-{dom}-{w}"


def add(acc, m, cond):
    b = m["summary"]["behavior_by_condition"].get(cond)
    if b is None:
        return False
    acc["ua_k"] += b["unauthorized_action"]; acc["ua_n"] += b["unauthorized_n"]; acc["la_k"] += b["authorized_use"]; acc["la_n"] += b["authorized_n"]
    return True


def zero():
    return {"ua_k": 0, "ua_n": 0, "la_k": 0, "la_n": 0}


# ------------------------------------------------------------------ memory designs and the instruction, per domain and pooled
conds = ("typed", "hybrid", "rebuild", "instruction", "instruction_hybrid", "typed_matched_instruction", "hybrid_matched_instruction")
acc = {d: {c: zero() for c in conds} for d in DOMS + ["pooled"]}
runs_used = collections.Counter(); per_writer = collections.defaultdict(lambda: collections.defaultdict(zero))
for dom, seeds in SEEDS.items():
    for seed in seeds:
        for w in W7:
            bm = latest_completed(base_pattern(dom, seed, w))
            if bm is None:
                out["missing"].append(f"base {dom} {seed} {w}"); continue
            for tgt in (dom, "pooled"):
                add(acc[tgt]["typed"], bm, "incremental_typed"); add(acc[tgt]["hybrid"], bm, "incremental_hybrid")
                rm = bm if "incremental_typed__rebuild3" in bm["summary"]["behavior_by_condition"] else latest_completed(f"results/{dom}/*__rebuild3-s{seed}-{dom}-{w}")
                if rm is not None and add(acc[tgt]["rebuild"], rm, "incremental_typed__rebuild3"):
                    runs_used["rebuild"] += tgt == dom
                elif tgt == dom:
                    out["missing"].append(f"rebuild {dom} {seed} {w}")
            add(per_writer[w][dom], bm, "incremental_typed")
            runs_used["base"] += 1
            mm = latest_completed(mandate_pattern(dom, seed, w))
            if mm is None:
                out["missing"].append(f"instruction {dom} {seed} {w}"); continue
            for tgt in (dom, "pooled"):
                add(acc[tgt]["instruction"], mm, "incremental_typed__mandate"); add(acc[tgt]["instruction_hybrid"], mm, "incremental_hybrid__mandate")
                add(acc[tgt]["typed_matched_instruction"], bm, "incremental_typed"); add(acc[tgt]["hybrid_matched_instruction"], bm, "incremental_hybrid")
            runs_used["instruction"] += 1


def rates(a):
    return {"ua": 100 * a["ua_k"] / a["ua_n"] if a["ua_n"] else None, "la": 100 * a["la_k"] / a["la_n"] if a["la_n"] else None, "ua_n": a["ua_n"], "la_n": a["la_n"]}


out["designs"] = {d: {c: rates(a) for c, a in per.items()} for d, per in acc.items()}
out["runs_used"] = dict(runs_used)
out["typed_by_writer"] = {w: {d: rates(a) for d, a in per.items()} for w, per in per_writer.items()}

# ------------------------------------------------------------------ hybrid cells for the writer-executor plates (canonical seed)
cells = {}
for dom in DOMS:
    seed = SEEDS[dom][0]
    for w in W7:
        m = latest_completed(base_pattern(dom, seed, w))
        if m is None:
            continue
        for key, b in m["summary"].get("behavior_by_condition_executor", {}).items():
            cond, ex = key.split("|")
            if cond == "incremental_hybrid":
                cells[f"{dom}|{w}|{ex}"] = {"la_k": b["authorized_use"], "la_n": b["authorized_n"], "ua_k": b["unauthorized_action"], "ua_n": b["unauthorized_n"]}
out["hybrid_cells"] = cells

# ------------------------------------------------------------------ independent review over all writers (typed pools)
ind = {k: [0, 0] for k in (2, 4, 8)}
rows = list(csv.DictReader(open("results/procurement/20260815__deepseek_independent_ttc_k8_analysis_v2/selection_by_pool.csv", encoding="utf-8")))
for r in rows:
    if r["method"] == "deepseek_review" and "typed" in r["condition_id"]:
        k = int(r["k"]); ind[k][0] += r["selected_exact"] == "True"; ind[k][1] += 1
for w in ("inkling", "deepseek_v4_1_flash"):
    for k in (2, 4, 8):
        ds = [d for d in glob.glob(f"results/procurement/*__authorization-memory-writer_ttc__procurement-v1-{w}-ttc-k{k}-review") if "superseded" not in d]
        if not ds:
            out["missing"].append(f"review {w} k{k}"); continue
        pools = collections.defaultdict(dict)
        for l in open(sorted(ds)[-1] + "/selection_fidelity.jsonl", encoding="utf-8"):
            r = json.loads(l)
            if "typed" in r["condition_id"] and r["selected"]:
                pools[(r["case_id"], r["condition_id"])] = bool(r["exact"])
        ind[k][0] += sum(pools.values()); ind[k][1] += len(pools)
out["independent_review_selected_exact"] = {str(k): {"k_exact": v[0], "pools": v[1], "rate": 100 * v[0] / v[1] if v[1] else None} for k, v in ind.items()}

# ------------------------------------------------------------------ event sourcing per writer and domain (behavior, from the analysis directories; Inkling reruns included when present)
ev = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0, 0]))
for d in sorted(glob.glob("results/analysis/event_sourcing/event-s*")):
    d = d.replace(chr(92), "/"); dom = d.split("-")[-1] if not d.endswith("inkling") else d.split("-")[-2]
    for l in open(d + "/paired_metrics.jsonl", encoding="utf-8"):
        r = json.loads(l); sv = json.loads(r["stratum_value"]) if isinstance(r["stratum_value"], str) else r["stratum_value"]
        if r["metric"] not in ("authorized_use", "unauthorized_submission"):
            continue
        a = ev[sv.get("target_id")][(dom, r["metric"])]
        a[0] += r["typed_incremental"]["numerator"]; a[1] += r["typed_incremental"]["denominator"]; a[2] += r["event_sourced"]["numerator"]; a[3] += r["event_sourced"]["denominator"]
out["event_by_writer"] = {w: {f"{k[0]}|{k[1]}": v for k, v in per.items()} for w, per in ev.items()}


# ------------------------------------------------------------------ typed against hybrid per writer and domain (three seeds pooled)
tv = collections.defaultdict(lambda: {"typed": zero(), "hybrid": zero()})
for dom, seeds in SEEDS.items():
    for seed in seeds:
        for w in W7:
            bm = latest_completed(base_pattern(dom, seed, w))
            if bm is None:
                continue
            add(tv[(w, dom)]["typed"], bm, "incremental_typed"); add(tv[(w, dom)]["hybrid"], bm, "incremental_hybrid")
out["typed_vs_hybrid_by_writer"] = {f"{w}|{d}": {c: rates(a) for c, a in per.items()} for (w, d), per in tv.items()}

# ------------------------------------------------------------------ closed loop: executor refusal share per domain (action arm, all rounds) and records under the instruction
ref = collections.defaultdict(collections.Counter)
for d in glob.glob("results/*/*__rounds3v2-both-*"):
    d = d.replace(chr(92), "/")
    if "superseded" in d:
        continue
    try:
        m = json.load(open(d + "/manifest.json", encoding="utf-8"))
    except Exception:
        continue
    if m.get("status") != "completed":
        continue
    dom = d.split("results/")[1].split("/")[0]
    for l in open(d + "/trials.jsonl", encoding="utf-8"):
        t = json.loads(l); st = t["metadata"]["study"]
        if st.get("loop") != "closed" or st.get("loop_writer") != "same":
            continue
        ref[dom][t["decision"]] += 1; ref[dom]["_n"] += 1
out["refusal_share"] = {dom: {"escalate_or_decline": 100 * (c["escalate"] + c["decline"]) / c["_n"], "execute_requested": 100 * c["execute_requested"] / c["_n"], "n": c["_n"]} for dom, c in ref.items() if c["_n"]}
rows = list(csv.DictReader(open("results/diagnosis/failures.csv", encoding="utf-8")))
out["records_from_own_lines"] = {"without_instruction_action_arm": sum(1 for r in rows if r["group"] == "loop-both" and r.get("record_id") and r["arm"] == "action"),
                                 "without_instruction_control": sum(1 for r in rows if r["group"] == "loop-both" and r.get("record_id") and r["arm"] == "neutral"),
                                 "with_instruction": sum(1 for r in rows if r["group"] == "loop-mandate" and r.get("record_id"))}
json.dump(out, open("scratch/iclr_seven/parity_pool.json", "w", encoding="utf-8"), indent=1)
print("refusal:", out["refusal_share"]); print("records:", out["records_from_own_lines"])

print("runs used:", dict(runs_used)); print("missing:", len(out["missing"]))
for m in out["missing"][:40]:
    print("  ", m)
for d in DOMS + ["pooled"]:
    r = out["designs"][d]
    print(d, {c: (f"{v['ua']:.1f}/{v['la']:.1f}" if v["ua"] is not None else "-") for c, v in r.items()})
print("independent review:", out["independent_review_selected_exact"])
