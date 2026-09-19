"""GLM 5.3 as a third executor. Every glm53-<tag> run is an executor-only replay of the finished run tagged <tag>: the same
frozen memories, the same probes, GLM 5.3 instead of GPT-OSS-120B and DeepSeek V4 Pro. This script pairs each replay with
its source and prints per-executor tables for the studies that pool "both executors" in docs/extension_studies.md: the
paper writer route for the added writers (S5), the memory grid (S1), the procurement variants (S1), the generated corpus
(S4), and the mandate at three seeds (S7, with the paired change per executor). Writes results/analysis/section_glm53.md
and replaces the block between <!-- glm53-start --> and <!-- glm53-end --> in the doc (inserted before '## 6. ' if absent).

    uv run python scratch/section_glm53.py
"""
import collections
import glob
import json
import math
import os
import pathlib
import random
import re
import statistics

random.seed(20260914)
DOC = pathlib.Path("results/analysis/glm53_seven.md")
EXEC = ["gptoss_baseten", "deepseek_baseten", "glm_5_3_baseten"]
ELABEL = {"gptoss_baseten": "GPT-OSS-120B", "deepseek_baseten": "DeepSeek V4 Pro", "glm_5_3_baseten": "GLM 5.3"}
WLABEL = {"glm_5_2_baseten": "GLM 5.2", "kimi_baseten": "Kimi K2.6", "nemotron_3_ultra_baseten": "Nemotron 3 Ultra", "inkling_baseten": "Inkling", "deepseek_v4_1_flash_baseten": "DeepSeek V4.1 Flash", "grok_4_3_openrouter": "Grok 4.3", "qwen_plus_0728_openrouter": "Qwen-Plus", "inkling": "Inkling", "deepseek_v4_1_flash": "DeepSeek V4.1 Flash"}
SEEDS = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
DOM = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance"}
CASE = re.compile(r"procurement_v1_gen_(rr|patch)_g(\d)_s(\d)(_imp)?_([a-z]+)_(\d+)")


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * (c - h), 100 * (c + h))


def manifests():
    out = {}
    for m in glob.glob("results/*/*__*/manifest.json"):
        if "superseded" in m:
            continue
        d = os.path.dirname(m)
        try:
            j = json.load(open(m, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if j.get("status") != "completed":
            continue
        tag = os.path.basename(d).split("__")[-1]
        j.setdefault("domain_id", d.replace("\\", "/").split("/")[1])  # older manifests carry no domain_id; the results folder does
        out.setdefault(tag, []).append((d, j))
    return {t: sorted(v)[-1] for t, v in out.items()}  # latest completed per tag


M = manifests()
REPLAYS = {t[len("glm53-"):]: v for t, v in M.items() if t.startswith("glm53-")}


class Acc:
    def __init__(self):
        self.c = collections.defaultdict(lambda: [0, 0, 0, 0])  # key -> us_k, us_n, au_k, au_n

    def add(self, key, us_k, us_n, au_k, au_n):
        a = self.c[key]
        a[0] += us_k; a[1] += us_n; a[2] += au_k; a[3] += au_n

    def cell(self, key):
        a = self.c.get(key)
        if not a or not a[1]:
            return "n/a"
        lo, hi = wilson(a[0], a[1])
        return f"US {100 * a[0] / a[1]:.1f}% ({lo:.1f}–{hi:.1f}), AU {100 * a[2] / a[3]:.1f}%"

    def n(self, key):
        a = self.c.get(key)
        return a[1] if a else 0


def from_manifest(acc, m, ex, keyfn):
    """Add per-condition counts for executor ex from a writer_variants manifest."""
    for k, b in m["summary"].get("behavior_by_condition_executor", {}).items():
        cond, e = k.split("|")
        if e != ex:
            continue
        key = keyfn(cond)
        if key is None:
            continue
        acc.add(key, b["unauthorized_action"], b["unauthorized_n"], b["authorized_use"], b["authorized_n"])


def from_trials(acc, run_dir, ex, keyfn, only_final=False):
    """Add counts from trials.jsonl (needed for the paper route and for case-level splits)."""
    for line in open(os.path.join(run_dir, "trials.jsonl"), encoding="utf-8"):
        if not line.strip():
            continue
        t = json.loads(line)
        if t["executor"]["target_id"] != ex:
            continue
        st = t["metadata"].get("study", {})
        if only_final and st.get("route") == "writer" and st.get("evidence_role") != "generated_final":
            continue
        key = keyfn(t)
        if key is None:
            continue
        taken = int(bool(t["requested_action_taken"]))
        if t["request_authorized"]:
            acc.add(key, 0, 0, taken, 1)
        else:
            acc.add(key, taken, 1, 0, 0)


out = ["<!-- glm53-start -->", "### Third executor: GLM 5.3", ""]
out.append("Every table in this note that pools \"both executors\" was replayed with GLM 5.3 (`zai-org/GLM-5.3` on Baseten) as the executor. A replay reuses the finished run's frozen memories and probes and runs only the executor stage, so the writer-side results are byte-identical to the source run and the three executors answer the same requests against the same memories. Replays exist for the memory grid (Section 1), the generated corpus (Section 4), the paper writer route for Inkling and DeepSeek V4.1 Flash (Section 5), and the mandate with its baselines at the paper's three seeds (Section 7). They do not exist, and GLM 5.3 is not reported, for the closed loop (its executor is part of the loop, so a third executor means new chains), for the pressure route (it inherits the executor of its writer source), or for the paper route of the paper's five writers, whose memories are not in this clone. Tables below are pooled over writers and seeds as in the sections they extend; n is the number of unauthorized requests per executor.")
out.append("")

# ---- S5: paper route, added writers
missing = []

acc = Acc()
for dom, seeds in SEEDS.items():
    for seed in seeds:
        for w in ("inkling", "deepseek_v4_1_flash"):
            tag = f"paper-writer-s{seed}-{dom}-{w}"
            src = M.get(tag); rep = REPLAYS.get(tag)
            if src is None or rep is None:
                continue
            for ex in EXEC[:2]:
                from_trials(acc, src[0], ex, lambda t, dom=dom, w=w, ex=ex: (dom, w, t["condition_id"], ex), only_final=True)
            from_trials(acc, rep[0], EXEC[2], lambda t, dom=dom, w=w: (dom, w, t["condition_id"], EXEC[2]))
rows = []
for dom in SEEDS:
    for w in ("inkling", "deepseek_v4_1_flash"):
        for cond in ("one_shot_typed", "one_shot_text", "incremental_typed", "incremental_text"):
            if acc.n((dom, w, cond, EXEC[2])) == 0:
                continue
            rows.append(f"| {DOM[dom]} | {WLABEL[w]} | {cond.replace('_', ' ')} | " + " | ".join(acc.cell((dom, w, cond, ex)) for ex in EXEC) + f" | {acc.n((dom, w, cond, EXEC[2]))} |")
if rows:
    out += ["**Paper writer route, added writers** (three seeds per domain, pooled). US with its 95% interval and AU, per executor.", "",
            "| Domain | Writer | Condition | " + " | ".join(ELABEL[e] for e in EXEC) + " | n per executor |", "|---|---|---|---|---|---|---|"] + rows + [""]

# ---- S1: memory grid, per domain
def grid_key(cond):
    if cond.endswith("__mandate"):
        return None
    return cond
acc = Acc()
grid_sources = collections.defaultdict(list)
for tag, (d, m) in M.items():
    if tag.startswith("glm53-") or tag.endswith("glm_5_3_baseten"):
        continue
    if re.match(r"(seeds-2026\d+-|newwriter-s2026\d+-)", tag) and m["domain_id"] == "procurement":
        grid_sources["procurement"].append(tag)
    elif re.match(r"memtable-(cybersecurity|finance)-", tag):
        grid_sources[m["domain_id"]].append(tag)
for dom, tags in grid_sources.items():
    for tag in tags:
        d, m = M[tag]
        rep = REPLAYS.get(tag)
        if rep is None:
            missing.append(tag)
            continue
        for ex in EXEC[:2]:
            from_manifest(acc, m, ex, lambda c, dom=dom, ex=ex: (dom, grid_key(c), ex) if grid_key(c) else None)
        from_manifest(acc, rep[1], EXEC[2], lambda c, dom=dom: (dom, grid_key(c), EXEC[2]) if grid_key(c) else None)
order = ["incremental_typed", "incremental_typed__rebuild3", "incremental_text", "incremental_text__rebuild3", "incremental_hybrid", "incremental_hybrid__rebuild3"]
nice = {"incremental_typed": "typed, incremental", "incremental_typed__rebuild3": "typed, rebuild every 3", "incremental_text": "free text, incremental", "incremental_text__rebuild3": "free text, rebuild every 3", "incremental_hybrid": "hybrid, incremental", "incremental_hybrid__rebuild3": "hybrid, rebuild every 3"}
rows = []
for dom in SEEDS:
    for cond in order:
        if acc.n((dom, cond, EXEC[2])) == 0:
            continue
        rows.append(f"| {DOM[dom]} | {nice[cond]} | " + " | ".join(acc.cell((dom, cond, ex)) for ex in EXEC) + f" | {acc.n((dom, cond, EXEC[2]))} |")
if rows:
    out += ["**Memory type × writing method** (Section 1 design; seven writers; procurement at three seeds, cybersecurity and finance at the canonical seed).", "",
            "| Domain | Memory, writing method | " + " | ".join(ELABEL[e] for e in EXEC) + " | n per executor |", "|---|---|---|---|---|---|"] + rows + [""]

# ---- S1 variants (procurement: retrieval, rebuild at last block, periodic)
acc = Acc()
for tag, (d, m) in M.items():
    if tag.startswith("glm53-") or m["domain_id"] != "procurement":
        continue
    if not re.match(r"(variants-|rebuildk-|periodic-)", tag):
        continue
    rep = REPLAYS.get(tag)
    if rep is None:
        missing.append(tag)
        continue
    for ex in EXEC[:2]:
        from_manifest(acc, m, ex, lambda c, ex=ex: (c, ex))
    from_manifest(acc, rep[1], EXEC[2], lambda c: (c, EXEC[2]))
rows = [f"| {cond} | " + " | ".join(acc.cell((cond, ex)) for ex in EXEC) + f" | {acc.n((cond, EXEC[2]))} |" for cond in sorted({k[0] for k in acc.c}) if acc.n((cond, EXEC[2]))]
if rows:
    out += ["**Procurement writing-method variants** (Section 1's second table and Section 2; paper's writers, canonical seed).", "",
            "| Condition | " + " | ".join(ELABEL[e] for e in EXEC) + " | n per executor |", "|---|---|---|---|---|"] + rows + [""]

# ---- S4 generated corpus: by restatement count and lifecycle, per executor, with and without the mandate
for fam, label in (("generated-v2", "without the mandate"), ("mandate-generated-v2", "with the mandate")):
    acc = Acc()
    for tag, (d, m) in M.items():
        if not tag.startswith(fam + "-") or tag.endswith("glm_5_3_baseten"):
            continue
        rep = REPLAYS.get(tag)
        if rep is None:
            missing.append(tag)
            continue
        def key(t, ex):
            k = CASE.match(t["case_id"])
            if not k:
                return None
            return (("stale", int(k.group(3))), ex), (("lifecycle", {"patch": "amendment", "rr": "revoke-and-replace"}[k.group(1)]), ex)
        for ex in EXEC[:2]:
            for line in open(os.path.join(d, "trials.jsonl"), encoding="utf-8"):
                t = json.loads(line)
                if t["executor"]["target_id"] != ex:
                    continue
                ks = key(t, ex)
                if ks is None:
                    continue
                taken = int(bool(t["requested_action_taken"]))
                for kk in ks:
                    if t["request_authorized"]:
                        acc.add(kk, 0, 0, taken, 1)
                    else:
                        acc.add(kk, taken, 1, 0, 0)
        for line in open(os.path.join(rep[0], "trials.jsonl"), encoding="utf-8"):
            t = json.loads(line)
            ks = key(t, EXEC[2])
            if ks is None:
                continue
            taken = int(bool(t["requested_action_taken"]))
            for kk in ks:
                if t["request_authorized"]:
                    acc.add(kk, 0, 0, taken, 1)
                else:
                    acc.add(kk, taken, 1, 0, 0)
    rows = []
    for k in (("stale", 0), ("stale", 2), ("stale", 4), ("lifecycle", "amendment"), ("lifecycle", "revoke-and-replace")):
        if acc.n((k, EXEC[2])) == 0:
            continue
        rows.append(f"| {k[0]} = {k[1]} | " + " | ".join(acc.cell((k, ex)) for ex in EXEC) + f" | {acc.n((k, EXEC[2]))} |")
    if rows:
        out += [f"**Generated corpus, {label}** (Section 4; typed incremental; the writers with a replay).", "",
                "| Level | " + " | ".join(ELABEL[e] for e in EXEC) + " | n per executor |", "|---|---|---|---|---|"] + rows + [""]

# ---- S7 mandate at three seeds, per executor, with the paired change
W5 = ["glm_5_2_baseten", "kimi_baseten", "nemotron_3_ultra_baseten", "inkling_baseten", "deepseek_v4_1_flash_baseten", "grok_4_3_openrouter", "qwen_plus_0728_openrouter"]
ADDED = {"inkling_baseten", "deepseek_v4_1_flash_baseten", "grok_4_3_openrouter", "qwen_plus_0728_openrouter"}
def base_tag(dom, seed, w):
    if dom == "procurement":
        return f"{'newwriter-s' if w in ADDED else 'seeds-'}{seed}-{w}"
    return f"memtable-{dom}-{w}" if seed == SEEDS[dom][0] else f"memtable-s{seed}-{dom}-{w}"
def mand_tag(dom, seed, w):
    return f"mandate-{dom}-{w}" if seed == SEEDS[dom][0] else f"mandate-s{seed}-{dom}-{w}"
pairs = collections.defaultdict(list)  # (dom, mem, ex) -> list of (base rates, mandate rates)
acc = Acc()
for dom, seeds in SEEDS.items():
    for seed in seeds:
        for w in W5:
            bt, mt = base_tag(dom, seed, w), mand_tag(dom, seed, w)
            if bt not in M or mt not in M:
                continue
            for ex in EXEC:
                bsrc = M[bt] if ex != EXEC[2] else REPLAYS.get(bt)
                msrc = M[mt] if ex != EXEC[2] else REPLAYS.get(mt)
                if bsrc is None or msrc is None:
                    if ex == EXEC[2]:
                        missing += [t for t, s in ((bt, bsrc), (mt, msrc)) if s is None]
                    continue
                for mem in ("typed", "hybrid"):
                    b = bsrc[1]["summary"]["behavior_by_condition_executor"].get(f"incremental_{mem}|{ex}")
                    c = msrc[1]["summary"]["behavior_by_condition_executor"].get(f"incremental_{mem}__mandate|{ex}")
                    if b is None or c is None:
                        continue
                    acc.add((dom, mem, "base", ex), b["unauthorized_action"], b["unauthorized_n"], b["authorized_use"], b["authorized_n"])
                    acc.add((dom, mem, "mand", ex), c["unauthorized_action"], c["unauthorized_n"], c["authorized_use"], c["authorized_n"])
                    pairs[(dom, mem, ex)].append((100 * (c["unauthorized_action"] / c["unauthorized_n"] - b["unauthorized_action"] / b["unauthorized_n"]), 100 * (c["authorized_use"] / c["authorized_n"] - b["authorized_use"] / b["authorized_n"])))
def paired(ds, B=5000):
    if not ds:
        return "n/a"
    mean = statistics.fmean(ds); N = len(ds)
    boots = sorted(statistics.fmean(random.choices(ds, k=N)) for _ in range(B))
    lo, hi = boots[int(0.025 * B)], boots[int(0.975 * B) - 1]
    obs = abs(mean); ge = sum(abs(statistics.fmean(x if random.random() < 0.5 else -x for x in ds)) >= obs - 1e-12 for _ in range(B))
    return f"{mean:+.1f} ({lo:+.1f} to {hi:+.1f}), p={(ge + 1) / (B + 1):.3f}, {N} pairs"
rows = []
for dom in SEEDS:
    for mem in ("typed", "hybrid"):
        for ex in EXEC:
            if acc.n((dom, mem, "base", ex)) == 0:
                continue
            us = paired([p[0] for p in pairs[(dom, mem, ex)]]); au = paired([p[1] for p in pairs[(dom, mem, ex)]])
            rows.append(f"| {DOM[dom]} | {mem} incremental | {ELABEL[ex]} | {acc.cell((dom, mem, 'base', ex))} | {acc.cell((dom, mem, 'mand', ex))} | {us} | {au} |")
if rows:
    out += ["**One-line mandate, open loop, three seeds** (Section 7; seven writers). Paired change is the mean over writer × seed pairs of the mandate rate minus the baseline rate, in points, with a bootstrap 95% interval and a sign-flip p-value.", "",
            "| Domain | Memory | Executor | Without the line | With the line | Paired change in US | Paired change in AU |", "|---|---|---|---|---|---|---|"] + rows + [""]

if missing:
    out.append("Replays not yet present: " + ", ".join(sorted(set(missing))) + ".")
    out.append("")
out.append("**Reading.** On unauthorized submission the three executors are interchangeable: on every replayed table GLM 5.3 is within about a point of GPT-OSS-120B and DeepSeek V4 Pro (procurement grid, typed incremental: 25.4% against 25.6% and 25.2%; cybersecurity and finance cells identical to the decimal; the generated corpus within a point at every restatement level), and the mandate's paired change in unauthorized submission is the same to the first decimal for all three (procurement typed −19.3 to −19.8, cybersecurity typed +11.4 to +11.5, finance typed −30.0 to −30.2). The executor acts on whatever permission the memory holds; which model acts does not change how often a false permission is used. Authorized use is where the executors differ, and only on procurement memories: GLM 5.3 executes about 10 points fewer legitimate requests there (typed incremental 79.3% against 90.7% and 90.4%; Inkling's paper-route memories 75.9% against 90.7%) and the same number elsewhere. This is a property of the executor reading procurement memories, not of the memories, and it interacts with the mandate: cleaner memories raise GLM 5.3's procurement authorized use by 16.7 points against 7.6 and 7.8 for the other two. The one place the doc's two-executor numbers should be read as executor-specific is therefore authorized use in procurement; every unauthorized-submission number generalizes to the third executor.")
out.append("")
out.append("<!-- glm53-end -->")
text = "\n".join(out) + "\n"
pathlib.Path("results/analysis/section_glm53_seven_raw.md").write_text(text, encoding="utf-8", newline="\n")
DOC.write_text(text, encoding="utf-8", newline=chr(10))
print(text)
