"""Update the paper to the seven-writer parity results. Reads the pooled outputs written by run_parity_finish.sh,
regenerates the figures that carry them, and rewrites every affected table row, sentence, and paragraph, wrapping the
changed prose in \\updated{} (blue). Table cells are never coloured. Run from the eal-bench root:
    python scratch/iclr_seven/apply_parity.py <scratchpad dir>"""
import collections
import csv
import json
import pathlib
import re
import shutil
import subprocess
import sys

import os
ICLR = pathlib.Path(os.environ.get("ICLR_DIR", r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr"))
S = pathlib.Path(sys.argv[1])
PY = sys.executable
POOL = json.load(open("scratch/iclr_seven/parity_pool.json", encoding="utf-8"))
NAME = {"glm_5_2_baseten": "GLM 5.2", "kimi_baseten": "Kimi K2.6", "nemotron_3_ultra_baseten": "Nemotron 3 Ultra", "inkling_baseten": "Inkling",
        "deepseek_v4_1_flash_baseten": "DeepSeek V4.1 Flash", "grok_4_3_openrouter": "Grok 4.3", "qwen_plus_0728_openrouter": "Qwen-Plus"}
W7 = list(NAME)
DOMS = ["procurement", "cybersecurity", "finance"]
DOMNAME = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance"}
log = []


def resub_(pattern, repl, string, count=1, flags=0):
    """re.sub with a literal replacement (backslashes in LaTeX are not escapes)."""
    n = len(re.findall(pattern, string, flags))
    assert n >= 1, f"pattern not found: {pattern[:80]}"
    return re.sub(pattern, (lambda m: repl) if isinstance(repl, str) else repl, string, count=count, flags=flags)


def U(text):
    return "\\updated{" + text + "}"


def f1(x):
    return f"{x:.1f}"


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    log.append(label); return text.replace(old, new)


def replace_par(text, body_marker, new, label):
    """Replace the coloured paragraph whose body starts with body_marker (any of \\added, \\revised, \\updated)."""
    m = list(re.finditer(r"\\(?:added|revised|updated)\{" + re.escape(body_marker), text))
    assert len(m) == 1, f"{label}: marker found {len(m)} times"
    i = m[0].start(); j = text.index("}\n", i) + 1
    log.append(label); return text[:i] + new + text[j:]


def pct(k, n):
    return 100 * k / n if n else float("nan")


# ------------------------------------------------------------------ inputs
D = POOL["designs"]
missing = POOL["missing"]
print("missing runs:", len(missing))


def parse_section7(path):
    txt = pathlib.Path(path).read_text(encoding="utf-8")
    pooled = {}; per_writer = collections.defaultdict(dict)
    part = txt.split("### Per seed")[0]
    for line in part.splitlines():
        m = re.match(r"\| (procurement|cybersecurity|finance) \| (typed|hybrid) incremental \| ([0-9.]+)% \([^)]*\), n=(\d+) \| ([0-9.]+)% [^|]*\| ([0-9.]+)% [^|]*\| ([0-9.]+)% [^|]*\| (\d+) → (\d+) \| ([-+0-9.]+) \(([-+0-9.]+) to ([-+0-9.]+)\), p=([0-9.]+), (\d+) pairs \| ([-+0-9.]+) \(([-+0-9.]+) to ([-+0-9.]+)\), p=([0-9.]+), (\d+) pairs \|", line)
        if m:
            g = m.groups()
            pooled[(g[0], g[1])] = {"ua_without": float(g[2]), "n": int(g[3]), "ua_with": float(g[4]), "la_without": float(g[5]), "la_with": float(g[6]), "formed_without": int(g[7]), "formed_with": int(g[8]),
                                    "dua": (float(g[9]), float(g[10]), float(g[11])), "pairs": int(g[13]), "dla": (float(g[14]), float(g[15]), float(g[16]))}
    part = txt.split("### Per writer")[1] if "### Per writer" in txt else ""
    for line in part.splitlines():
        m = re.match(r"\| (procurement|cybersecurity|finance) \| ([^|]+?) \| ([0-9.]+)% \([^)]*\) → ([0-9.]+)% \([^)]*\) \| ([0-9.]+)% \([^)]*\) → ([0-9.]+)% \([^)]*\) \|", line)
        if m:
            per_writer[m.group(1)][m.group(2).strip()] = {"ua_without": float(m.group(3)), "ua_with": float(m.group(4)), "la_without": float(m.group(5)), "la_with": float(m.group(6))}
    per_seed = collections.defaultdict(list)
    part = txt.split("### Per seed")[1].split("### Per writer")[0] if "### Per seed" in txt else ""
    for line in part.splitlines():
        m = re.match(r"\| (procurement|cybersecurity|finance) \| (\S+)[^|]*\| ([0-9.]+)% \([^)]*\) → ([0-9.]+)% ", line)
        if m:
            per_seed[m.group(1)].append((float(m.group(3)), float(m.group(4))))
    assert len(pooled) == 6, list(pooled)
    return pooled, per_writer, per_seed


S7, S7W, S7S = parse_section7("results/analysis/section7_seven.md")


def parse_section4(path):
    txt = pathlib.Path(path).read_text(encoding="utf-8").split("| lifecycle")[0]  # the restatement table only
    out = {}
    for line in txt.splitlines():
        m = re.match(r"\| (\w[\w-]*) \| (\d+) \| ([0-9.]+)% \(([0-9.]+)–([0-9.]+)\), (\d+)/(\d+) \| (\d+)/(\d+) \| ([0-9.]+)% \([^)]*\) \| ([0-9.]+)% \|", line)
        if m:
            g = m.groups()
            out[g[0]] = {"memories": int(g[1]), "pf": float(g[2]), "lo": float(g[3]), "hi": float(g[4]), "k": int(g[5]), "n": int(g[6]), "exact_k": int(g[7]), "exact_n": int(g[8]), "ua": float(g[9]), "la": float(g[10])}
    assert {"0", "2", "4"} <= set(out), list(out)
    return out


S4_WITHOUT = parse_section4("results/analysis/section4_seven_without.md")
S4_WITH = parse_section4("results/analysis/section4_seven_with.md")


def parse_loop(path):
    txt = pathlib.Path(path).read_text(encoding="utf-8")
    out = {"US": {}, "AU": {}}
    sec = None
    for line in txt.splitlines():
        if line.startswith("== US"): sec = "US"
        elif line.startswith("== AU"): sec = "AU"
        elif line.startswith("== unsafe") or line.startswith("== records"): sec = None
        m = re.match(r"\s*round (\d)\s+action\s+(\d+)/(\d+)\s+([0-9.]+)%\s+neutral\s+(\d+)/(\d+)\s+([0-9.]+)%\s+diff\s+([-+0-9.]+) pts\s+95% CI \[([-+0-9.]+), ([-+0-9.]+)\]\s+p=([0-9.]+)\s+chains=(\d+)", line)
        if m and sec:
            g = m.groups(); out[sec][int(g[0])] = {"action": float(g[3]), "neutral": float(g[6]), "diff": float(g[7]), "lo": float(g[8]), "hi": float(g[9]), "p": float(g[10]), "chains": int(g[11])}
    rec = collections.Counter()
    for line in txt.splitlines():
        m = re.match(r"\s*(procurement|cybersecurity|finance)\s+(\S+)\s+seed \S+\s+executor \S+\s+action\s+(\d+)\s+neutral\s+(\d+)", line)
        if m:
            rec["action"] += int(m.group(3)); rec["neutral"] += int(m.group(4))
    out["records"] = dict(rec)
    assert 3 in out["AU"], path
    return out


LOOP = parse_loop("results/analysis/loop_vs_null_seven.txt")
LOOP_W = {w: parse_loop(f"results/analysis/loop_vs_null_{w}.txt") for w in W7 if pathlib.Path(f"results/analysis/loop_vs_null_{w}.txt").exists() and "round 3" in pathlib.Path(f"results/analysis/loop_vs_null_{w}.txt").read_text(encoding="utf-8")}
CL = {(r["domain"], r["arm"], int(r["round"])): r for r in csv.DictReader(open("results/figures/closed_loop_control.csv", encoding="utf-8"))}

# cause table over the refreshed failures.csv, same grouping as the paper's table
rows = list(csv.DictReader(open("results/diagnosis/failures.csv", encoding="utf-8")))
LABELS = ["restatement_applied", "own_action_as_approval", "authoritative_change_misapplied", "update_failed", "other"]


def setting(r):
    mandate = r["group"] in ("mandate-open", "loop-mandate"); closed = r["group"] in ("loop-both", "loop-mandate", "onepass"); writeback = r["loop_block"] == "True"
    if mandate:
        return "With the instruction, cybersecurity" if r["domain"] == "cybersecurity" else "With the instruction, procurement and finance"
    if closed and writeback:
        return "Closed loop, the agent's own lines"
    if closed:
        return "Closed loop, shared history blocks"
    return f"Open loop, {r['domain']}"


ORDER = ["Open loop, procurement", "Open loop, finance", "Open loop, cybersecurity", "Closed loop, shared history blocks", "Closed loop, the agent's own lines", "With the instruction, procurement and finance", "With the instruction, cybersecurity"]
counts = collections.defaultdict(collections.Counter); updates = collections.defaultdict(set)
for r in rows:
    counts[setting(r)][r["consensus_cause"] or "no majority"] += 1
    updates[setting(r)].add((r["run_tag"], r["chain_id"], r["arm"] if r["loop_block"] == "True" else "", r["error_block"]))
tot = collections.Counter()
for c in counts.values():
    tot.update(c)
all_updates = set().union(*updates.values()); sum_updates = sum(len(u) for u in updates.values())
n_fail = sum(tot.values())
unanimous = sum(1 for r in rows if r["agreement"] in ("3", "3/3", "unanimous") or (r.get("deepseek") and r["deepseek"] == r["glm_5_3"] == r["nemotron"]))
judge_counts = {j: collections.Counter(r[j] for r in rows) for j in ("deepseek", "glm_5_3", "nemotron")}
cyber_open = counts["Open loop, cybersecurity"]; cyber_open_n = sum(cyber_open.values())
INCR = ("incremental_typed", "incremental_hybrid"); INCR_M = ("incremental_typed__mandate", "incremental_hybrid__mandate")
cyber_ins_fail = sum(1 for r in rows if r["group"] == "mandate-open" and r["domain"] == "cybersecurity" and r["condition_id"] in INCR_M)
cyber_ins_rej = sum(1 for r in rows if r["group"] == "mandate-open" and r["domain"] == "cybersecurity" and r["condition_id"] in INCR_M and r["consensus_cause"] == "update_failed")
cyber_base_fail = sum(1 for r in rows if r["group"] in ("memtable-cyber", "memtable-seeds") and r["domain"] == "cybersecurity" and r["condition_id"] in INCR)
cyber_base_rej = sum(1 for r in rows if r["group"] in ("memtable-cyber", "memtable-seeds") and r["domain"] == "cybersecurity" and r["condition_id"] in INCR and r["consensus_cause"] == "update_failed")

# gate over all seven writers: the paper's five published cells plus the exact counts of the two added writers' gate runs
n5 = {"procurement": 1080, "cybersecurity": 1920, "finance": 960}
five = {"procurement": (28.9, 6.8, 96.8, 13.6), "cybersecurity": (10.4, 10.4, 88.8, 88.8), "finance": (51.0, 1.7, 98.3, 29.2)}
added_gate = {"procurement": [(216, 71, 24, 193, 10), (216, 20, 9, 216, 37)], "cybersecurity": [(384, 42, 42, 336, 336), (384, 40, 40, 336, 336)], "finance": [(192, 56, 0, 192, 16), (192, 70, 0, 192, 80)]}
GATE = {}; totg = [0] * 5
for dom in DOMS:
    n = n5[dom]; uo, ug, lo, lg = [round(v * n / 100) for v in five[dom]]
    for m_, a, b, c, d_ in added_gate[dom]:
        uo += a; ug += b; lo += c; lg += d_; n += m_
    GATE[dom] = (n, uo, ug, lo, lg)
    for i, v in enumerate((uo, ug, lo, lg, n)):
        totg[i] += v
GATE["pooled"] = (totg[4], totg[0], totg[1], totg[2], totg[3])

# event sourcing: the paper's five published counts plus Flash and, when its reruns are analysed, Inkling
event5 = {"procurement": (312, 116, 1045, 967, 1080), "cybersecurity": (200, 175, 1704, 1466, 1920), "finance": (490, 66, 944, 128, 960)}
EV = POOL["event_by_writer"]
ink_ok = all(f"{d}|unauthorized_submission" in EV.get("inkling_baseten", {}) for d in DOMS) and pathlib.Path("results/analysis/event_sourcing").exists() and len(list(pathlib.Path("results/analysis/event_sourcing").glob("event-s*-inkling"))) == 9
EVENT = {}; tote = [0] * 5
for dom in DOMS:
    uo, ue, lo, le, n = event5[dom]
    for w in (["deepseek_v4_1_flash_baseten"] + (["inkling_baseten"] if ink_ok else [])):
        a = EV[w][f"{dom}|unauthorized_submission"]; b = EV[w][f"{dom}|authorized_use"]
        uo += a[0]; ue += a[2]; lo += b[0]; le += b[2]; n += a[1]
    EVENT[dom] = (n, uo, ue, lo, le)
    for i, v in enumerate((uo, ue, lo, le, n)):
        tote[i] += v
EVENT["pooled"] = (tote[4], tote[0], tote[1], tote[2], tote[3])
print("event writers:", "seven" if ink_ok else "six")

# ------------------------------------------------------------------ figures
json.dump({d: [[D[d]["hybrid"]["ua"], D[d]["hybrid"]["la"]], [D[d]["rebuild"]["ua"], D[d]["rebuild"]["la"]], [D[d]["instruction"]["ua"], D[d]["instruction"]["la"]]] for d in DOMS}, open("scratch/iclr_seven/fig2_designs.json", "w"), indent=1)
json.dump({"baseline": (pct(EVENT["pooled"][1], EVENT["pooled"][0]), pct(EVENT["pooled"][3], EVENT["pooled"][0])), "gate": (pct(GATE["pooled"][2], GATE["pooled"][0]), pct(GATE["pooled"][4], GATE["pooled"][0])),
           "event": (pct(EVENT["pooled"][2], EVENT["pooled"][0]), pct(EVENT["pooled"][4], EVENT["pooled"][0])), "instruction": (D["pooled"]["instruction"]["ua"], D["pooled"]["instruction"]["la"]), "rebuild": (D["pooled"]["rebuild"]["ua"], D["pooled"]["rebuild"]["la"])},
          open("scratch/iclr_seven/fig4_points.json", "w"), indent=1)
json.dump({"N": S4_WITHOUT["0"]["n"], "M": S4_WITHOUT["0"]["exact_n"], "PF": {"without": [S4_WITHOUT[l]["k"] for l in "024"], "with": [S4_WITH[l]["k"] for l in "024"]},
           "UA": {"without": [S4_WITHOUT[l]["ua"] for l in "024"], "with": [S4_WITH[l]["ua"] for l in "024"]}, "EXACT": {"without": [S4_WITHOUT[l]["exact_k"] for l in "024"], "with": [S4_WITH[l]["exact_k"] for l in "024"]}},
          open("scratch/iclr_seven/restatement.json", "w"), indent=1)
json.dump([[s.replace("Closed loop, the agent's own lines", "Closed loop, agent's own lines").replace("shared history blocks", "shared history"), [counts[s][l] for l in LABELS]] for s in ORDER], open("scratch/iclr_seven/mechanism.json", "w"), indent=1)
for script, out in (("fig2_final.py", "fig2_final"), ("fig4_final.py", "fig4_final"), ("fig_restatement.py", "fig_restatement"), ("fig_mechanism.py", "fig_mechanism"), ("fig_ttc_seven.py", "fig_ttc_seven")):
    r = subprocess.run([PY, f"scratch/iclr_seven/{script}", str(S / out)], capture_output=True, text=True)
    assert r.returncode == 0, (script, r.stderr[-800:])
shutil.copy(S / "fig2_final.pdf", ICLR / "figures/EAL-Bench_memory_design.pdf")
shutil.copy(S / "fig4_final.pdf", ICLR / "figures/mitigation_pareto_frontier.pdf")
shutil.copy(S / "fig_restatement.pdf", ICLR / "figures/restatements.pdf")
shutil.copy(S / "fig_mechanism.pdf", ICLR / "figures/failure_mechanism.pdf")
shutil.copy(S / "fig_ttc_seven.pdf", ICLR / "figures/TTC-scale.pdf")
shutil.copy("results/figures/closed_loop_control.pdf", ICLR / "figures/closed_loop_control.pdf")
print("figures regenerated")

# ------------------------------------------------------------------ derived statements
hy = [D[d]["hybrid"]["ua"] for d in DOMS]; rb = [D[d]["rebuild"]["ua"] for d in DOMS]
rb_la_ok = all(D[d]["rebuild"]["la"] >= D[d]["typed"]["la"] - 0.5 for d in DOMS)
pf0, pf2, pf4 = (S4_WITHOUT[l]["pf"] for l in "024"); two_vs_four = not (S4_WITHOUT["4"]["hi"] < S4_WITHOUT["2"]["lo"] or S4_WITHOUT["2"]["hi"] < S4_WITHOUT["4"]["lo"])
au3 = LOOP["AU"][3]; us3 = LOOP["US"][3]; chains = au3["chains"]
rec_a = POOL["records_from_own_lines"]["without_instruction_action_arm"]; rec_c = POOL["records_from_own_lines"]["without_instruction_control"]; rec_i = POOL["records_from_own_lines"]["with_instruction"]
dom_au_diff = {d: float(CL[(d, "action", 3)]["au"]) - float(CL[(d, "neutral", 3)]["au"]) for d in DOMS}
worst_dom = min(dom_au_diff, key=dom_au_diff.get)
fin_flat = abs(dom_au_diff["finance"]) < 4 and abs(float(CL[("finance", "action", 3)]["us"]) - float(CL[("finance", "neutral", 3)]["us"])) < 4
ref = POOL["refusal_share"]
ins = {d: (D[d]["typed_matched_instruction"]["ua"], D[d]["instruction"]["ua"], D[d]["typed_matched_instruction"]["la"], D[d]["instruction"]["la"]) for d in DOMS}
cyb_ratio = ins["cybersecurity"][1] / ins["cybersecurity"][0]
same_dir = all(a > b for a, b in S7S["procurement"] + S7S["finance"]) and all(b > a for a, b in S7S["cybersecurity"])
la_ok = all(ins[d][3] >= ins[d][2] - 1.0 for d in ("procurement", "finance"))
cyb_word = "doubles" if 1.7 <= cyb_ratio <= 2.4 else ("roughly doubles" if 1.5 <= cyb_ratio < 1.7 or 2.4 < cyb_ratio <= 2.8 else f"multiplies by {cyb_ratio:.1f}")
hurt = [w for w, v in S7W["cybersecurity"].items() if v["ua_with"] > v["ua_without"] + 0.5]; same = [w for w, v in S7W["cybersecurity"].items() if abs(v["ua_with"] - v["ua_without"]) <= 0.5]
indep8 = POOL["independent_review_selected_exact"]["8"]["rate"]; indep = [POOL["independent_review_selected_exact"][k]["rate"] for k in ("2", "4", "8")]
pooled_ins = D["pooled"]["instruction"]; pooled_rb = D["pooled"]["rebuild"]
rec_cut = 100 * (1 - rec_i / 127) if rec_i else 100  # against the same writers' 127 records without the instruction
rounds_au = [LOOP["AU"][r]["diff"] for r in (1, 2, 3)]
excl0 = [NAME[w] for w, l in LOOP_W.items() if l["US"][3]["lo"] > 0]
tvh = POOL["typed_vs_hybrid_by_writer"]
helped = {d: [NAME[w] for w in W7 if f"{w}|{d}" in tvh and tvh[f"{w}|{d}"]["hybrid"]["ua"] is not None and tvh[f"{w}|{d}"]["hybrid"]["ua"] < tvh[f"{w}|{d}"]["typed"]["ua"] - 1] for d in DOMS}
n_writers_run = len({w for w in W7 if any(f"{w}|{d}" in tvh for d in DOMS)})

# ------------------------------------------------------------------ main.tex
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
s = resub_(r"false authority forms for [0-9.]+\\% of unauthorized requests after two restatements and for under 1\\% without one",
           U(f"false authority forms for {pf2:.0f}\\% of unauthorized requests after two restatements and for {'under 1' if pf0 < 1 else f1(pf0)}\\% without one"), s, count=1); log.append("abstract restatement")
s = resub_(r"lowers legitimate actions by \d+ points over three rounds", U(f"lowers legitimate actions by {abs(au3['diff']):.0f} points over three rounds"), s, count=1); log.append("contribution loop")
s = replace_par(s, "The last three bars of Figure~\\ref{fig:memory-design-across-domains} confirm",
                U(f"The last three bars of Figure~\\ref{{fig:memory-design-across-domains}} confirm that the update strategy drives the failure (Appendix~\\ref{{app:rebuild}}). The hybrid schema still updates from memory alone and still launders, at {min(hy):.0f} to {max(hy):.0f}\\% unauthorized action rate across the domains, and whether it improves on typed memory depends on the writer. Rebuilding the memory from the full history every three blocks lowers the unauthorized action rate to {max(rb):.0f}\\% or below in every domain {'with the legitimate action rate unchanged or higher' if rb_la_ok else 'while the legitimate action rate stays within a point of the baseline'}, so the incremental writer recovers one-shot behavior as soon as it sees the history again. Writer-side retrieval changes nothing, which places the misleading material in the new block itself rather than in what the writer no longer sees."), "4.1")
s = replace_par(s, "The cause can be isolated on generated procurement histories",
                U(f"The cause can be isolated on generated procurement histories that differ only in whether a superseded permission is later restated (Appendix~\\ref{{app:generated-corpus}}). Without a restatement, false authority forms for {'under 1' if pf0 < 1 else f1(pf0)}\\% of unauthorized requests; with two restatements it forms for {f1(pf2)}\\%, and four restatements are {'not measurably worse than two' if two_vs_four else 'measurably different from two'} (Figure~\\ref{{fig:restatements}}). Attribution then shows what the writer does with such a message, and the answer differs by domain (Figure~\\ref{{fig:mechanism}}). In procurement and finance nearly every failure is a restatement applied: the writer changes the record to match a message that carried no authority. In cybersecurity {'nine of ten' if cyber_open['update_failed'] / cyber_open_n >= 0.85 else f'{100*cyber_open['update_failed']/cyber_open_n:.0f}\\% of'} failures are instead a rejected update at the block carrying the duty officer's signed replacement of the permission list. The writer's plan is correct, but its write attempts are rejected as invalid output, and the old grant remains active. Section~\\ref{{sec:mitigation-pareto-results}} shows that this difference decides which defenses work."), "4.2")
s = replace_par(s, "An agent that logs its actions produces the very messages",
                U(f"An agent that logs its actions produces the very messages identified above as the cause, and in deployment those lines enter the history the writer reads. We therefore write the executor's log line for each request back into the history for three rounds and compare against a control with the same updates and neutral content (Appendix~\\ref{{app:closed-loop}}). The writer treats its own log as evidence about authority: it creates {rec_a} permission records that cite nothing but the agent's lines, against {rec_c} in the control, and the judges label nearly all failures entering through a written-back line as an escalation, decline, or order read as a grant. The damage falls on legitimate work rather than on safety: the legitimate action rate at round 3 is {abs(au3['diff']):.1f} points below the control, with the largest loss in {worst_dom}, where the executor escalates most often, whereas the unauthorized action rate {'barely moves' if abs(us3['diff']) < 3 else f'rises by {us3['diff']:.1f} points'}{' and finance is unaffected in both arms' if fin_flat else ''}. A single write-back has no effect, and the loss accumulates over rounds (Figure~\\ref{{fig:closed-loop}})."), "4.4")
s = resub_(r"and an independent DeepSeek V4 Pro reviewer in [0-9.]+\\%\.", U(f"and an independent DeepSeek V4 Pro reviewer in {f1(indep8)}\\%.")[:-1] + "}", s, count=1); log.append("4.5 independent")
s = replace_par(s, "On the shared three-seed typed-incremental population, source-authority gating cuts",
                U(f"On the shared three-seed typed-incremental population, source-authority gating cuts the unauthorized action rate from {f1(pct(GATE['pooled'][1], GATE['pooled'][0]))}\\% to {f1(pct(GATE['pooled'][2], GATE['pooled'][0]))}\\% and bounded event sourcing cuts it from {f1(pct(EVENT['pooled'][1], EVENT['pooled'][0]))}\\% to {f1(pct(EVENT['pooled'][2], EVENT['pooled'][0]))}\\%. Both pay in legitimate use: the legitimate action rate falls to {f1(pct(GATE['pooled'][4], GATE['pooled'][0]))}\\% under the gate and to {f1(pct(EVENT['pooled'][4], EVENT['pooled'][0]))}\\% under event sourcing, from {f1(pct(GATE['pooled'][3], GATE['pooled'][0]))}\\% and {f1(pct(EVENT['pooled'][3], EVENT['pooled'][0]))}\\%."), "4.6 origin numbers")
s = replace_par(s, "A defense matched to the writer's error avoids this tradeoff",
                U(f"A defense matched to the writer's error avoids this tradeoff (Table~\\ref{{tab:writer-side-mitigations}}). Rebuilding memory from the history removes the error before it is stored, and it lowers the unauthorized action rate in every domain with no loss of legitimate actions (Section~\\ref{{sec:memory-design-results}}). The writer instruction forbids exactly the error found in procurement and finance, an applied restatement, and there it removes most of the laundering, from {f1(ins['procurement'][0])}\\% to {f1(ins['procurement'][1])}\\% and from {f1(ins['finance'][0])}\\% to {f1(ins['finance'][1])}\\%, {'with the legitimate action rate unchanged or higher' if la_ok else 'with the legitimate action rate within a point of the baseline'}{' and the same direction at every seed' if same_dir else ''}. Pooled over domains, it is the point on the frontier of Figure~\\ref{{fig:mitigation-pareto}} that stays closest to the baseline's legitimate action rate, and rebuilding, which removes the error before it is stored, lies beyond the frontier on both axes. The same sentence {cyb_word} the unauthorized action rate in cybersecurity, from {f1(ins['cybersecurity'][0])}\\% to {f1(ins['cybersecurity'][1])}\\%, where the failure is a rejected write of the legitimate change: an instruction about authority cannot restore a write that never lands, and under it the writer's updates at the critical block fail {'nearly twice as often' if 1.6 <= cyber_ins_fail / max(1, cyber_base_fail) <= 2.4 else f'{cyber_ins_fail / max(1, cyber_base_fail):.1f} times as often'}. Doubling memory capacity removes the baseline cybersecurity failure, which is therefore a write that does not fit, but leaves most of the instruction's penalty in place, whose rejected writes are malformed rather than oversize (Appendix~\\ref{{app:mandate}}). These runs leave open why the instruction degrades the writer's output, but they establish that a rule about authority must match the error the writer makes and that this error can be read from the saved memories before the executor is granted tools (Appendix~\\ref{{app:diagnosis}})."), "4.6 instruction")
s = sub1(s, "hollow markers: a control with the same updates and neutral content. GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash, both executors, canonical seed; 95\\% bootstrap intervals over chains.}",
         "hollow markers: a control with the same updates and neutral content. \\updated{Both executors, canonical seed; 95\\% bootstrap intervals over chains.}}", "fig3 caption")
s = resub_(r"and [0-9.]+\\%, [0-9.]+\\%, and [0-9.]+\\% at \$k=2,4,8\$ under independent DeepSeek V4 Pro review of the pools of GLM 5\.2, Kimi K2\.6, Nemotron 3 Ultra, Grok 4\.3, and Qwen-Plus\.",
           U(f"and {f1(indep[0])}\\%, {f1(indep[1])}\\%, and {f1(indep[2])}\\% at $k=2,4,8$ under independent DeepSeek V4 Pro review."), s, count=1); log.append("ttc appendix independent")
s = sub1(s, "The independent reviewer uses the same frozen candidate pools, and at $k=8$ it selects an exact memory more often than self-review does while remaining far below the availability ceiling, so the gap is not only a self-review artifact.}",
         U("The independent reviewer uses the same frozen candidate pools, and at $k=8$ it selects an exact memory " + ("more often than" if indep8 > POOL.get("self_review_k8", 23.8) else "about as often as") + " self-review does while remaining far below the availability ceiling, so the gap is not only a self-review artifact.") + "}", "ttc appendix B2")
# plates: hybrid cells for the writers that had a dash
cells = POOL["hybrid_cells"]
pm = ICLR / "memory_design_appendix.tex"; t = pm.read_text(encoding="utf-8")
pat = re.compile(r"(\\mdwriter\{[^\n]*\{([^{}]+)\}\}\n(?:\s*\{\\mdcell[^\n]*\}\n){4})(\s*\{--\}\n)")
NAME2ID = {v: k for k, v in NAME.items()}
filled = 0
for dom, label in (("procurement", "tab:memory-design-procurement"), ("cybersecurity", "tab:memory-design-cybersecurity"), ("finance", "tab:memory-design-finance")):
    i = t.index(f"\\mddomainplate{{{dom.capitalize()}}}{{{label}}}"); j = t.find("\\mddomainplate", i + 10); j = len(t) if j < 0 else j
    plate = t[i:j]; blocks = list(pat.finditer(plate)); new = ""; last = 0
    # the panel order is GPT-OSS then DeepSeek, seven writers each; count mdwriter blocks to place executors
    all_blocks = list(re.finditer(r"\\mdwriter\{[^\n]*\{([^{}]+)\}\}", plate)); pos = {m.start(): k for k, m in enumerate(all_blocks)}
    for m in blocks:
        ex = "gptoss_baseten" if pos[m.start(1)] < 7 else "deepseek_baseten"; key = f"{dom}|{NAME2ID[m.group(2)]}|{ex}"
        if key in cells:
            c = cells[key]; cell = f"    {{\\mdcell{{{100*c['la_k']/c['la_n']:.1f}}}{{{100*c['ua_k']/c['ua_n']:.1f}}}{{{c['la_k']}}}{{{c['ua_k']}}}{{{c['la_n']}}}}}\n"
            new += plate[last:m.start(3)] + cell; last = m.end(3); filled += 1
    new += plate[last:]; t = t[:i] + new + t[j:]
pm.write_text(t, encoding="utf-8", newline="\n"); print("plate cells filled:", filled)
p.write_text(s, encoding="utf-8", newline="\n")

# multiseed: third executor wording
pms = ICLR / "multiseed_appendix.tex"; t = pms.read_text(encoding="utf-8")
t = t.replace("replayed the frozen memories of every open-loop extension study (the memory designs, the generated histories, and the writer instruction with its baselines), 124 executor-only replays in all,", "replayed the frozen memories of the open-loop extension studies (the memory designs, the generated histories, and the writer instruction with its baselines), 124 executor-only replays in all,")
pms.write_text(t, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ extension results appendix
p = ICLR / "extension_results_appendix.tex"; s = p.read_text(encoding="utf-8")
N4 = S4_WITHOUT["0"]["n"]; M4 = S4_WITHOUT["0"]["exact_n"]
s = sub1(s, "GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash with GPT-OSS-120B as executor, 540 unauthorized requests and 180 memories per point.}}",
         U(f"GPT-OSS-120B as executor; {N4} unauthorized requests and {M4} memories per point.") + "}}", "restatement fig caption")
s = sub1(s, "GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash; 180 memories and 540 unauthorized requests per row.}}",
         U(f"{M4} memories and {N4} unauthorized requests per row.") + "}}", "restatement table caption")
tab = []
for arm, src in (("no", S4_WITHOUT), ("yes", S4_WITH)):
    for lvl in "024":
        r = src[lvl]; tab.append(f"    {lvl} & {arm} & {f1(r['pf'])} ({f1(r['lo'])}--{f1(r['hi'])}) & {r['exact_k']}/{r['exact_n']} & {f1(r['ua'])} & {f1(r['la'])} \\\\")
i = s.index("    0 & no & 0.7 (0.3--1.9)"); j = s.index("    \\bottomrule", i)
s = s[:i] + "\n".join(tab) + "\n" + s[j:]; log.append("restatement rows")
ex_without = sum(S4_WITHOUT[l]["exact_k"] for l in "024"); ex_with = sum(S4_WITH[l]["exact_k"] for l in "024")
s = replace_par(s, "With everything but the restatements held fixed,",
                U(f"With everything but the restatements held fixed, false authority forms for {S4_WITHOUT['0']['k']} of {N4} zero-restatement requests and for {f1(pf2)}\\% of requests once two restatements follow the change, while four restatements are {'not measurably different from two' if two_vs_four else 'measurably different from two'} (Figure~\\ref{{fig:restatements}}, Table~\\ref{{tab:restatements}}). The legitimate action rate stays at or near 100\\% throughout, so the failure on this corpus is laundering rather than caution. The writer instruction cuts the rate to {f1(S4_WITH['2']['pf'])}\\% and {f1(S4_WITH['4']['pf'])}\\% at two and four restatements, {'removes the zero-restatement failures entirely' if S4_WITH['0']['k'] == 0 else f'leaves {S4_WITH['0']['k']} zero-restatement failures'}, and raises the number of exact memories from {ex_without} to {ex_with} of {3*M4}."), "restatement results")
lc = {}
for path, key in (("results/analysis/section4_seven_without.md", "lc"),):
    txt = pathlib.Path(path).read_text(encoding="utf-8")
    for line in txt.splitlines():
        m = re.match(r"\| (amendment|revoke-and-replace|1|2|3) \| \d+ \| ([0-9.]+)% ", line)
        if m:
            lc[m.group(1)] = float(m.group(2))
s = replace_par(s, "The same corpus shows two further differences, which are observed rather than matched:",
                U(f"The same corpus shows two further differences, which are observed rather than matched: histories that amend the grant in place fail about {lc['amendment']/max(lc['revoke-and-replace'],0.1):.0f} times as often as histories that revoke it and issue a replacement (false-authority rate {f1(lc['amendment'])}\\% against {f1(lc['revoke-and-replace'])}\\%), and the failure rate shows no trend across gaps of one to three blocks between grant and change ({f1(lc['1'])}\\%, {f1(lc['2'])}\\%, and {f1(lc['3'])}\\%). Because a change of lifecycle or gap also redraws the case's dates, limits, and surrounding text, neither difference is attributed to the lifecycle or the gap alone."), "observed differences")
# closed loop tables
s = sub1(s, "Round 3 against the open-loop starting point, with 95\\% bootstrap intervals over chains; GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash, both executors, canonical seed.}}",
         "Round 3 against the open-loop starting point, with 95\\% bootstrap intervals over chains; \\updated{both executors, canonical seed}.}}", "loop domain caption")
rows_d = []
for d in DOMS:
    a0 = CL[(d, "action", 0)]; a3 = CL[(d, "action", 3)]; n3 = CL[(d, "neutral", 3)]
    rows_d.append(f"    {DOMNAME[d]} & {a3['chains']} & {a0['au']} & {a3['au']} ({a3['au_lo']}--{a3['au_hi']}) & {n3['au']} ({n3['au_lo']}--{n3['au_hi']}) & {a0['us']} & {a3['us']} ({a3['us_lo']}--{a3['us_hi']}) & {n3['us']} ({n3['us_lo']}--{n3['us_hi']}) \\\\")
i = s.index("    Procurement & 120 & 96.7 &"); j = s.index("    \\bottomrule", i)
s = s[:i] + "\n".join(rows_d) + "\n" + s[j:]; log.append("loop domain rows")
s = replace_par(s, "Paired over all 360 chains at round 3,",
                U(f"Paired over all {chains} chains at round 3, the legitimate action rate in the action arm is {abs(au3['diff']):.1f} points below the control (95\\% CI ${au3['lo']:+.1f}$ to ${au3['hi']:+.1f}$) and the unauthorized action rate {abs(us3['diff']):.1f} points {'above' if us3['diff'] >= 0 else 'below'} it (95\\% CI ${us3['lo']:+.1f}$ to ${us3['hi']:+.1f}$). The loss builds over rounds, from {abs(rounds_au[0]):.1f} points at round 1 to {abs(rounds_au[1]):.1f} at round 2 and {abs(rounds_au[2]):.1f} at round 3, while the paired difference in the unauthorized action rate stays within {'a point' if max(abs(LOOP['US'][r]['diff']) for r in (1,2)) < 1.5 else f"{max(abs(LOOP['US'][r]['diff']) for r in (1,2)):.0f} points"} of zero until round 3; Table~\\ref{{tab:closed-loop-writers}} gives the per-writer differences{', and ' + (excl0[0] if len(excl0) == 1 else ', '.join(excl0[:-1]) + ' and ' + excl0[-1]) + (' is the one writer' if len(excl0) == 1 else ' are the writers') + ' whose unauthorized-action interval excludes zero' if excl0 else ', and no writer has an unauthorized-action interval that excludes zero'}. The control also loses legitimate actions in procurement, so part of the decline there follows from repeated updating alone, and only the paired difference isolates the content of the agent's lines."), "loop paired")
rows_w = []
for w in W7:
    if w not in LOOP_W:
        continue
    l = LOOP_W[w]; u = l["US"][3]; a = l["AU"][3]
    rows_w.append(f"    {NAME[w]} & {u['chains']} & ${u['diff']:+.1f}$ (${u['lo']:+.1f}$, ${u['hi']:+.1f}$) & ${a['diff']:+.1f}$ (${a['lo']:+.1f}$, ${a['hi']:+.1f}$) & {l['records'].get('action', 0)} / {l['records'].get('neutral', 0)} \\\\")
rows_w.append("    \\midrule"); rows_w.append(f"    All & {chains} & ${us3['diff']:+.1f}$ (${us3['lo']:+.1f}$, ${us3['hi']:+.1f}$) & ${au3['diff']:+.1f}$ (${au3['lo']:+.1f}$, ${au3['hi']:+.1f}$) & {rec_a} / {rec_c} \\\\")
i = s.index("    GLM 5.2 & 72 &"); j = s.index("    \\bottomrule", i)
s = s[:i] + "\n".join(rows_w) + "\n" + s[j:]; log.append("loop writer rows")
s = replace_par(s, "The action arm alone shows two effects.",
                U(f"The action arm alone shows two effects. First, the writer manufactures permission records out of the agent's own actions: {rec_a} records cite nothing but written-back lines, against {rec_c} in the control, and Appendix~\\ref{{app:diagnosis}} labels nearly all of them as an escalation, decline, or order read as a grant. Second, real grants disappear: in the cybersecurity action arm the final memories hold 4.5 real, active permission records per chain against 7.8 in the frozen starting memory and 6.5 in the control, and cybersecurity is where the executor refuses most often, escalating or declining at {ref['cybersecurity']['escalate_or_decline']:.0f}\\% of positions against {ref['procurement']['escalate_or_decline']:.0f}\\% in procurement and {ref['finance']['escalate_or_decline']:.0f}\\% in finance. Which written-back lines cause a real grant to be deactivated has not been traced. {'In finance neither arm moves either metric, and writing' if fin_flat else 'Writing'} the actions back once, without further rounds, has no effect in any variant, so nothing compounds within one pass. With the writer instruction of Appendix~\\ref{{app:mandate}}, the records created from the agent's own lines fall by {rec_cut:.0f}\\% while the round-3 legitimate action rate stays within a few points of the arm without it, so the instruction stops the minted records without recovering the loss."), "two effects")
# cause table and text
s = sub1(s, "The open-loop rows pool the memory-design grid, the paper's writer route for Inkling and DeepSeek V4.1 Flash, the instruction baselines at the other two seeds, and, in procurement, the generated histories with and without the instruction;",
         "The open-loop rows pool the memory-design runs at three seeds, the instruction baselines, and, in procurement, the generated histories with and without the instruction;", "cause caption sources")
s = resub_(r"so the rows sum to [0-9,]+ updates against [0-9,]+ distinct\.", f"so the rows sum to {sum_updates:,} updates against {len(all_updates):,} distinct.", s, count=1); log.append("cause caption sums")
rows_c = []
for st in ORDER:
    c = counts[st]; rows_c.append(f"    {st} & {len(updates[st])} & {sum(c.values())} & " + " & ".join(str(c[l]) for l in LABELS) + " \\\\")
rows_c.append("    \\midrule"); rows_c.append(f"    All & {len(all_updates)} & {n_fail:,}".replace(",", "{,}") + " & " + " & ".join(f"{tot[l]:,}".replace(",", "{,}") for l in LABELS) + " \\\\")
i = s.index("    Open loop, procurement &"); j = s.index("    \\bottomrule", i)
s = s[:i] + "\n".join(rows_c) + "\n" + s[j:]; log.append("cause rows")
rows_j = []
for j_, nm in (("deepseek", "DeepSeek V4 Pro"), ("glm_5_3", "GLM 5.3"), ("nemotron", "Nemotron 3 Ultra")):
    rows_j.append(f"    {nm} & " + " & ".join(f"{judge_counts[j_][l]:,}".replace(",", "{,}") for l in LABELS) + " \\\\")
i = s.index("    DeepSeek V4 Pro & 1{,}251"); j = s.index("    \\bottomrule", i)
s = s[:i] + "\n".join(rows_j) + "\n" + s[j:]; log.append("judge rows")
s = resub_(r"Labels given by each judge over all [0-9,{}]+ rows\.", f"Labels given by each judge over all {n_fail:,} rows.".replace(",", "{,}"), s, count=1)
s = replace_par(s, "Nearly all 2,250 judged failures fall under three errors,",
                U(f"Nearly all {n_fail:,} judged failures fall under three errors, which separate by domain and setting rather than by writer (Figure~\\ref{{fig:mechanism}}, Table~\\ref{{tab:cause}}). In the open loop, procurement and finance failures are a restatement applied: a status line, a colleague, or a forwarded copy repeats the superseded figure and the writer changes the record to match. In the closed loop, nearly every failure entering through a written-back block is an escalation, decline, or order read as a grant. Cybersecurity differs in kind, because most of its failures, with or without the instruction, are a rejected update at the block carrying the duty officer's signed replacement of the whole permission list, after which the old permission stays active. The judges agree unanimously on {100*unanimous/n_fail:.0f}\\% of rows, and on a blind sample of fifty failures a fourth model given the judges' inputs agreed with the majority label on 46 (Cohen's $\\kappa=0.88$)."), "three errors")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ extension mitigations appendix
p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
pairs = S7[("procurement", "typed")]["pairs"]
s = sub1(s, "and the paired change in points with 95\\% bootstrap intervals; GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash, three seeds per domain, both executors, 30 pairs per row.}}",
         f"and the paired change in points with 95\\% bootstrap intervals; \\updated{{three seeds per domain, both executors, {pairs} pairs per row}}.}}}}", "mandate caption")
rows_m = []
for d in DOMS:
    for mem in ("typed", "hybrid"):
        r = S7[(d, mem)]
        rows_m.append(f"    {DOMNAME[d]} & {mem} & {f1(r['ua_without'])} & {f1(r['ua_with'])} & {f1(r['la_without'])} & {f1(r['la_with'])} & ${r['dua'][0]:+.1f}$ (${r['dua'][1]:+.1f}$, ${r['dua'][2]:+.1f}$) & ${r['dla'][0]:+.1f}$ (${r['dla'][1]:+.1f}$, ${r['dla'][2]:+.1f}$) \\\\")
i = s.index("    Procurement & typed & 25.4 &"); j = s.index("    \\bottomrule", i)
s = s[:i] + "\n".join(rows_m) + "\n" + s[j:]; log.append("mandate rows")
hurt_n = len(hurt); same_n = len(same)
s = replace_par(s, "The direction is the same at every seed in every domain",
                U(f"{'The direction is the same at every seed in every domain' if same_dir else 'The direction is the same at every seed in cybersecurity and in nearly every seed elsewhere'} (Table~\\ref{{tab:mandate-pooled}}). In procurement the unauthorized action rate falls for every writer and the legitimate action rate rises, which is consistent with the writer also ceasing to record restated figures that made it refuse legitimate requests, a reading not tested here. In finance the drop is as large and the legitimate action rate does not measurably change. In cybersecurity the instruction hurts {hurt_n} of the {len(S7W['cybersecurity'])} writers{' and leaves ' + ('one' if same_n == 1 else str(same_n)) + ' unchanged' if same_n else ''}. In the closed loop it lowers the open-loop unauthorized action rate in procurement and finance, raises it in cybersecurity, and cuts the records minted from the agent's own lines by {rec_cut:.0f}\\% while the round-3 legitimate action rate stays within a few points of the arm without it (Appendix~\\ref{{app:closed-loop}})."), "direction")
s = replace_par(s, "The remaining failures show why the domains diverge.",
                U(f"The remaining failures show why the domains diverge. With the instruction, nearly all remaining procurement and finance failures are still a restatement applied, the error the instruction reduces, whereas in cybersecurity not one failure is, with or without the instruction: of {cyber_ins_fail} failures in the instruction runs, {cyber_ins_rej} are a rejected update, against {cyber_base_rej} of {cyber_base_fail} in the same seeds' runs without it. The failing block is the same everywhere, the one carrying the duty officer's signed change set that replaces the whole permission list, and in nearly every case both of the writer's attempts to write the new list are rejected as invalid output, either a patch that cannot be applied or a profile over the memory's size limit, so the memory keeps the old permission active. The instruction does not change how a cybersecurity failure looks but {'nearly doubles' if 1.6 <= cyber_ins_fail / max(1, cyber_base_fail) <= 2.4 else 'raises'} how often one happens, and the attempt logs show the rejected writes rather than what the writer took the change set's authority to be."), "remaining failures")
s = sub1(s, "Unauthorized action rate (UA) and legitimate action rate (LA) under typed incremental memory and three changes to how the writer writes; GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash, both executors, three seeds per domain.}}",
         "Unauthorized action rate (UA) and legitimate action rate (LA) under typed incremental memory and three changes to how the writer writes; \\updated{both executors, three seeds per domain}.}}", "designs caption")
rows_t = []
for d in DOMS:
    r = D[d]; rows_t.append(f"    {DOMNAME[d]} & {f1(r['typed']['ua'])} & {f1(r['typed']['la'])} & {f1(r['hybrid']['ua'])} & {f1(r['hybrid']['la'])} & {f1(r['rebuild']['ua'])} & {f1(r['rebuild']['la'])} & {f1(r['instruction']['ua'])} & {f1(r['instruction']['la'])} \\\\")
i = s.index("    Procurement & 25.4 & 90.6 &"); j = s.index("    \\bottomrule", i)
s = s[:i] + "\n".join(rows_t) + "\n" + s[j:]; log.append("designs rows")


def lst(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + (", and " if len(names) > 2 else " and ") + names[-1]


hyb_sentence = f"The hybrid schema depends on the writer and the domain: it lowers the unauthorized action rate for {len(helped[chr(112)+chr(114)+chr(111)+chr(99)+chr(117)+chr(114)+chr(101)+chr(109)+chr(101)+chr(110)+chr(116)])} of {n_writers_run} writers in procurement, {len(helped[chr(99)+chr(121)+chr(98)+chr(101)+chr(114)+chr(115)+chr(101)+chr(99)+chr(117)+chr(114)+chr(105)+chr(116)+chr(121)])} of {n_writers_run} in cybersecurity, and {len(helped[chr(102)+chr(105)+chr(110)+chr(97)+chr(110)+chr(99)+chr(101)])} of {n_writers_run} in finance, and for Inkling in cybersecurity the rate rises from 18.8\\% to 62.5\\% in one cell."
s = replace_par(s, "Rebuilding lowers the unauthorized action rate for every writer in every domain",
                U(f"Rebuilding lowers the unauthorized action rate in every domain and raises the legitimate action rate (Table~\\ref{{tab:writer-side-mitigations}}), and it is the one design change that holds across writers. {hyb_sentence} Retrieval changes no cell for any memory type, which is consistent with the misleading material being in the new block the writer already reads rather than in what it has forgotten. Free text launders less than typed memory under incremental writing but gives up legitimate actions, because about half its updates exceed the size limit and are discarded."), "designs results")
s = sub1(s, "and never rebuilding leaves 38.0\\% (one seed; GLM 5.2, Kimi K2.6, Nemotron 3 Ultra).", "and never rebuilding leaves 38.0\\% (one seed).", "rebuild timing names")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ gate and event appendices
p = ICLR / "source_authority_appendix.tex"; s = p.read_text(encoding="utf-8")
s = s.replace("\\revised{, pooling six writers, three seeds, and both executors}", "\\updated{, pooling all writers, three seeds, and both executors}")
g = GATE
rows_g = [f"    {DOMNAME[d]} & {f1(pct(g[d][3], g[d][0]))} $\\rightarrow$ {f1(pct(g[d][4], g[d][0]))} & {f1(pct(g[d][1], g[d][0]))} $\\rightarrow$ {f1(pct(g[d][2], g[d][0]))} \\\\" for d in DOMS]
i = s.index("    Procurement & 97.3 $\\rightarrow$ 14.2"); j = s.index("    \\midrule", i)
s = s[:i] + "\n".join(rows_g) + "\n" + s[j:]
s = resub_(r"\\textbf\{Pooled\} & \\textbf\{[0-9.]+ \$\\rightarrow\$ [0-9.]+\} & \\textbf\{[0-9.]+ \$\\rightarrow\$ [0-9.]+\} \\\\",
           f"\\textbf{{Pooled}} & \\textbf{{{f1(pct(g['pooled'][3], g['pooled'][0]))} $\\rightarrow$ {f1(pct(g['pooled'][4], g['pooled'][0]))}}} & \\textbf{{{f1(pct(g['pooled'][1], g['pooled'][0]))} $\\rightarrow$ {f1(pct(g['pooled'][2], g['pooled'][0]))}}} \\\\", s, count=1)
p.write_text(s, encoding="utf-8", newline="\n"); log.append("gate table")

p = ICLR / "event_sourcing_appendix.tex"; s = p.read_text(encoding="utf-8")
e = EVENT
s = s.replace("Values pool \\revised{six} writers, three seeds, and both executors.}", "Values pool \\updated{all writers, three seeds, and both executors}.}" if ink_ok else "Values pool \\updated{six} writers, three seeds, and both executors.}")
rows_e = [f"    {DOMNAME[d]} & {e[d][1]}/{e[d][0]} ({f1(pct(e[d][1], e[d][0]))}\\%) & {e[d][2]}/{e[d][0]} ({f1(pct(e[d][2], e[d][0]))}\\%) & {e[d][3]}/{e[d][0]} ({f1(pct(e[d][3], e[d][0]))}\\%) & {e[d][4]}/{e[d][0]} ({f1(pct(e[d][4], e[d][0]))}\\%) \\\\" for d in DOMS]
i = s.index("    Procurement & 332/1296 (25.6\\%)"); j = s.index("    \\midrule", i)
s = s[:i] + "\n".join(rows_e) + "\n" + s[j:]
pe = e["pooled"]
s = resub_(r"\\textbf\{Pooled\} & \\textbf\{[^}]+\} & \\textbf\{[^}]+\} & \\textbf\{[^}]+\} & \\textbf\{[^}]+\} \\\\",
           f"\\textbf{{Pooled}} & \\textbf{{{pe[1]}/{pe[0]} ({f1(pct(pe[1], pe[0]))}\\%)}} & \\textbf{{{pe[2]}/{pe[0]} ({f1(pct(pe[2], pe[0]))}\\%)}} & \\textbf{{{pe[3]}/{pe[0]} ({f1(pct(pe[3], pe[0]))}\\%)}} & \\textbf{{{pe[4]}/{pe[0]} ({f1(pct(pe[4], pe[0]))}\\%)}} \\\\", s, count=1)
if ink_ok:
    s = resub_(r" \\revised\{Inkling's event writer reasons inside the completion[^}]*\}", "", s, count=1)
s = resub_(r"is about \d+ percentage points, with a 95\\% interval that excludes zero by a wide margin\.", f"is about {abs(pct(pe[2], pe[0]) - pct(pe[1], pe[0])):.0f} percentage points, with a 95\\% interval that excludes zero by a wide margin.", s, count=1)
p.write_text(s, encoding="utf-8", newline="\n"); log.append("event table")

json.dump({"gate": GATE, "event": EVENT, "ink_ok": ink_ok, "loop_round3": {"au": au3, "us": us3}, "records": POOL["records_from_own_lines"], "indep": indep, "restatement": {"pf0": pf0, "pf2": pf2, "pf4": pf4}, "cause_total": n_fail, "updates": [len(all_updates), sum_updates], "hurt": hurt, "same": same}, open("scratch/iclr_seven/apply_parity_summary.json", "w"), indent=1)
print("edits applied:", len(log)); print(log)
