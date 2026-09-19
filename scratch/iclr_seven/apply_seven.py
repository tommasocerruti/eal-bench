"""Pool Inkling and DeepSeek V4.1 Flash into the paper's memory-design, mechanism, transfer and pressure results.

Reads the frozen five-writer counts (results/<domain>/paper/counts.json, pooled earlier) and the added writers'
recounted trials, then rewrites the affected tables in the ICLR clone and redraws Figure 2. Every replacement is
asserted to match exactly once, so a drifted source file stops the script instead of silently skipping an edit.
"""
import json
import math
import re
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

T = Path(r"C:/Users/mikad/.claude/jobs/e03609a8/tmp/seven")
ICLR = Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
DOMS = ("procurement", "cybersecurity", "finance")
DOMNAME = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance"}
CONDS = ("one_shot_text", "incremental_text", "one_shot_typed", "incremental_typed")
SEEDS = {"procurement": ["20260719", "20260821", "20260822"], "cybersecurity": ["20260812", "20260821", "20260822"],
         "finance": ["20260816", "20260821", "20260822"]}
EXS = ("gptoss_baseten", "deepseek_baseten")
ADDED = ("inkling", "deepseek_v4_1_flash")
LOGO = {"inkling": r"\modelname[trim=30 120 30 120,clip]{figures/ModelLogos/inkling-logo.png}{Inkling}",
        "deepseek_v4_1_flash": r"\modelname{figures/ModelLogos/deepseek-logo.png}{DeepSeek V4.1 Flash}"}
# Five-writer request-level false-authority counts implied by the printed rates (28.3%, 10.4%, 50.2%; total 494/1,980).
PAPER_F = {"procurement": (153, 540), "cybersecurity": (100, 960), "finance": (241, 480)}
# Five-writer exact-repair table: (natural taken, natural n, repaired taken, repaired n).
PAPER_T3 = {"procurement": (66, 68, 0, 68), "cybersecurity": (60, 60, 0, 60), "finance": (79, 80, 0, 80)}
# Five-writer typed-incremental mechanism details as printed in the appendix.
PAPER_MECH = dict(traj=540, states=5550, semantic=3464, gain=444, final_not_exact=388, F=494, F_n=1980)
# Added writers, computed with analysis/failure_mechanisms.py on their 18 paper-route runs.
ADDED_MECH = dict(traj=216, states=2220, semantic=1150, gain=137, final_not_exact=155, F=239, F_n=792)

P = json.load(open(T / "paper_counts_pooled.json", encoding="utf-8"))
A = json.load(open(T / "added_writer_counts.json", encoding="utf-8"))
A2 = json.load(open(T / "added_per_seed_executor.json", encoding="utf-8"))
AG = json.load(open(T / "added_agreement.json", encoding="utf-8"))
FX = json.load(open(T / "added_counts_v2.json", encoding="utf-8"))["fixed_seed_by_executor"]
TP = json.load(open(T / "t3_press.json", encoding="utf-8"))
PF = json.load(open(T / "pf_added2.json", encoding="utf-8"))

summary = {}


def pct(k, n):
    return f"{100 * k / n:.1f}"


def rnd(x):
    return int(math.floor(x + 0.5))


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:120]}"
    return text.replace(old, new)


# ------------------------------------------------------------------ pooled seven-writer counts by condition
pool = {}
for dom in DOMS:
    for cond in CONDS:
        p = P[f"{dom}|ALL|{cond}|BOTH"]
        au_k, au_n, us_k, us_n = p["authorized_use"], p["authorized_trials"], p["unauthorized_submissions"], p["unauthorized_trials"]
        add = [A[f"{w}|{dom}|{cond}"] for w in ADDED]
        assert all(a["pe"] == 0 for a in add)
        au_k += sum(a["auth_use"] for a in add); au_n += sum(a["auth_n"] for a in add)
        us_k += sum(a["unauth_sub"] for a in add); us_n += sum(a["unauth_n"] for a in add)
        # cross-check the per-executor recount against the per-writer recount
        ex_sum = sum(A2[f"{dom}|ALL|{cond}|{e}"]["unauth_sub"] for e in EXS)
        assert ex_sum == sum(a["unauth_sub"] for a in add), (dom, cond, ex_sum)
        pool[(dom, cond)] = dict(au_k=au_k, au_n=au_n, us_k=us_k, us_n=us_n)
summary["pooled_by_condition"] = {f"{d}|{c}": v for (d, c), v in pool.items()}

# ------------------------------------------------------------------ Figure 2
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
                     "mathtext.fontset": "stix", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.bbox": "tight"})
fig, axes = plt.subplots(1, 3, figsize=(8.6, 2.55), sharey=True)
labels = ["Text\none-shot", "Text\nincr.", "Typed\none-shot", "Typed\nincr."]
blue, orange = "#4C72B0", "#DD8452"
w = 0.38
for ax, dom in zip(axes, DOMS):
    au = [100 * pool[(dom, c)]["au_k"] / pool[(dom, c)]["au_n"] for c in CONDS]
    us = [100 * pool[(dom, c)]["us_k"] / pool[(dom, c)]["us_n"] for c in CONDS]
    x = range(4)
    ax.bar([i - w / 2 for i in x], au, w, color=blue, label="Authorized use", zorder=3)
    ax.bar([i + w / 2 for i in x], us, w, color=orange, label="Unauthorized submission", zorder=3)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels)
    ax.set_title(DOMNAME[dom]); ax.set_ylim(0, 105)
    ax.set_yticks(range(0, 101, 20)); ax.set_yticklabels([f"{v}%" for v in range(0, 101, 20)])
    ax.yaxis.grid(True, color="#dddddd", zorder=0); ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0)
axes[0].set_ylabel("Rate")
handles, labs = axes[0].get_legend_handles_labels()
fig.legend(handles, labs, loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 1.06))
fig.tight_layout(rect=(0, 0, 1, 0.93))
orig = ICLR / "figures/EAL-Bench_memory_design.pdf"
backup = T / "EAL-Bench_memory_design.fivewriter.pdf"
if not backup.exists():
    shutil.copy(orig, backup)
fig.savefig(orig); fig.savefig(T / "EAL-Bench_memory_design.png", dpi=160)
plt.close(fig)

# ------------------------------------------------------------------ main.tex
main = (ICLR / "main.tex").read_text(encoding="utf-8")

# Figure 2 caption and Table 5 (decomposition) caption / values
main = sub1(main, "Results pool three seeds, five writers, and both executors.", "Results pool three seeds, seven writers, and both executors.", "fig2 caption")
main = sub1(main, "Results pool all three seeds,\n  five writers, and both executors.", "Results pool all three seeds,\n  seven writers, and both executors.", "decomposition caption")
old_dec = {
    "procurement": ("97.4", "0.5", "86.8", "18.2", "98.8", "1.6", "96.8", "28.9"),
    "cybersecurity": ("96.4", "1.1", "92.2", "5.9", "96.6", "0.8", "88.8", "10.4"),
    "finance": ("99.4", "2.7", "94.6", "30.8", "91.7", "0.4", "98.3", "51.0"),
}
for dom in DOMS:
    o = old_dec[dom]
    old = (f"    {dom} &\n" + "\n".join(f"    \\shortstack{{A: {o[2*i]}\\\\U: {o[2*i+1]}}} {'&' if i < 3 else chr(92)+chr(92)}" for i in range(4)))
    cells = []
    for i, c in enumerate(CONDS):
        v = pool[(dom, c)]
        cells.append(f"    \\shortstack{{A: {pct(v['au_k'], v['au_n'])}\\\\U: {pct(v['us_k'], v['us_n'])}}} {'&' if i < 3 else chr(92)+chr(92)}")
    new = f"    {dom} &\n" + "\n".join(cells)
    main = sub1(main, old, new, f"decomposition row {dom}")

# Section 4.1 finance number
fin_ti = pool[("finance", "incremental_typed")]
main = sub1(main, "reaching 51.0\\% unauthorized submission in finance", f"reaching {pct(fin_ti['us_k'], fin_ti['us_n'])}\\% unauthorized submission in finance", "4.1 finance")

# Table 2: formation vs submission
f_rows = {}
for dom in DOMS:
    fk, fn = PAPER_F[dom]; a = PF[f"{dom}|ALL"]
    F = (fk + a["F"], fn + a["n"]); us = pool[(dom, "incremental_typed")]
    f_rows[dom] = (F, (us["us_k"], us["us_n"]))
summary["formation"] = {d: {"F": f_rows[d][0], "US": f_rows[d][1]} for d in DOMS}
main = sub1(main, "and five writers; unauthorized-submission rates also pool both executors.", "and seven writers; unauthorized-submission rates also pool both executors.", "table 2 caption")
t2s = main.index("\\label{tab:formation-vs-submission}"); t2e = main.index("\\end{table}", t2s)
seg = main[t2s:t2e]
for dom, old in (("procurement", "    Procurement & 28.3\\% & 28.9\\% \\\\"), ("cybersecurity", "    Cybersecurity & 10.4\\% & 10.4\\% \\\\"), ("finance", "    Finance & 50.2\\% & 51.0\\% \\\\")):
    F, us = f_rows[dom]
    seg = sub1(seg, old, f"    {DOMNAME[dom]} & {pct(*F)}\\% & {pct(*us)}\\% \\\\", f"table 2 row {dom}")
main = main[:t2s] + seg + main[t2e:]
old = ("Across three seeds, formation closely tracks unauthorized submission in all three domains (Table~\\ref{tab:formation-vs-submission}): under typed incremental memory, pooled $P(F)$ is 28.3\\% in procurement, 10.4\\% in cybersecurity, and 50.2\\% in finance, each within 0.8 points of the corresponding submission rates.")
Fp, Fc, Ff = (f_rows[d][0] for d in DOMS); Up, Uc, Uf = (f_rows[d][1] for d in DOMS)
new = (f"Across three seeds, formation tracks unauthorized submission in all three domains (Table~\\ref{{tab:formation-vs-submission}}): under typed incremental memory, pooled $P(F)$ is {pct(*Fp)}\\% in procurement, {pct(*Fc)}\\% in cybersecurity, and {pct(*Ff)}\\% in finance, against submission rates of {pct(*Up)}\\%, {pct(*Uc)}\\%, and {pct(*Uf)}\\%.")
main = sub1(main, old, new, "4.2 formation sentence")

# Table 3: exact repair
t3 = {}
for dom in DOMS:
    nt, nn, rt, rn = PAPER_T3[dom]; a = TP["t3"][f"{dom}|ALL"]
    t3[dom] = (nt + a["natural_error_taken"], nn + a["natural_error_n"], rt + a["exact_repair_taken"], rn + a["exact_repair_n"])
summary["repair"] = t3
tot = [sum(t3[d][i] for d in DOMS) for i in range(4)]
main = sub1(main, "Procurement & 66/68 (97.1\\%) & 0/68 (0.0\\%) \\\\", f"Procurement & {t3['procurement'][0]}/{t3['procurement'][1]} ({pct(t3['procurement'][0], t3['procurement'][1])}\\%) & {t3['procurement'][2]}/{t3['procurement'][3]} ({pct(t3['procurement'][2], t3['procurement'][3])}\\%) \\\\", "t3 proc")
main = sub1(main, "Cybersecurity & 60/60 (100.0\\%) & 0/60 (0.0\\%) \\\\", f"Cybersecurity & {t3['cybersecurity'][0]}/{t3['cybersecurity'][1]} ({pct(t3['cybersecurity'][0], t3['cybersecurity'][1])}\\%) & {t3['cybersecurity'][2]}/{t3['cybersecurity'][3]} ({pct(t3['cybersecurity'][2], t3['cybersecurity'][3])}\\%) \\\\", "t3 cyber")
main = sub1(main, "Finance & 79/80 (98.8\\%) & 0/80 (0.0\\%) \\\\", f"Finance & {t3['finance'][0]}/{t3['finance'][1]} ({pct(t3['finance'][0], t3['finance'][1])}\\%) & {t3['finance'][2]}/{t3['finance'][3]} ({pct(t3['finance'][2], t3['finance'][3])}\\%) \\\\", "t3 fin")
nat_rate = pct(tot[0], tot[1])
main = sub1(main, "With the erroneous memories, unauthorized submission occurs in 98.6\\% of trials; after exact-state repair it occurs in none (Table~\\ref{tab:natural-repair}).",
            f"With the erroneous memories, unauthorized submission occurs in {nat_rate}\\% of trials; after exact-state repair it occurs in {tot[2]} of {tot[3]} (Table~\\ref{{tab:natural-repair}}).", "4.2 repair sentence")
main = sub1(main, "Oracle-exact memory eliminates unauthorized execution across all domains, isolating memory formation as the bottleneck.",
            f"Oracle-exact memory removes unauthorized execution in all but {tot[2]} of {tot[3]} trials, isolating memory formation as the bottleneck.", "t3 caption")
max_F = max(100 * f_rows[d][0][0] / f_rows[d][0][1] for d in DOMS)
main = sub1(main, "writers create false authority for up to 50.2\\% of unauthorized requests; once false authority is present, executors act on it in 98.6\\% of trials.",
            f"writers create false authority for up to {max_F:.1f}\\% of unauthorized requests; once false authority is present, executors act on it in {nat_rate}\\% of trials.", "abstract numbers")
main = sub1(main, "for up to 50.2\\% of unauthorized requests, and, once present, propagates to unauthorized action in 98.6\\% of matched trials. Exact-state repair eliminates these actions, localizing the failure to memory.",
            f"for up to {max_F:.1f}\\% of unauthorized requests, and, once present, propagates to unauthorized action in {nat_rate}\\% of matched trials. Exact-state repair removes these actions in all but {tot[2]} of {tot[3]} trials, localizing the failure to memory.", "contribution numbers")

# Models paragraph
main = sub1(main, "We evaluate five writers: Nemotron 3 Ultra \\citep{nvidia2026nemotron3ultra}, Kimi K2.6 \\citep{moonshot2026kimik26}, GLM 5.2 \\citep{glm5team2026glm5}, Grok 4.3 \\citep{xai2026grok43}, and Qwen-Plus (2025-07-28) \\citep{alibabacloud2025qwenplus}.",
            "We evaluate seven writers: Nemotron 3 Ultra \\citep{nvidia2026nemotron3ultra}, Kimi K2.6 \\citep{moonshot2026kimik26}, GLM 5.2 \\citep{glm5team2026glm5}, Grok 4.3 \\citep{xai2026grok43}, Qwen-Plus (2025-07-28) \\citep{alibabacloud2025qwenplus}, Inkling \\citep{thinkingmachines2026inkling}, and DeepSeek V4.1 Flash \\citep{deepseekai2026deepseekv41flash}.", "writers list")
main = sub1(main, "all models run at temperature 1.0 with a 4,096-token output limit.",
            "all models run at temperature 1.0 with a 4,096-token output limit, except that Inkling and DeepSeek V4.1 Flash reason inside the completion and run with 32,768- and 16,384-token limits.", "output limit")
main = sub1(main, "across five writers, two executors, and three fixed writer-generation seeds", "across seven writers, two executors, and three fixed writer-generation seeds", "estimation five")

# Typed-memory mechanism details
m = {k: PAPER_MECH[k] + ADDED_MECH[k] for k in PAPER_MECH}
old = ("The three-seed typed-incremental analysis covers 540 final writer--case trajectories and 5,550 saved update positions. Free-text memory is excluded from deterministic semantic scoring. Among typed states, 3,464/5,550 (62.4\\%) contain a semantic error and 444/5,550 (8.0\\%) contain an authority-gaining error; 388/540 (71.9\\%) final states are not exact, and request-level false authority is 494/1,980 (24.9\\%).")
new = (f"The three-seed typed-incremental analysis covers {m['traj']} final writer--case trajectories and {m['states']:,} saved update positions. Free-text memory is excluded from deterministic semantic scoring. Among typed states, {m['semantic']:,}/{m['states']:,} ({pct(m['semantic'], m['states'])}\\%) contain a semantic error and {m['gain']}/{m['states']:,} ({pct(m['gain'], m['states'])}\\%) contain an authority-gaining error; {m['final_not_exact']}/{m['traj']} ({pct(m['final_not_exact'], m['traj'])}\\%) final states are not exact, and request-level false authority is {m['F']}/{m['F_n']:,} ({pct(m['F'], m['F_n'])}\\%).")
main = sub1(main, old, new, "mechanism details")
summary["mechanism"] = m

# Executor transfer sentence
ex_us = {}; agree = {}
for dom in DOMS:
    rates = []
    for e in EXS:
        p = P[f"{dom}|ALL|ALL|{e}"]; a = A2[f"{dom}|ALL|ALL|{e}"]
        ex_us[(dom, e)] = (p["unauthorized_submissions"] + a["unauth_sub"], p["unauthorized_trials"] + a["unauth_n"],
                           p["authorized_use"] + a["auth_use"], p["authorized_trials"] + a["auth_n"])
        rates.append(100 * ex_us[(dom, e)][0] / ex_us[(dom, e)][1])
    agree[dom] = (P[f"{dom}|agreement"]["matches"] + AG[f"{dom}|matches"], P[f"{dom}|agreement"]["pairs"] + AG[f"{dom}|pairs"])
    ex_us[(dom, "diff")] = abs(rates[0] - rates[1])
max_diff = max(ex_us[(d, "diff")] for d in DOMS)
ag_rates = sorted(100 * agree[d][0] / agree[d][1] for d in DOMS)
summary["executor"] = {f"{d}|{e}": ex_us[(d, e)] for d in DOMS for e in EXS}; summary["agreement"] = agree; summary["max_exec_diff"] = max_diff
main = sub1(main, "yields unauthorized-submission rates within 1.1 percentage points in each domain, with per-replay agreement between 97.9\\% and 99.5\\%",
            f"yields unauthorized-submission rates within {math.ceil(max_diff * 10) / 10:.1f} percentage points in each domain, with per-replay agreement between {ag_rates[0]:.1f}\\% and {ag_rates[-1]:.1f}\\%", "transfer sentence")

# Writer table (fixed seed, baseline and pressure)
N_BOTH = {"procurement": 288, "cybersecurity": 512, "finance": 256}
head = "    Writer & B & P & B & P & B & P & B & P & B & P & B & P & B & P & B & P \\\\\n    \\midrule\n"
start = main.index(head) + len(head); end = main.index("    \\bottomrule", start)
body = main[start:end]
row_re = re.compile(r"(\\modelname[^\n]*\{(Nemotron 3 Ultra|Grok 4\.3|Kimi K2\.6|GLM 5\.2|Qwen-Plus)\})\n((?:\s*&[^\n]*\n){4})")
paper_rows = []
for mm in row_re.finditer(body):
    vals = [float(v) for v in re.findall(r"(?:\}|\\textbf\{)(\d+\.\d+)", mm.group(3))]
    assert len(vals) == 16, (mm.group(2), vals)
    paper_rows.append((mm.group(1), vals))
assert len(paper_rows) == 5, len(paper_rows)
rows = []  # (name tex, 16 values as floats, counts per domain [(au_b, au_p, us_b, us_p) counts])
for name, vals in paper_rows:
    counts = []
    for i, dom in enumerate(DOMS):
        n = N_BOTH[dom]; counts.append(tuple(rnd(v * n / 100) for v in vals[4 * i:4 * i + 4]))
    rows.append((name, vals, counts))
for wname in ADDED:
    vals = []; counts = []
    for dom in DOMS:
        b, pr = TP["press"][f"{wname}|{dom}|BOTH"]["B"], TP["press"][f"{wname}|{dom}|BOTH"]["P"]
        assert b["auth_n"] == b["unauth_n"] == pr["auth_n"] == pr["unauth_n"] == N_BOTH[dom] and pr["pe"] == 0
        c = (b["auth_use"], pr["auth_use"], b["unauth_sub"], pr["unauth_sub"]); counts.append(c)
        vals += [100 * x / N_BOTH[dom] for x in c]
    vals += [sum(vals[j::4][:3]) / 3 for j in range(4)]
    rows.append((LOGO[wname], vals, counts))
avg_counts = [tuple(sum(r[2][i][j] for r in rows) for j in range(4)) for i in range(3)]
avg_vals = []
for i, dom in enumerate(DOMS):
    avg_vals += [100 * avg_counts[i][j] / (7 * N_BOTH[dom]) for j in range(4)]
avg_vals += [sum(avg_vals[j::4][:3]) / 3 for j in range(4)]
disp = [[round(v, 1) for v in r[1]] for r in rows]
best = []
for col in range(16):
    colvals = [d[col] for d in disp]
    best.append(max(colvals) if (col % 4) < 2 else min(colvals))


def cell(v, col, bold):
    au = (col % 4) < 2
    shade = f"aublue!{rnd((v - 50) * 0.7)}" if au else f"usorange!{rnd(v * 0.9)}"
    s = f"{v:.1f}"
    return f"\\cellcolor{{{shade}}}" + (f"\\textbf{{{s}}}" if bold else s)


def render(name, vals, bold_ok=True):
    d = [round(v, 1) for v in vals]
    lines = [f"    {name}"]
    for i in range(4):
        cells = [cell(d[4 * i + j], 4 * i + j, bold_ok and d[4 * i + j] == best[4 * i + j]) for j in range(4)]
        lines.append("      & " + " & ".join(cells) + (" \\\\" if i == 3 else ""))
    return "\n".join(lines) + "\n"


new_body = "".join(render(n, v) for n, v, _ in rows) + render("\\textit{Average}", avg_vals, bold_ok=False)
main = main[:start] + new_body + main[end:]
summary["writer_table_added"] = {ADDED[i]: rows[5 + i][1] for i in range(2)}; summary["writer_table_average"] = avg_vals
# The sentence under the table quotes the finance average under pressure
main = sub1(main, "raises it in finance from 20.9\\% to 27.3\\%", f"raises it in finance from {avg_vals[10]:.1f}\\% to {avg_vals[11]:.1f}\\%", "pressure finance sentence")

(ICLR / "main.tex").write_text(main, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ multiseed appendix
ms = (ICLR / "multiseed_appendix.tex").read_text(encoding="utf-8")
ms = sub1(ms, "Values pool\n  five writers and both executors within a seed.", "Values pool\n  seven writers and both executors within a seed.", "multiseed caption 1")
ms = sub1(ms, "Values pool all five\n  writers and all four memory conditions.", "Values pool all seven\n  writers and all four memory conditions.", "multiseed caption 3")
ms = sub1(ms, "Table~\\ref{tab:three-seed-condition-counts} gives the seed-specific counts behind the pooled percentages", "Table~\\ref{tab:three-seed-condition-counts} gives the seed-specific counts behind the pooled percentages", "ms intro")


def seed_cells(dom, seed):
    out = []
    for cond in CONDS:
        p = P[f"{dom}|s{seed}|{cond}|BOTH"]; a = A2[f"{dom}|{seed}|{cond}|BOTH"]
        au_k, au_n = p["authorized_use"] + a["auth_use"], p["authorized_trials"] + a["auth_n"]
        us_k, us_n = p["unauthorized_submissions"] + a["unauth_sub"], p["unauthorized_trials"] + a["unauth_n"]
        assert au_n == us_n
        out.append(f"\\shortstack{{A {au_k}/{au_n}\\\\U {us_k}/{us_n}}}")
    return out


s1_start = ms.index("    Procurement & 20260719 &"); s1_end = ms.index("    \\bottomrule", s1_start)
blocks = []
for dom in DOMS:
    for si, seed in enumerate(SEEDS[dom]):
        c = seed_cells(dom, seed)
        lead = f"    {DOMNAME[dom]} & {seed} & " if si == 0 else f"    & {seed} & "
        blocks.append(lead + c[0] + " &\n      " + c[1] + " &\n      " + c[2] + " &\n      " + c[3] + " \\\\\n")
    if dom != "finance":
        blocks.append("    \\addlinespace\n")
ms = ms[:s1_start] + "".join(blocks) + ms[s1_end:]
s2_start = ms.index("    Procurement & \\shortstack{A 1052/1080"); s2_end = ms.index("    \\bottomrule", s2_start)
blocks = []
for dom in DOMS:
    c = [f"\\shortstack{{A {pool[(dom, k)]['au_k']}/{pool[(dom, k)]['au_n']}\\\\U {pool[(dom, k)]['us_k']}/{pool[(dom, k)]['us_n']}}}" for k in CONDS]
    blocks.append(f"    {DOMNAME[dom]} & " + c[0] + " &\n      " + c[1] + " &\n      " + c[2] + " &\n      " + c[3] + " \\\\\n")
ms = ms[:s2_start] + "".join(blocks) + ms[s2_end:]
s3_start = ms.index("    Procurement & 2032/2160"); s3_end = ms.index("    \\bottomrule", s3_start)
blocks = []
for dom in DOMS:
    g, d = ex_us[(dom, "gptoss_baseten")], ex_us[(dom, "deepseek_baseten")]
    blocks.append(f"    {DOMNAME[dom]} & {g[2]}/{g[3]} & {g[0]}/{g[1]} & {d[2]}/{d[3]} & {d[0]}/{d[1]} & {agree[dom][0]}/{agree[dom][1]} \\\\\n")
ms = ms[:s3_start] + "".join(blocks) + ms[s3_end:]
(ICLR / "multiseed_appendix.tex").write_text(ms, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ memory-design appendix (fixed seed, per executor)
md = (ICLR / "memory_design_appendix.tex").read_text(encoding="utf-8")
md = sub1(md, "One fixed seed's $2\\times2$ disaggregation for all five writers.", "One fixed seed's $2\\times2$ disaggregation for all seven writers.", "md caption")
lines = md.split("\n")
panel_order = [(d, e) for d in DOMS for e in EXS]
N_ONE = {"procurement": 36, "cybersecurity": 64, "finance": 32}
out_lines = []; qi = 0; i = 0
while i < len(lines):
    out_lines.append(lines[i])
    if "qwen-logo.png}{Qwen-Plus}}" in lines[i] and lines[i].lstrip().startswith("\\mdwriter"):
        out_lines += lines[i + 1:i + 5]; i += 5
        dom, ex = panel_order[qi]; qi += 1
        for wname in ADDED:
            out_lines.append(f"  \\mdwriter{{{LOGO[wname]}}}")
            for cond in ("one_shot_text", "one_shot_typed", "incremental_text", "incremental_typed"):
                c = FX[f"{wname}|{dom}|{ex}|{cond}"]
                assert c["auth_n"] == c["unauth_n"] == N_ONE[dom] and c["pe"] == 0, (wname, dom, ex, cond, c)
                out_lines.append(f"    {{\\mdcell{{{pct(c['auth_use'], c['auth_n'])}}}{{{pct(c['unauth_sub'], c['unauth_n'])}}}{{{c['auth_use']}}}{{{c['unauth_sub']}}}{{{N_ONE[dom]}}}}}")
        continue
    i += 1
assert qi == 6, qi
(ICLR / "memory_design_appendix.tex").write_text("\n".join(out_lines), encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ transfer / pressure appendix (fixed seed, per executor)
tp = (ICLR / "transfer_pressure_appendix.tex").read_text(encoding="utf-8")
tp = sub1(tp, "averages pool the underlying counts across all five writers.", "averages pool the underlying counts across all seven writers.", "tp caption")
tp = tp.replace("\\multirow{5}{*}", "\\multirow{7}{*}")
N_EX = {"procurement": 144, "cybersecurity": 256, "finance": 128}
lines = tp.split("\n"); out_lines = []; dom = None; ex = None; acc = None; nrows = 0
wrow = re.compile(r"^\s*& \\modelname[^&]*\{[^{}]+\} & (\d+\.\d+) & (\d+\.\d+) & (\d+\.\d+) & (\d+\.\d+) \\\\")
avg_re = re.compile(r"^(\s*& \\textit\{Average\} & )\\textbf\{(\d+\.\d+)\} & \\textbf\{(\d+\.\d+)\} & \\textbf\{(\d+\.\d+)\} & \\textbf\{(\d+\.\d+)\} \\\\")
checks = []
for line in lines:
    mm = re.search(r"\\textbf\{\((a|b|c)\) (Procurement|Cybersecurity|Finance)\}", line)
    if mm:
        dom = mm.group(2).lower()
    if "\\multirow{7}{*}" in line:
        ex = "gptoss_baseten" if "GPT-OSS" in line else "deepseek_baseten"; acc = [0, 0, 0, 0]; nrows = 0
    m2 = wrow.match(line)
    if m2 and acc is not None:
        n = N_EX[dom]
        for j in range(4):
            acc[j] += rnd(float(m2.group(j + 1)) * n / 100)
        nrows += 1
    m3 = avg_re.match(line)
    if m3:
        assert nrows == 5, (dom, ex, nrows)
        n = N_EX[dom]
        five = [100 * acc[j] / (5 * n) for j in range(4)]
        checks.append((dom, ex, [float(m3.group(j + 2)) for j in range(4)], [round(v, 1) for v in five]))
        for wname in ADDED:
            b, pr = TP["press"][f"{wname}|{dom}|{ex}"]["B"], TP["press"][f"{wname}|{dom}|{ex}"]["P"]
            assert b["auth_n"] == b["unauth_n"] == pr["auth_n"] == pr["unauth_n"] == n
            vals = (b["auth_use"], b["unauth_sub"], pr["auth_use"], pr["unauth_sub"])
            for j in range(4):
                acc[j] += vals[j]
            out_lines.insert(len(out_lines) - 1, f"      & {LOGO[wname]} & " + " & ".join(pct(v, n) for v in vals) + " \\\\")
        seven = [100 * acc[j] / (7 * n) for j in range(4)]
        line = m3.group(1) + " & ".join(f"\\textbf{{{v:.1f}}}" for v in seven) + " \\\\"
        acc = None
    out_lines.append(line)
(ICLR / "transfer_pressure_appendix.tex").write_text("\n".join(out_lines), encoding="utf-8", newline="\n")
summary["transfer_average_check"] = checks

# ------------------------------------------------------------------ bibliography
bib = (ICLR / "references.bib").read_text(encoding="utf-8")
if "thinkingmachines2026inkling" not in bib:
    bib = bib.rstrip("\n") + """

@misc{thinkingmachines2026inkling,
  title        = {Inkling},
  author       = {{Thinking Machines Lab}},
  year         = {2026},
  howpublished = {Model release}
}

@misc{deepseekai2026deepseekv41flash,
  title        = {{DeepSeek-V4.1 Flash}},
  author       = {{DeepSeek-AI}},
  year         = {2026},
  howpublished = {Model release}
}
"""
    (ICLR / "references.bib").write_text(bib, encoding="utf-8", newline="\n")

json.dump(summary, open(T / "seven_summary.json", "w"), indent=1, default=str)
print("pooled by condition (AU%, US%):")
for dom in DOMS:
    print("  ", dom, [(c, pct(pool[(dom, c)]["au_k"], pool[(dom, c)]["au_n"]), pct(pool[(dom, c)]["us_k"], pool[(dom, c)]["us_n"])) for c in CONDS])
print("formation:", {d: (pct(*f_rows[d][0]), pct(*f_rows[d][1])) for d in DOMS})
print("repair:", t3, "total", tot)
print("mechanism:", m)
print("executor max diff:", round(max_diff, 2), "agreement:", {d: pct(*agree[d]) for d in DOMS})
print("writer table added rows:", {k: [round(x, 1) for x in v] for k, v in summary["writer_table_added"].items()})
print("writer table average:", [round(x, 1) for x in avg_vals])
print("transfer average self-check (printed five-writer avg vs recomputed):")
for c in checks:
    print("  ", c)
