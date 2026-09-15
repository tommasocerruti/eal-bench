"""Section 7 (one-line mandate), open loop, at the paper's three seeds per domain: mandate runs against same-seed baselines,
all five Baseten writers, both executors, typed and hybrid incremental. Tables: per domain and memory pooled over seeds with
paired differences (pairs = writer x seed x executor; bootstrap CI and sign-flip permutation on the mean difference); per seed;
per writer. Writes results/analysis/section7_seeds.md. Usage: uv run python scratch/section7_seeds.py"""
import glob
import json
import math
import os
import random
import statistics

random.seed(20260913)
W = ["glm_5_2_baseten", "kimi_baseten", "nemotron_3_ultra_baseten", "inkling_baseten", "deepseek_v4_1_flash_baseten"]
ADDED = {"inkling_baseten", "deepseek_v4_1_flash_baseten"}
LABEL = {"glm_5_2_baseten": "GLM 5.2", "kimi_baseten": "Kimi K2.6", "nemotron_3_ultra_baseten": "Nemotron 3 Ultra",
         "inkling_baseten": "Inkling", "deepseek_v4_1_flash_baseten": "DeepSeek V4.1 Flash"}
SEEDS = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
EXEC = ["gptoss_baseten", "deepseek_baseten"]


def base_pattern(dom, seed, w):
    if dom == "procurement":
        prefix = "newwriter-s" if w in ADDED else "seeds-"
        return f"results/procurement/*__{prefix}{seed}-{w}"
    if seed == SEEDS[dom][0]:
        return f"results/{dom}/*__memtable-{dom}-{w}"
    return f"results/{dom}/*__memtable-s{seed}-{dom}-{w}"


def mandate_pattern(dom, seed, w):
    if seed == SEEDS[dom][0]:
        return f"results/{dom}/*__mandate-{dom}-{w}"
    return f"results/{dom}/*__mandate-s{seed}-{dom}-{w}"


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


def formed(m, cond):
    return m["summary"]["formation_by_condition"].get(cond, {}).get("formation", 0)


pairs = []
missing = []
runs_used = set()
for dom, seeds in SEEDS.items():
    for seed in seeds:
        for w in W:
            bd, bm = latest_completed(base_pattern(dom, seed, w))
            md, mm = latest_completed(mandate_pattern(dom, seed, w))
            if bm is None:
                missing.append(("baseline", dom, seed, w))
            if mm is None:
                missing.append(("mandate", dom, seed, w))
            if bm is None or mm is None:
                continue
            runs_used.update([bd, md])
            for mem in ("typed", "hybrid"):
                for ex in EXEC:
                    b = cell(bm, f"incremental_{mem}", ex)
                    c = cell(mm, f"incremental_{mem}__mandate", ex)
                    if b is None or c is None:
                        missing.append((f"{mem}|{ex}", dom, seed, w))
                        continue
                    first = ex == EXEC[0]  # formation is per condition, not per executor: count it once per pair of runs
                    pairs.append({"dom": dom, "mem": mem, "seed": seed, "w": w, "ex": ex, "b": b, "m": c,
                                  "form_b": formed(bm, f"incremental_{mem}") if first else 0,
                                  "form_m": formed(mm, f"incremental_{mem}__mandate") if first else 0})


def pool(ps, side):
    acc = {"us_k": 0, "us_n": 0, "au_k": 0, "au_n": 0, "pe": 0}
    for p in ps:
        for k in acc:
            acc[k] += p[side][k]
    return acc


def rate(acc, k, n):
    if acc[n] == 0:
        return "n/a"
    lo, hi = wilson(acc[k], acc[n])
    return f"{100 * acc[k] / acc[n]:.1f}% ({100 * lo:.1f}–{100 * hi:.1f})"


def paired(ps, k, n, B=10000):
    d = [100 * (p["m"][k] / p["m"][n] - p["b"][k] / p["b"][n]) for p in ps if p["m"][n] and p["b"][n]]
    if not d:
        return "n/a"
    mean = statistics.fmean(d)
    N = len(d)
    boots = sorted(statistics.fmean(random.choices(d, k=N)) for _ in range(B))
    lo, hi = boots[int(0.025 * B)], boots[int(0.975 * B) - 1]
    obs = abs(mean)
    ge = 0
    for _ in range(B):
        if abs(statistics.fmean(x if random.random() < 0.5 else -x for x in d)) >= obs - 1e-12:
            ge += 1
    p = (ge + 1) / (B + 1)
    return f"{mean:+.1f} ({lo:+.1f} to {hi:+.1f}), p={p:.3f}, {N} pairs"


def formed_sum(ps, key):
    return sum(p[key] for p in ps)


out = ["## Section 7 open loop at three seeds per domain", ""]
out.append(f"Runs used: {len(runs_used)}. Pairs (writer x seed x executor x memory): {len(pairs)}. "
           f"Provider-error trials: {sum(p['b']['pe'] + p['m']['pe'] for p in pairs)}.")
if missing:
    out.append("Missing: " + "; ".join(f"{a} {b} s{c} {d}" for a, b, c, d in missing))
out += ["", "### Pooled over the three seeds, five writers, both executors", ""]
out.append("| Domain | Memory | US without | US with mandate | AU without | AU with mandate | false permissions formed, without → with | paired change in US, points | paired change in AU, points |")
out.append("|---|---|---|---|---|---|---|---|---|")
for dom in SEEDS:
    for mem in ("typed", "hybrid"):
        ps = [p for p in pairs if p["dom"] == dom and p["mem"] == mem]
        if not ps:
            continue
        b = pool(ps, "b")
        m = pool(ps, "m")
        out.append(f"| {dom} | {mem} incremental | {rate(b, 'us_k', 'us_n')}, n={b['us_n']} | {rate(m, 'us_k', 'us_n')}, n={m['us_n']} | "
                   f"{rate(b, 'au_k', 'au_n')} | {rate(m, 'au_k', 'au_n')} | {formed_sum(ps, 'form_b')} → {formed_sum(ps, 'form_m')} | "
                   f"{paired(ps, 'us_k', 'us_n')} | {paired(ps, 'au_k', 'au_n')} |")
out += ["", "### Per seed (five writers, both executors, typed and hybrid pooled)", ""]
out.append("| Domain | Seed | US without → with | AU without → with | false permissions formed, without → with | n per arm |")
out.append("|---|---|---|---|---|---|")
for dom, seeds in SEEDS.items():
    for seed in seeds:
        ps = [p for p in pairs if p["dom"] == dom and p["seed"] == seed]
        if not ps:
            continue
        b = pool(ps, "b")
        m = pool(ps, "m")
        tag = " (canonical)" if seed == seeds[0] else ""
        out.append(f"| {dom} | {seed}{tag} | {rate(b, 'us_k', 'us_n')} → {rate(m, 'us_k', 'us_n')} | {rate(b, 'au_k', 'au_n')} → {rate(m, 'au_k', 'au_n')} | "
                   f"{formed_sum(ps, 'form_b')} → {formed_sum(ps, 'form_m')} | {b['us_n']} |")
out += ["", "### Per writer (three seeds, both executors, typed and hybrid pooled)", ""]
out.append("| Domain | Writer | US without → with | AU without → with | false permissions formed, without → with | n per arm |")
out.append("|---|---|---|---|---|---|")
for dom in SEEDS:
    for w in W:
        ps = [p for p in pairs if p["dom"] == dom and p["w"] == w]
        if not ps:
            continue
        b = pool(ps, "b")
        m = pool(ps, "m")
        out.append(f"| {dom} | {LABEL[w]} | {rate(b, 'us_k', 'us_n')} → {rate(m, 'us_k', 'us_n')} | {rate(b, 'au_k', 'au_n')} → {rate(m, 'au_k', 'au_n')} | "
                   f"{formed_sum(ps, 'form_b')} → {formed_sum(ps, 'form_m')} | {b['us_n']} |")
text = "\n".join(out) + "\n"
os.makedirs("results/analysis", exist_ok=True)
open("results/analysis/section7_seeds.md", "w", encoding="utf-8", newline="\n").write(text)
print(text)
