"""Table 33 (tab:mandate-pooled) with the writer-route typed-incremental baseline of Table 5 as the 'without' arm, so the
paper reports one typed-incremental baseline. Pairs are writer x seed with both executors pooled (21 per row), because the
frozen five-writer counts (results/<domain>/paper/counts.json) carry writer x seed cells only. Hybrid rows keep the
design-run baseline (the only hybrid-without-instruction data) at the same pairing unit."""
import glob, json, os, random, statistics, pathlib, re, collections
random.seed(7)
ROOT = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench"); ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
os.chdir(ROOT)
W5 = ["glm_5_2_baseten", "kimi_baseten", "nemotron_3_ultra_baseten", "grok_4_3_openrouter", "qwen_plus_0728_openrouter"]
ADDED = {"inkling_baseten": "inkling", "deepseek_v4_1_flash_baseten": "deepseek_v4_1_flash"}
SEEDS = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
EXEC = ["gptoss_baseten", "deepseek_baseten"]

def latest_completed(pattern):
    found = []
    for d in sorted(glob.glob(pattern)):
        if "superseded" in d or "glm53" in d: continue
        try: m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
        except (OSError, json.JSONDecodeError): continue
        if m.get("status") == "completed": found.append((d, m))
    return found[-1] if found else (None, None)

def base_pattern(dom, seed, w):  # design-run baseline (hybrid rows)
    if dom == "procurement":
        prefix = "newwriter-s" if (w in ADDED or w.endswith("_openrouter")) else "seeds-"
        return f"results/procurement/*__{prefix}{seed}-{w}"
    return f"results/{dom}/*__memtable-{dom}-{w}" if seed == SEEDS[dom][0] else f"results/{dom}/*__memtable-s{seed}-{dom}-{w}"

def mandate_pattern(dom, seed, w):
    return f"results/{dom}/*__mandate-{dom}-{w}" if seed == SEEDS[dom][0] else f"results/{dom}/*__mandate-s{seed}-{dom}-{w}"

def cell_sum(m, cond):
    acc = {"us_k": 0, "us_n": 0, "au_k": 0, "au_n": 0}
    for ex in EXEC:
        b = m["summary"]["behavior_by_condition_executor"][f"{cond}|{ex}"]
        acc["us_k"] += b["unauthorized_action"]; acc["us_n"] += b["unauthorized_n"]; acc["au_k"] += b["authorized_use"]; acc["au_n"] += b["authorized_n"]
    return acc

def paper_cell(dom, seed, w):
    if w in W5:
        c = json.load(open(f"results/{dom}/paper/counts.json", encoding="utf-8"))[f"{dom}-s{seed}-{w}"]["by_condition"]["incremental_typed"]
        assert c["provider_error_trials"] == 0
        return {"us_k": c["unauthorized_submissions"], "us_n": c["unauthorized_trials"], "au_k": c["authorized_use"], "au_n": c["authorized_trials"]}
    d, m = latest_completed(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{ADDED[w]}")
    acc = {"us_k": 0, "us_n": 0, "au_k": 0, "au_n": 0}
    for line in open(os.path.join(d, "trials.jsonl"), encoding="utf-8"):
        t = json.loads(line)
        if t["metadata"]["study"].get("evidence_role") != "generated_final" or t["condition_id"] != "incremental_typed" or t.get("provider_error"): continue
        if t["request_authorized"]: acc["au_n"] += 1; acc["au_k"] += bool(t["requested_action_taken"])
        else: acc["us_n"] += 1; acc["us_k"] += bool(t["requested_action_taken"])
    return acc

def paired(ps, k, n, B=10000):
    d = [100 * (p["m"][k] / p["m"][n] - p["b"][k] / p["b"][n]) for p in ps]
    mean = statistics.fmean(d); N = len(d)
    boots = sorted(statistics.fmean(random.choices(d, k=N)) for _ in range(B))
    return mean, boots[int(0.025 * B)], boots[int(0.975 * B) - 1], N

def pool(ps, side, k, n):
    return 100 * sum(p[side][k] for p in ps) / sum(p[side][n] for p in ps)

rows = {}; per_seed_dir = {}
for dom, seeds in SEEDS.items():
    for mem in ("typed", "hybrid"):
        ps = []
        for seed in seeds:
            for w in W5 + list(ADDED):
                md, mm = latest_completed(mandate_pattern(dom, seed, w)); assert mm is not None, (dom, seed, w)
                m = cell_sum(mm, f"incremental_{mem}__mandate")
                if mem == "typed": b = paper_cell(dom, seed, w)
                else:
                    bd, bm = latest_completed(base_pattern(dom, seed, w)); assert bm is not None, (dom, seed, w); b = cell_sum(bm, "incremental_hybrid")
                ps.append({"b": b, "m": m, "seed": seed, "w": w})
        us = paired(ps, "us_k", "us_n"); au = paired(ps, "au_k", "au_n")
        rows[(dom, mem)] = {"ua_without": pool(ps, "b", "us_k", "us_n"), "ua_with": pool(ps, "m", "us_k", "us_n"), "la_without": pool(ps, "b", "au_k", "au_n"), "la_with": pool(ps, "m", "au_k", "au_n"), "dua": us, "dla": au,
                            "n_without": sum(p["b"]["us_n"] for p in ps), "n_with": sum(p["m"]["us_n"] for p in ps)}
        per_seed_dir[(dom, mem)] = [(seed, pool([p for p in ps if p["seed"] == seed], "b", "us_k", "us_n"), pool([p for p in ps if p["seed"] == seed], "m", "us_k", "us_n")) for seed in seeds]
        r = rows[(dom, mem)]
        print(f"{dom:14s} {mem:6s} UA {r['ua_without']:.1f} -> {r['ua_with']:.1f}  LA {r['la_without']:.1f} -> {r['la_with']:.1f}  dUA {us[0]:+.1f} ({us[1]:+.1f},{us[2]:+.1f}) dLA {au[0]:+.1f} ({au[1]:+.1f},{au[2]:+.1f}) N={us[3]} n={r['n_without']}/{r['n_with']}")
        print("   per seed UA without -> with:", [(s, round(a, 1), round(b, 1)) for s, a, b in per_seed_dir[(dom, mem)]])
json.dump({f"{k[0]}|{k[1]}": v for k, v in rows.items()}, open("scratch/iclr_seven/table33_paper_baseline.json", "w"), indent=1)

# ---- write the table rows and caption
DOMNAME = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance"}
p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
new_rows = []
for dom in SEEDS:
    for mem in ("typed", "hybrid"):
        r = rows[(dom, mem)]; us, au = r["dua"], r["dla"]
        new_rows.append(f"    {DOMNAME[dom]} & {mem} & {r['ua_without']:.1f} & {r['ua_with']:.1f} & {r['la_without']:.1f} & {r['la_with']:.1f} & ${us[0]:+.1f}$ (${us[1]:+.1f}$, ${us[2]:+.1f}$) & ${au[0]:+.1f}$ (${au[1]:+.1f}$, ${au[2]:+.1f}$) " + chr(92) + chr(92))
i = s.index("    Procurement & typed & 25.7 &"); j = s.index("    " + chr(92) + "bottomrule", i)
s = s[:i] + chr(10).join(new_rows) + chr(10) + s[j:]
old_cap = "and the paired change in points with 95" + chr(92) + "% bootstrap intervals; three seeds per domain, both executors, 42 pairs per row.}"
assert s.count(old_cap) == 1, s[s.index("bootstrap intervals; three seeds"):][:120]
s = s.replace(old_cap, "and the paired change in points with 95" + chr(92) + "% bootstrap intervals over writer--seed pairs, both executors pooled; three seeds per domain, 21 pairs per row. The typed baseline is the writer-route typed incremental memory of Table~" + chr(92) + "ref{tab:memory-design-decomposition}.}")
p.write_text(s, encoding="utf-8", newline="\n"); print("table 33 rewritten")
