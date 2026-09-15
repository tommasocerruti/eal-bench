"""Section 7 mechanism test: the cybersecurity mandate comparison with the oversize write failure removed.

Four arms per writer at the canonical seed, typed incremental, both executors: capacity as calibrated (2,646 tokens) without
and with the one-line mandate (the memtable-cybersecurity-<w> and mandate-cybersecurity-<w> runs), and capacity doubled
(--capacity-scale 2, 5,292 tokens) without and with it (cap2-cybersecurity-<w>, cap2-mandate-cybersecurity-<w>). Reports
unauthorized submission, authorized use, false permissions formed, the paired mandate effect at each capacity, and the
rejected writer updates at the change-set block split into oversize and other. Writes results/analysis/section_cap2.md.
Run from the eal-bench root: PYTHONIOENCODING=utf-8 uv run python scratch/section_cap2.py"""
import collections
import glob
import json
import math
import os
import random
import statistics

random.seed(20260914)
W = ["glm_5_2_baseten", "kimi_baseten", "nemotron_3_ultra_baseten", "inkling_baseten", "deepseek_v4_1_flash_baseten"]
NAME = {"glm_5_2_baseten": "GLM 5.2", "kimi_baseten": "Kimi K2.6", "nemotron_3_ultra_baseten": "Nemotron 3 Ultra", "inkling_baseten": "Inkling", "deepseek_v4_1_flash_baseten": "DeepSeek V4.1 Flash"}
EXEC = ["gptoss_baseten", "deepseek_baseten"]
ARMS = {  # (capacity, mandate) -> (run tag pattern, condition id)
    ("1x", "without"): ("results/cybersecurity/*__memtable-cybersecurity-{w}", "incremental_typed"),
    ("1x", "with"): ("results/cybersecurity/*__mandate-cybersecurity-{w}", "incremental_typed__mandate"),
    ("2x", "without"): ("results/cybersecurity/*__cap2-cybersecurity-{w}", "incremental_typed"),
    ("2x", "with"): ("results/cybersecurity/*__cap2-mandate-cybersecurity-{w}", "incremental_typed__mandate"),
}
CHANGE_BLOCK = 9


def latest_completed(pattern):
    found = []
    for d in sorted(glob.glob(pattern)):
        if "superseded" in d:
            continue
        try:
            m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if m.get("status") == "completed":
            found.append((d, m))
    return found[-1] if found else (None, None)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def cell(m, cond, ex):
    b = m["summary"]["behavior_by_condition_executor"].get(f"{cond}|{ex}")
    if b is None:
        return None
    return {"us_k": b["unauthorized_action"], "us_n": b["unauthorized_n"], "au_k": b["authorized_use"], "au_n": b["authorized_n"], "pe": b.get("provider_errors", 0)}


def rejected(run_dir, cond):
    """Rejected typed updates in this run: (at the change-set block: oversize, other, chains with both attempts rejected; all blocks)."""
    over = other = allb = 0
    by_chain = collections.defaultdict(list)
    for line in open(os.path.join(run_dir, "memory_attempts.jsonl"), encoding="utf-8"):
        a = json.loads(line)
        if a.get("condition_id") != cond or a["status"] not in ("writer_error", "invalid_payload"):
            continue
        allb += 1
        if a["block_index"] != CHANGE_BLOCK:
            continue
        oversize = a["status"] == "invalid_payload" and "capacity is" in json.dumps(a.get("detail"))
        over += oversize
        other += not oversize
        by_chain[(a["case_id"], a.get("writer_run_id"))].append(a["status"])
    double = sum(1 for v in by_chain.values() if len(v) >= 2)
    return {"over": over, "other": other, "double": double, "all": allb}


def rate(acc, k, n):
    if acc[n] == 0:
        return "n/a"
    lo, hi = wilson(acc[k], acc[n])
    return f"{100 * acc[k] / acc[n]:.1f}% ({100 * lo:.1f}–{100 * hi:.1f})"


def paired(pairs, k, n, B=10000):
    d = [100 * (p["m"][k] / p["m"][n] - p["b"][k] / p["b"][n]) for p in pairs if p["m"][n] and p["b"][n]]
    if not d:
        return "n/a"
    mean = statistics.fmean(d)
    N = len(d)
    boots = sorted(statistics.fmean(random.choices(d, k=N)) for _ in range(B))
    lo, hi = boots[int(0.025 * B)], boots[int(0.975 * B) - 1]
    obs = abs(mean)
    ge = sum(1 for _ in range(B) if abs(statistics.fmean(x if random.random() < 0.5 else -x for x in d)) >= obs - 1e-12)
    return f"{mean:+.1f} ({lo:+.1f} to {hi:+.1f}), p={(ge + 1) / (B + 1):.3f}, {N} pairs"


data = {}  # (cap, arm, w) -> dict(cells by executor, formed, rejected, dir)
missing = []
for (cap, arm), (pat, cond) in ARMS.items():
    for w in W:
        d, m = latest_completed(pat.format(w=w))
        if m is None:
            missing.append((cap, arm, w))
            continue
        cells = {ex: cell(m, cond, ex) for ex in EXEC}
        if any(c is None for c in cells.values()):
            missing.append((cap, arm, w, "cells"))
            continue
        data[(cap, arm, w)] = {"cells": cells, "formed": m["summary"]["formation_by_condition"].get(cond, {}).get("formation", 0),
                               "rej": rejected(d, cond), "dir": d, "capacity": m.get("capacity_tokens")}
writers = [w for w in W if all((cap, arm, w) in data for cap in ("1x", "2x") for arm in ("without", "with"))]

out = ["## Cybersecurity mandate with the oversize write failure removed", "",
       f"Canonical seed, typed incremental, both executors, writers with all four arms complete: {', '.join(NAME[w] for w in writers) or 'none yet'}. "
       "Capacity 1x is the calibrated primary capacity (2,646 tokens); 2x doubles it (5,292), so a profile that was rejected for size now fits. "
       "Rejected updates are the writer's attempts returned as invalid output (a patch that cannot be applied, a malformed call) or over capacity; "
       f"the change-set block is block {CHANGE_BLOCK}, the duty officer's signed replacement of the permission list.", ""]


def pool(keys):
    acc = {"us_k": 0, "us_n": 0, "au_k": 0, "au_n": 0, "pe": 0}
    for key in keys:
        for ex in EXEC:
            for k in acc:
                acc[k] += data[key]["cells"][ex][k]
    return acc


out += ["| Capacity | Mandate | US | AU | false permissions formed | rejected updates at the change-set block: oversize / other | chains with both attempts rejected there | rejected updates, all blocks | n per arm |",
        "|---|---|---|---|---|---|---|---|---|"]
for cap in ("1x", "2x"):
    for arm in ("without", "with"):
        keys = [(cap, arm, w) for w in writers]
        if not keys:
            continue
        acc = pool(keys)
        rej = {k: sum(data[key]["rej"][k] for key in keys) for k in ("over", "other", "double", "all")}
        out.append(f"| {cap} | {arm} | {rate(acc, 'us_k', 'us_n')} | {rate(acc, 'au_k', 'au_n')} | {sum(data[key]['formed'] for key in keys)} | {rej['over']} / {rej['other']} | {rej['double']} | {rej['all']} | {acc['us_n']} |")
out.append("")
out += ["Paired change from adding the line (mandate minus baseline), writer-by-executor pairs, bootstrap 95% interval and sign-flip permutation p-value:", "",
        "| Capacity | paired change in US, points | paired change in AU, points |", "|---|---|---|"]
for cap in ("1x", "2x"):
    pairs = [{"b": data[(cap, "without", w)]["cells"][ex], "m": data[(cap, "with", w)]["cells"][ex]} for w in writers for ex in EXEC]
    if pairs:
        out.append(f"| {cap} | {paired(pairs, 'us_k', 'us_n')} | {paired(pairs, 'au_k', 'au_n')} |")
out.append("")
out += ["Paired change from doubling capacity (2x minus 1x), same arm:", "", "| Mandate | paired change in US, points | paired change in AU, points |", "|---|---|---|"]
for arm in ("without", "with"):
    pairs = [{"b": data[("1x", arm, w)]["cells"][ex], "m": data[("2x", arm, w)]["cells"][ex]} for w in writers for ex in EXEC]
    if pairs:
        out.append(f"| {arm} | {paired(pairs, 'us_k', 'us_n')} | {paired(pairs, 'au_k', 'au_n')} |")
out.append("")
out += ["By writer (both executors pooled; US without → with the line, rejected updates at the change-set block oversize / other):", "",
        "| Writer | 1x: US | 1x: AU | 1x: rejected | 2x: US | 2x: AU | 2x: rejected |", "|---|---|---|---|---|---|---|"]
for w in writers:
    row = [NAME[w]]
    for cap in ("1x", "2x"):
        b, m = pool([(cap, "without", w)]), pool([(cap, "with", w)])
        rb, rm = data[(cap, "without", w)]["rej"], data[(cap, "with", w)]["rej"]
        row += [f"{100 * b['us_k'] / b['us_n']:.1f}% → {100 * m['us_k'] / m['us_n']:.1f}%", f"{100 * b['au_k'] / b['au_n']:.1f}% → {100 * m['au_k'] / m['au_n']:.1f}%",
                f"{rb['over']}/{rb['other']} → {rm['over']}/{rm['other']}"]
    out.append("| " + " | ".join(row) + " |")
out.append("")
if missing:
    out.append("Missing arms: " + ", ".join(":".join(map(str, x)) for x in missing))
pe = sum(data[k]["cells"][ex]["pe"] for k in data for ex in EXEC)
out.append(f"Provider-error trials across the arms used: {pe}.")
text = "\n".join(out) + "\n"
os.makedirs("results/analysis", exist_ok=True)
open("results/analysis/section_cap2.md", "w", encoding="utf-8", newline="\n").write(text)
print(text)
