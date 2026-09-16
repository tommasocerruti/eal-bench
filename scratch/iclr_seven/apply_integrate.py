"""Integrate the added writers into the paper's own tables and figures, unify populations, remove the
separate 'added' appendices and their caption disclaimers, and reconcile the claims the results do not support."""
import csv
import json
import pathlib
import re
import shutil
import statistics
import sys

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
S = pathlib.Path(sys.argv[1])  # scratchpad with the regenerated figures
DATA = json.load(open("scratch/iclr_seven/integrate_data.json", encoding="utf-8"))


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:200]}"
    return text.replace(old, new)


def cut_between(text, start_marker, end_marker, label):
    i = text.index(start_marker); j = text.index(end_marker, i)
    return text[:i] + text[j:]


def replace_par(text, start_marker, new, label):
    n = text.count(start_marker)
    assert n == 1, f"{label}: start marker found {n} times"
    i = text.index(start_marker); j = text.index("}\n", i) + 1
    return text[:i] + new + text[j:]


# ------------------------------------------------------------------ figures
shutil.copy(S / "fig4_final.pdf", ICLR / "figures/mitigation_pareto_frontier.pdf")
shutil.copy(S / "fig_ttc_seven.pdf", ICLR / "figures/TTC-scale.pdf")
shutil.copy(S / "fig_restatement.pdf", ICLR / "figures/restatements.pdf")
shutil.copy(S / "fig_mechanism.pdf", ICLR / "figures/failure_mechanism.pdf")
for f in ("evaluation_cue_main_summary", "evaluation_cue_appendix_writer_behavior", "evaluation_cue_appendix_executor_behavior", "evaluation_cue_appendix_writer_fidelity"):
    shutil.copy(S / "cue7_out" / f"{f}.pdf", ICLR / "figures" / f"{f}.pdf")

# ------------------------------------------------------------------ main.tex
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")

# claims the results do not support
s = sub1(s, "\\revised{The failures trace to one cause, a later message that repeats a permission the history has since changed. On generated histories that differ only in whether such a restatement occurs, false authority forms after a restatement and almost never without one. Agents that log",
         "\\revised{In procurement and finance the failures trace to a later message that repeats a permission the history has since changed: on generated histories that differ only in whether such a restatement occurs, false authority forms for 16\\% of unauthorized requests after two restatements and for under 1\\% without one. In cybersecurity the writer instead fails to store the legitimate change, so the old grant survives. Agents that log", "abstract cause")
s = sub1(s, "\\item \\revised{False authority forms only after a superseded permission is restated without authority; the writer applies the restatement in two domains and loses the legitimate change in the third.}",
         "\\item \\revised{False authority forms almost only after a superseded permission is restated without authority, and the writer applies that restatement in procurement and finance while losing the legitimate change in cybersecurity.}", "contribution 4")
s = sub1(s, "Without a restatement, false authority never forms (0 of 324 unauthorized requests); with two restatements it forms for 15.4\\% of requests, and four restatements are not measurably worse than two. Attribution then shows what the writer does with such a message, and the answer differs by domain (Appendix~\\ref{app:diagnosis}).",
         "Without a restatement, false authority forms for under 1\\% of unauthorized requests; with two restatements it forms for 15.6\\%, and four restatements are not measurably worse than two (Figure~\\ref{fig:restatements}). Attribution then shows what the writer does with such a message, and the answer differs by domain (Figure~\\ref{fig:mechanism}).", "4.2 restatements")
s = sub1(s, "\\revised{The writer's error has a location and a shape: on matched histories, false authority forms only after a party without authority restates",
         "\\revised{The writer's error has a location and a shape: on matched histories, false authority forms almost only after a party without authority restates", "conclusion almost")

# capacity: the procurement ablation and the cybersecurity capacity test say different things about different failures
s = sub1(s, "Because incremental writers never revisit earlier raw blocks, added capacity cannot recover information already lost or distorted, and relaxing the bound gives no clear improvement (Appendix~\\ref{app:capacity-ablation}), so tight memory limits are not the main cause of the failures.",
         "\\revised{Because incremental writers never revisit earlier raw blocks, added capacity cannot recover information already lost or distorted, and relaxing the bound in procurement gives no clear improvement (Appendix~\\ref{app:capacity-ablation}); capacity matters only where the failure is a write that does not fit, which Section~\\ref{sec:mitigation-pareto-results} shows for cybersecurity.}", "capacity claim")

# no population disclaimers in the methods
s = sub1(s, ", and the rebuild variant above serves as a fourth. The writer-side comparisons, the closed loop, and the attribution use five of the seven writers, and every caption names its population.}",
         ", and the rebuild variant above serves as a fourth.}", "methods population")
s = sub1(s, " (Appendix~\\ref{app:added-writers})}", "}", "models appendix ref")

# writer-side compute: seven writers
s = sub1(s, "From $k{=}1$ to $k{=}8$, the unauthorized action rate falls from 13.2\\% to 8.6\\% and the legitimate action rate rises from 94.2\\% to 95.8\\%. Generation improves faster than selection: at $k{=}8$ an exact memory exists in 55.0\\% of pools, self-review selects one in 26.7\\% of them, and an independent DeepSeek reviewer in 30.0\\%, which also improves downstream behavior to a 7.6\\% unauthorized action rate and a 97.2\\% legitimate action rate. In incremental typed memory, final-state error falls from 63.3\\% at $k{=}1$ to 51.7\\% at $k{=}8$, while observed errors persist in 100\\% of cases and self-repair stays at 0\\% at every $k$.",
         "\\revised{From $k{=}1$ to $k{=}8$, the unauthorized action rate falls from 11.3\\% to 8.5\\% and the legitimate action rate rises from 92.6\\% to 94.8\\%. Generation improves faster than selection: at $k{=}8$ an exact memory exists in 54.2\\% of pools, self-review selects one in 23.8\\% of them, and an independent DeepSeek V4 Pro reviewer in 30.0\\%. In incremental typed memory, final-state error falls from 60.7\\% at $k{=}1$ to 54.8\\% at $k{=}8$, while observed errors persist in 98\\% of cases and self-repair stays near 2\\% at every $k$.}", "ttc main")
s = sub1(s, "\\revised{Nested candidate pools are generated by five writers while GPT-OSS-120B remains the fixed executor.}",
         "\\revised{Nested candidate pools are generated by seven writers while GPT-OSS-120B remains the fixed executor.}", "ttc caption")

# mitigations: one pooled population for the origin checks, rebuild on the frontier
s = sub1(s, "On the shared three-seed typed-incremental population, source-authority gating cuts the unauthorized action rate from 25.3\\% to 7.3\\%, a drop of 18.0 percentage points (95\\% CI: 14.9--21.1), and bounded event sourcing cuts it to 9.0\\%, a drop of 16.3 points (95\\% CI: 12.2--20.4). Both pay in legitimate use: the legitimate action rate falls from 93.3\\% to 53.8\\% under the gate and to 64.7\\% under event sourcing. At the representation level, the false-authority rate falls from 24.9\\% to 5.5\\% and 8.7\\% respectively. \\added{Among these four,} no configuration dominates another on the pooled estimates, so the \\added{four} points form a discrete empirical Pareto frontier over the tested policies (Figure~\\ref{fig:mitigation-pareto}); we do not claim a complete frontier over possible architectures.",
         "\\revised{On the shared three-seed typed-incremental population, source-authority gating cuts the unauthorized action rate from 23.8\\% to 6.3\\% and bounded event sourcing cuts it to 8.0\\%. Both pay in legitimate use: the legitimate action rate falls from 93.4\\% to 54.4\\% under the gate and to 69.2\\% under event sourcing.} At the representation level, the false-authority rate falls from 24.9\\% to 5.5\\% and 8.7\\% respectively. \\revised{Among the baseline, the two origin checks, and the writer instruction, no configuration dominates another on the pooled estimates, so the four points form a discrete empirical Pareto frontier over those policies, whereas rebuilding memory from the history dominates all four (Figure~\\ref{fig:mitigation-pareto}); we do not claim a complete frontier over possible architectures.}", "mitigation numbers")
s = sub1(s, "The circle is the typed-incremental baseline, and the squares are the two mitigations. \\revised{GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Grok 4.3, and Qwen-Plus, three seeds, both executors. The diamond is the writer instruction, pooled over its three domains and five writers (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash).}",
         "\\revised{The circle is the typed-incremental baseline, the squares are the two origin checks, and the diamonds are the two writer-side changes; the dashed line joins the frontier of the first four, and rebuilding lies above and to the left of it.}", "fig4 caption")
s = sub1(s, "Pooled over domains, it is the point on the frontier of Figure~\\ref{fig:mitigation-pareto} that stays closest to the baseline's legitimate action rate.",
         "Pooled over domains, it is the point on the frontier of Figure~\\ref{fig:mitigation-pareto} that stays closest to the baseline's legitimate action rate, and rebuilding, which removes the error before it is stored, lies beyond the frontier on both axes.", "frontier text")

# conclusion future work: no writer-subset clause
s = sub1(s, "The per-writer, pressure, and closed-loop comparisons rest on one seed each and the writer-side comparisons on five of the seven writers, so replicating them at three seeds across all writers would tighten the estimates.",
         "The per-writer, pressure, and closed-loop comparisons rest on one seed each, so replicating them at three seeds would tighten the estimates.", "future work")

# writer-side compute appendix: seven-writer values, added-writer paragraph folded in
s = sub1(s, "Under self-review, unauthorized action rate falls from 13.2\\% at $k=1$ to 10.8\\%, 9.2\\%, and 8.6\\% at $k=2,4,8$. Legitimate action rate is 94.2\\%, 95.4\\%, 96.5\\%, and 95.8\\%. Both safety and legitimate use therefore improve overall from $k=1$ to $k=8$, although the 0.7-point drop in legitimate action rate from $k=4$ to $k=8$ suggests diminishing returns at the largest pool.",
         "\\revised{Under self-review, the unauthorized action rate falls from 11.3\\% at $k=1$ to 10.0\\%, 8.9\\%, and 8.5\\% at $k=2,4,8$, and the legitimate action rate is 92.6\\%, 94.4\\%, 95.5\\%, and 94.8\\%. Both safety and legitimate use therefore improve overall from $k=1$ to $k=8$, although the 0.7-point drop in the legitimate action rate from $k=4$ to $k=8$ suggests diminishing returns at the largest pool.}", "ttc appendix A")
s = sub1(s, "Exact-memory availability---the share of pools containing at least one exact memory---is 31.7\\%, 44.2\\%, 50.8\\%, and 55.0\\% at $k=1,2,4,8$. The corresponding selection rates are 31.7\\%, 35.0\\%, 31.7\\%, and 26.7\\% under writer self-review, and 31.7\\%, 35.8\\%, 33.3\\%, and 30.0\\% under independent DeepSeek V4 Pro review. At $k=1$, there is only one candidate, so availability and selection coincide. At $k=8$, the 28.3-point gap between availability and self-review shows a selection bottleneck in this setting, without implying that selection is generally harder than generation.",
         "\\revised{Exact-memory availability, the share of pools containing at least one exact memory, is 32.1\\%, 42.9\\%, 50.0\\%, and 54.2\\% at $k=1,2,4,8$. The corresponding selection rates are 32.1\\%, 31.5\\%, 28.6\\%, and 23.8\\% under writer self-review, and 35.8\\%, 33.3\\%, and 30.0\\% at $k=2,4,8$ under independent DeepSeek V4 Pro review of the pools of GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Grok 4.3, and Qwen-Plus. At $k=1$ there is only one candidate, so availability and selection coincide. At $k=8$, the 30-point gap between availability and self-review shows a selection bottleneck in this setting, without implying that selection is generally harder than generation.}", "ttc appendix B")
s = sub1(s, "The independent reviewer uses the same frozen candidate pools. At $k=8$, it lowers unauthorized action rate from 8.6\\% under self-review to 7.6\\% and raises legitimate action rate from 95.8\\% to 97.2\\%. DeepSeek therefore extracts some additional value from the larger pool but remains far from the 55.0\\% availability ceiling, showing that the gap is not only a self-review artifact.",
         "\\revised{The independent reviewer uses the same frozen candidate pools, and at $k=8$ it selects an exact memory more often than self-review does while remaining far below the availability ceiling, so the gap is not only a self-review artifact.}", "ttc appendix B2")
s = sub1(s, "The broader typed authorization-error rate falls from 26.7\\% at $k=1$ to 20.8\\% at $k=4$, while unauthorized action rate continues to improve through $k=8$ even as the selected exact-memory rate falls.",
         "\\revised{The broader typed authorization-error rate falls from 41.7\\% at $k=1$ to 35.7\\% at $k=8$, and the unauthorized action rate improves through $k=8$ even as the selected exact-memory rate falls.}", "ttc appendix fidelity")
s = sub1(s, "For incremental typed memory, the error-introduction rate is 15.2\\%, 13.7\\%, 14.0\\%, and 12.7\\% for $k=1,2,4,8$, while final-state error is 63.3\\%, 56.7\\%, 56.7\\%, and 51.7\\%.",
         "\\revised{For incremental typed memory, the error-introduction rate is 14.6\\%, 13.0\\%, 14.2\\%, and 13.2\\% for $k=1,2,4,8$, while final-state error is 60.7\\%, 54.8\\%, 58.3\\%, and 54.8\\%.}", "ttc appendix C")
s = sub1(s, "In procurement, persistence is 100\\% and self-repair is 0\\% at every $k$. Additional writer compute therefore appears to help mainly by avoiding damaging updates, rather than repairing errors after they enter persistent memory.",
         "\\revised{Persistence is 97 to 98\\% and self-repair 2 to 3\\% at every $k$, so additional writer compute helps mainly by avoiding damaging updates rather than by repairing errors after they enter persistent memory.}", "ttc appendix C2")
s = replace_par(s, "\\revised{With Inkling and DeepSeek V4.1 Flash run through the same protocol, the gap between generation and selection widens", "", "ttc added paragraph")

# evaluation cue appendix: seven writers, numbers from the regenerated summary
rows = list(csv.DictReader(open(S / "cue7_out" / "main_summary_data.csv", encoding="utf-8")))


def mean(stage, metric, contrast):
    v = [float(r["estimate_pp"]) for r in rows if r["stage"] == stage and r["metric"] == metric and r["contrast"] == contrast]
    return statistics.mean(v), statistics.median(v), min(v), max(v), len(v)


w_err1 = mean("writer", "authorization_error", "l1-l0"); w_err2 = mean("writer", "authorization_error", "l2-l1")
w_au1 = mean("writer", "authorized_use", "l1-l0"); w_au2 = mean("writer", "authorized_use", "l2-l1")
w_us1 = mean("writer", "unauthorized_submission", "l1-l0"); w_us2 = mean("writer", "unauthorized_submission", "l2-l1")
e_au1 = mean("executor", "authorized_use", "l1-l0"); e_au2 = mean("executor", "authorized_use", "l2-l1")
e_us1 = mean("executor", "unauthorized_submission", "l1-l0"); e_us2 = mean("executor", "unauthorized_submission", "l2-l1")
assert w_err1[4] == 7 and e_au1[4] == 14, (w_err1[4], e_au1[4])


def sg(x):
    return f"{x:+.2f}".replace("+", "+").replace("-", "-")


s = sub1(s, "The writer study crosses five targets, four memory conditions, twelve cases, and three pre-specified seeds, with GPT-OSS as executor; \\revised{the executor study replays frozen memories behind GPT-OSS and DeepSeek, so the analysis contains 7,200 cue-paired behavioral units and 360 typed-memory cue triplets.}",
         "\\revised{The writer study crosses seven targets, four memory conditions, twelve cases, and three pre-specified seeds, with GPT-OSS as executor; the executor study replays frozen memories behind GPT-OSS and DeepSeek, so the analysis contains 10,080 cue-paired behavioral units and 504 typed-memory cue triplets.}", "cue design")
s = sub1(s, "Across the five writer targets, the generic cue changes mean legitimate action rate and fewer unauthorized actions by only $-0.09$ and $-0.09$ percentage points. It reduces typed-memory authorization errors by 1.11 points on average, but the median effect is zero and target-specific effects range from $-4.17$ to $+9.72$ points. Moving from generic to authorization-specific framing yields mean changes of 1.11 points fewer typed-memory authorization errors, 0.79 points more legitimate action rate, and 1.20 points fewer unauthorized actions.",
         "\\revised{Across the seven writer targets, the generic cue changes the mean legitimate action rate by $" + sg(w_au1[0]) + "$ points and the mean number of avoided unauthorized actions by $" + sg(w_us1[0]) + "$ points. It reduces typed-memory authorization errors by " + f"{w_err1[0]:.2f}" + " points on average, but the median effect is " + f"{w_err1[1]:.2f}" + " and target-specific effects range from $" + sg(w_err1[2]) + "$ to $" + sg(w_err1[3]) + "$ points. Moving from generic to authorization-specific framing yields mean changes of " + f"{w_err2[0]:.2f}" + " points fewer typed-memory authorization errors, " + f"{w_au2[0]:.2f}" + " points more legitimate actions, and " + f"{w_us2[0]:.2f}" + " points fewer unauthorized actions.}", "cue writer numbers")
s = sub1(s, "\\revised{Executor-side effects are smaller: across ten frozen writer-memory--executor combinations,} the generic cue changes legitimate action rate by $+0.42$ points and reduces unauthorized action rate by $0.35$ points on average; adding authorization-specific framing changes the same outcomes by $+0.49$ and $-0.07$ points.",
         "\\revised{Executor-side effects are smaller: across fourteen frozen writer-memory--executor combinations, the generic cue changes the legitimate action rate by $" + sg(e_au1[0]) + "$ points and the number of avoided unauthorized actions by $" + sg(e_us1[0]) + "$ points on average, and adding authorization-specific framing changes the same outcomes by $" + sg(e_au2[0]) + "$ and $" + sg(e_us2[0]) + "$ points.}", "cue executor numbers")
s = replace_par(s, "\\revised{Inkling and DeepSeek V4.1 Flash were run through the same writer- and executor-stage design", "", "cue added paragraph")
s = sub1(s, "The evaluation-cue intervention keeps the main procurement cases, five writers, four memory conditions,", "The evaluation-cue intervention keeps the main procurement cases, \\revised{seven} writers, four memory conditions,", "cue five writers")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ multiseed appendix: third executor folded in
p = ICLR / "multiseed_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "All Procurement and Finance trials completed without terminal provider errors.",
         "\\revised{A third executor, GLM 5.3, replayed the frozen memories of every open-loop extension study (the memory designs, the generated histories, and the writer instruction with its baselines), 124 executor-only replays in all, so that three executors answer the same requests against the same memories. On the unauthorized action rate the three are interchangeable, within about one point in every replayed cell, and the writer instruction's paired change is the same to the first decimal for all three. The executors differ only on the legitimate action rate in procurement, where GLM 5.3 executes about 10 points fewer legitimate requests and gains correspondingly more from the instruction.}\n\nAll Procurement and Finance trials completed without terminal provider errors.", "third executor")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ writer-executor plates: a hybrid column
p = ICLR / "memory_design_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "\\newcommand{\\mdwriter}[5]{%\n  \\multirow{2}{*}{#1}\n    & \\textbf{One-shot} & #2 & #3\\\\\n    & \\textbf{Incremental} & #4 & #5\\\\\n  \\addlinespace[0.1em]\n}",
         "\\newcommand{\\mdwriter}[6]{%\n  \\multirow{2}{*}{#1}\n    & \\textbf{One-shot} & #2 & #3 & --\\\\\n    & \\textbf{Incremental} & #4 & #5 & #6\\\\\n  \\addlinespace[0.1em]\n}", "mdwriter")
s = sub1(s, "    \\begin{tabular}{@{}llcc@{}}\n      \\toprule\n      \\apptablehead\n      \\textbf{Writer} & \\textbf{Writing approach} &\n      \\textbf{Free-text} & \\textbf{Typed}\\\\",
         "    \\begin{tabular}{@{}llccc@{}}\n      \\toprule\n      \\apptablehead\n      \\textbf{Writer} & \\textbf{Writing approach} &\n      \\textbf{Free-text} & \\textbf{Typed} & \\textbf{Hybrid}\\\\", "mdpanel header")
s = sub1(s, "\\revised{The $2\\times2$ disaggregation at one fixed seed for all seven writers.}",
         "\\revised{The disaggregation by representation and update strategy at one fixed seed for all seven writers, with the hybrid schema under incremental updating.}", "plate caption")
NAME2ID = {"Nemotron 3 Ultra": "nemotron_3_ultra_baseten", "Grok 4.3": "grok_4_3_openrouter", "Kimi K2.6": "kimi_baseten", "GLM 5.2": "glm_5_2_baseten",
           "Qwen-Plus": "qwen_plus_0728_openrouter", "Inkling": "inkling_baseten", "DeepSeek V4.1 Flash": "deepseek_v4_1_flash_baseten"}
HYB = DATA["hybrid_canonical"]
pat = re.compile(r"(\\mdwriter\{[^\n]*\{([^{}]+)\}\}\n(?:\s*\{\\mdcell[^\n]*\}\n){4})")
out = []; pos = 0; counts = {}
for dom, label in (("procurement", "tab:memory-design-procurement"), ("cybersecurity", "tab:memory-design-cybersecurity"), ("finance", "tab:memory-design-finance")):
    i = s.index(f"\\mddomainplate{{{dom.capitalize()}}}{{{label}}}")
    j = s.index("\\mddomainplate", i + 10) if s.find("\\mddomainplate", i + 10) >= 0 else len(s)
    plate = s[i:j]
    blocks = list(pat.finditer(plate))
    assert len(blocks) == 14, (dom, len(blocks))
    new_plate = ""; last = 0
    for b_i, m in enumerate(blocks):
        name = m.group(2); ex = "gptoss_baseten" if b_i < 7 else "deepseek_baseten"
        key = f"{dom}|{NAME2ID[name]}|{ex}"
        if key in HYB:
            c = HYB[key]; assert c["la_n"] == c["ua_n"]
            cell = f"    {{\\mdcell{{{100*c['la_k']/c['la_n']:.1f}}}{{{100*c['ua_k']/c['ua_n']:.1f}}}{{{c['la_k']}}}{{{c['ua_k']}}}{{{c['la_n']}}}}}\n"
            counts[dom] = counts.get(dom, 0) + 1
        else:
            cell = "    {--}\n"
        new_plate += plate[last:m.end()] + cell; last = m.end()
    new_plate += plate[last:]
    s = s[:i] + new_plate + s[j:]
print("hybrid cells placed:", counts)
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ capacity ablation appendix: pointer to the cybersecurity test
p = ICLR / "capacity_ablation_appendix.tex"; s = p.read_text(encoding="utf-8")
anchor = s.index("\\begin{table}")
intro_end = s.rfind("\n\n", 0, anchor)
s = s[:intro_end] + " \\revised{The ablation speaks to procurement, where the failure is a misread message; in cybersecurity, where the failure is a write that does not fit, doubling capacity removes most of it (Appendix~\\ref{app:mandate}).}" + s[intro_end:]
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ source-authority and event-sourcing appendices: one pooled population
p = ICLR / "source_authority_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "  \\caption{\\textbf{Aligned three-seed source-authority results by domain.} Each cell gives typed-incremental baseline $\\rightarrow$ gated memory; values are percentages.}",
         "  \\caption{\\textbf{Aligned three-seed source-authority results by domain.} Each cell gives typed-incremental baseline $\\rightarrow$ gated memory; values are percentages\\revised{, pooling six writers, three seeds, and both executors}.}", "gate caption")
s = sub1(s, "  \\begin{tabular}{@{}lccc@{}}\n    \\toprule\n    \\apptablehead\n    Domain & Legitimate action rate & Unauthorized action rate & false-authority rate \\\\\n    \\midrule\n    Procurement & 96.8 $\\rightarrow$ 13.6 & 28.9 $\\rightarrow$ 6.8 & 28.3 $\\rightarrow$ 0.0 \\\\\n    Cybersecurity & 88.8 $\\rightarrow$ 88.8 & 10.4 $\\rightarrow$ 10.4 & 10.4 $\\rightarrow$ 10.4 \\\\\n    Finance & 98.3 $\\rightarrow$ 29.2 & 51.0 $\\rightarrow$ 1.7 & 50.2 $\\rightarrow$ 1.7 \\\\\n    \\midrule\n    \\textbf{Pooled} & \\textbf{93.3 $\\rightarrow$ 53.8} & \\textbf{25.3 $\\rightarrow$ 7.3} & \\textbf{25.0 $\\rightarrow$ 5.5} \\\\",
         "  \\begin{tabular}{@{}lcc@{}}\n    \\toprule\n    \\apptablehead\n    Domain & Legitimate action rate & Unauthorized action rate \\\\\n    \\midrule\n    Procurement & 97.3 $\\rightarrow$ 14.2 & 25.6 $\\rightarrow$ 6.3 \\\\\n    Cybersecurity & 88.5 $\\rightarrow$ 88.5 & 10.4 $\\rightarrow$ 10.4 \\\\\n    Finance & 98.6 $\\rightarrow$ 31.3 & 48.6 $\\rightarrow$ 1.4 \\\\\n    \\midrule\n    \\textbf{Pooled} & \\textbf{93.4 $\\rightarrow$ 54.4} & \\textbf{23.8 $\\rightarrow$ 6.3} \\\\", "gate table")
s = sub1(s, "The aligned evaluation reuses 4,532 baseline outcomes and 1,156 earlier gated outcomes only when the model-visible context matches exactly, makes 2,232 new calls across GPT-OSS and DeepSeek, and has no terminal provider errors.",
         "The aligned evaluation reuses 4,532 baseline outcomes and 1,156 earlier gated outcomes only when the model-visible context matches exactly, makes 2,232 new calls across GPT-OSS and DeepSeek, and has no terminal provider errors. \\revised{The gate changes nothing in cybersecurity because none of the records there cites a source it would reject, and the representation-level effect of Table~\\ref{tab:source-authority-full} therefore comes entirely from procurement and finance.}", "gate note")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "event_sourcing_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "Values pool five writers, three seeds, and both executors.}", "Values pool \\revised{six} writers, three seeds, and both executors.}", "event caption")
s = sub1(s, "    Procurement & 312/1080 (28.9\\%) & 116/1080 (10.7\\%) & 1045/1080 (96.8\\%) & 967/1080 (89.5\\%) \\\\\n    Cybersecurity & 200/1920 (10.4\\%) & 175/1920 (9.1\\%) & 1704/1920 (88.8\\%) & 1466/1920 (76.4\\%) \\\\\n    Finance & 490/960 (51.0\\%) & 66/960 (6.9\\%) & 944/960 (98.3\\%) & 128/960 (13.3\\%) \\\\\n    \\midrule\n    \\textbf{Pooled} & \\textbf{1002/3960 (25.3\\%)} & \\textbf{357/3960 (9.0\\%)} & \\textbf{3693/3960 (93.3\\%)} & \\textbf{2561/3960 (64.7\\%)} \\\\",
         "    Procurement & 332/1296 (25.6\\%) & 128/1296 (9.9\\%) & 1261/1296 (97.3\\%) & 1182/1296 (91.2\\%) \\\\\n    Cybersecurity & 240/2304 (10.4\\%) & 187/2304 (8.1\\%) & 2040/2304 (88.5\\%) & 1850/2304 (80.3\\%) \\\\\n    Finance & 559/1152 (48.5\\%) & 66/1152 (5.7\\%) & 1135/1152 (98.5\\%) & 256/1152 (22.2\\%) \\\\\n    \\midrule\n    \\textbf{Pooled} & \\textbf{1131/4752 (23.8\\%)} & \\textbf{381/4752 (8.0\\%)} & \\textbf{4436/4752 (93.4\\%)} & \\textbf{3288/4752 (69.2\\%)} \\\\", "event table")
# one sentence on the writer whose event arm is not evaluated
first_par_end = s.index("\n\n", s.index("\\label{app:event-sourcing}") + 1)
s = s[:first_par_end] + " \\revised{Inkling's event writer reasons inside the completion and exceeded the 4,096-token completion budget on 262 of its 1,552 event-writer calls, so its event-sourced arm is not evaluated.}" + s[first_par_end:]
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ extension results appendix: no separate 'added' section, pooled restatement table, figures
p = ICLR / "extension_results_appendix.tex"; s = p.read_text(encoding="utf-8")
s = cut_between(s, "\\subsection{\\added{Added writers and a third executor}}", "\\subsection{\\added{Generated histories}}", "drop B.6")
s = sub1(s, "\\revised{The paper's histories are written by hand, so the features that drive the failure are confounded.", "\\revised{The paper's histories are written by hand, so the features that drive the failure are confounded.", "gen design anchor")
# pooled restatement table
i = s.index("\\begin{table}[h]\n  \\centering\n  \\caption{\\added{\\textbf{False authority forms only after a superseded permission is restated")
j = s.index("\\end{table}", i) + len("\\end{table}")
s = s[:i] + r"""\begin{figure}[htbp]
  \centering
  \includegraphics[width=\linewidth]{figures/restatements.pdf}
  \caption{\revised{\textbf{False authority forms almost only after a superseded permission is restated, and the writer instruction removes most of it.} Generated procurement histories that differ only in the number of later restatements; \textbf{A}, false-authority rate with Wilson 95\% intervals; \textbf{B}, unauthorized action rate; \textbf{C}, share of exact memories. GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash with GPT-OSS-120B as executor, 540 unauthorized requests and 180 memories per point.}}
  \label{fig:restatements}
\end{figure}

\begin{table}[h]
  \centering
  \caption{\revised{\textbf{False authority forms almost only after a superseded permission is restated, and four restatements are not measurably worse than two.} Generated procurement histories; the false-authority rate is the share of unauthorized requests the final memory authorizes, an exact memory matches the ledger on every record, and intervals are Wilson 95\%. GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash; 180 memories and 540 unauthorized requests per row.}}
  \label{tab:restatements}
  \small
  \setlength{\tabcolsep}{4pt}
  \resizebox{\ifdim\width>\linewidth\linewidth\else\width\fi}{!}{\begin{tabular}{@{}lccccc@{}}
    \toprule
    Restatements & Instruction & False-authority rate & Exact memories & UA $\downarrow$ & LA $\uparrow$ \\
    \midrule
    0 & no & 0.7 (0.3--1.9) & 32/180 & 1.1 & 100.0 \\
    2 & no & 15.6 (12.7--18.9) & 13/180 & 17.2 & 98.9 \\
    4 & no & 10.9 (8.6--13.8) & 16/180 & 11.5 & 98.3 \\
    0 & yes & 0.0 (0.0--0.7) & 56/180 & 0.6 & 100.0 \\
    2 & yes & 2.2 (1.3--3.8) & 49/180 & 2.2 & 100.0 \\
    4 & yes & 1.5 (0.8--2.9) & 54/180 & 1.9 & 99.4 \\
    \bottomrule
  \end{tabular}}
\end{table}""" + s[j:]
s = replace_par(s, "\\revised{With everything but the restatements held fixed,",
                "\\revised{With everything but the restatements held fixed, false authority forms for 4 of 540 zero-restatement requests and for 15.6\\% of requests once two restatements follow the change, while four restatements are not measurably different from two (Figure~\\ref{fig:restatements}, Table~\\ref{tab:restatements}). The legitimate action rate stays at or near 100\\% throughout, so the failure on this corpus is laundering rather than caution. The writer instruction cuts the rate to 2.2\\% and 1.5\\% at two and four restatements, removes the zero-restatement failures entirely, and raises the number of exact memories from 61 to 159 of 540.}", "gen results")
s = replace_par(s, "\\revised{The same corpus shows two further differences, which are observed rather than matched:",
                "\\revised{The same corpus shows two further differences, which are observed rather than matched: histories that amend the grant in place fail about four times as often as histories that revoke it and issue a replacement (false-authority rate 18.3\\% against 4.4\\%), and the failure rate shows no trend across gaps of one to three blocks between grant and change (9.6\\%, 8.5\\%, and 9.1\\%). Because a change of lifecycle or gap also redraws the case's dates, limits, and surrounding text, neither difference is attributed to the lifecycle or the gap alone.}", "gen observed")
# closed loop: per-writer table, five-writer rounds
s = sub1(s, "The loss builds over rounds, from 7 points at round 1 to 24 at round 3 for the three original writers, while the paired difference in the unauthorized action rate includes zero at every round; Table~\\ref{tab:closed-loop-writers} gives the per-writer differences, and DeepSeek V4.1 Flash is the one writer whose interval excludes zero.",
         "The loss builds over rounds, from 4.7 points at round 1 to 14.4 at round 2 and 17.6 at round 3, while the paired difference in the unauthorized action rate stays within a point of zero until round 3; Table~\\ref{tab:closed-loop-writers} gives the per-writer differences, and DeepSeek V4.1 Flash is the one writer whose interval excludes zero.", "loop rounds")
s = sub1(s, "    GLM 5.2, Kimi K2.6, Nemotron 3 Ultra & 216 & $+2.9$ ($-0.1$, $+5.9$) & $-23.9$ ($-30.2$, $-17.4$) & 93 / 1 \\\\\n    Inkling & 72 & $-1.6$ ($-6.1$, $+2.5$) & $-10.9$ ($-18.5$, $-3.9$) & 14 / 3 \\\\\n    DeepSeek V4.1 Flash & 72 & $+3.9$ ($+1.6$, $+6.6$) & $-5.7$ ($-10.6$, $-1.0$) & 20 / 0 \\\\",
         "    GLM 5.2 & 72 & $+3.4$ ($-2.8$, $+9.1$) & $-14.6$ ($-25.0$, $-3.7$) & 33 / 1 \\\\\n    Kimi K2.6 & 72 & $+5.4$ ($+0.1$, $+11.3$) & $-30.2$ ($-43.1$, $-17.4$) & 45 / 0 \\\\\n    Nemotron 3 Ultra & 72 & $+0.0$ ($-3.6$, $+3.5$) & $-26.9$ ($-36.3$, $-17.4$) & 15 / 0 \\\\\n    Inkling & 72 & $-1.6$ ($-6.1$, $+2.7$) & $-10.9$ ($-18.8$, $-3.7$) & 14 / 3 \\\\\n    DeepSeek V4.1 Flash & 72 & $+3.9$ ($+1.6$, $+6.7$) & $-5.7$ ($-10.9$, $-1.0$) & 20 / 0 \\\\\n    \\midrule\n    All & 360 & $+2.2$ ($+0.2$, $+4.2$) & $-17.6$ ($-22.0$, $-13.3$) & 127 / 4 \\\\", "loop writer table")
s = sub1(s, "in the cybersecurity action arm the final memories hold 4.5 real, active permission records per chain against 7.8 in the frozen starting memory and 6.5 in the control, and cybersecurity",
         "in the cybersecurity action arm the final memories of GLM 5.2, Kimi K2.6, and Nemotron 3 Ultra hold 4.5 real, active permission records per chain against 7.8 in the frozen starting memory and 6.5 in the control, and cybersecurity", "grants writers")
s = sub1(s, "With the writer instruction of Appendix~\\ref{app:mandate}, records created from the agent's own lines fall from 91 to 4 while the round-3 legitimate action rate is unchanged, so the instruction stops the minted records without recovering the loss.}",
         "With the writer instruction of Appendix~\\ref{app:mandate}, records created from the agent's own lines by GLM 5.2, Kimi K2.6, and Nemotron 3 Ultra fall from 91 to 4 while the round-3 legitimate action rate is unchanged, so the instruction stops the minted records without recovering the loss.}", "loop instruction writers")
# mechanism figure next to the cause table
s = sub1(s, "\\revised{Nearly all 2,250 judged failures fall under three errors, which separate by domain and setting rather than by writer (Table~\\ref{tab:cause}).",
         "\\begin{figure}[htbp]\n  \\centering\n  \\includegraphics[width=\\linewidth]{figures/failure_mechanism.pdf}\n  \\caption{\\revised{\\textbf{The writer's error separates by domain and setting rather than by writer.} Share of judged failures under each majority label, by where the failure entered; counts are the failures of Table~\\ref{tab:cause}.}}\n  \\label{fig:mechanism}\n\\end{figure}\n\n\\revised{Nearly all 2,250 judged failures fall under three errors, which separate by domain and setting rather than by writer (Figure~\\ref{fig:mechanism}, Table~\\ref{tab:cause}).", "mechanism figure")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ extension mitigations appendix: no C.5, no dagger, no seed caveat
p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
i = s.index("\\subsection{\\added{Origin-based mitigations on the added writers}}"); s = s[:i].rstrip("\n") + "\n"
s = sub1(s, "both executors, three seeds per domain. $^\\dagger$13 writer-seed runs (Inkling at the canonical seed); their matched typed-incremental baseline is 10.0 / 88.9, against the 15-run 10.4 / 88.3 in the first column.}}", "both executors, three seeds per domain.}}", "dagger caption")
s = sub1(s, "    Cybersecurity & 10.4 & 88.3 & 12.7 & 86.5 & 6.0$^\\dagger$ & 93.0$^\\dagger$ & 21.8 & 77.9 \\\\", "    Cybersecurity & 10.4 & 88.3 & 12.7 & 86.5 & 6.0 & 93.0 & 21.8 & 77.9 \\\\", "dagger cell")
s = sub1(s, " pools GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash with both executors at three seeds per domain, except that Inkling's rebuild in cybersecurity is at the canonical seed only, because its other two seeds repeatedly exceeded the run's time limit.}",
         " pools GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash with both executors at three seeds per domain.}", "rebuild seed caveat")
s = sub1(s, "it helps the three original writers in procurement and DeepSeek V4.1 Flash everywhere", "it helps GLM 5.2, Kimi K2.6, and Nemotron 3 Ultra in procurement and DeepSeek V4.1 Flash everywhere", "hybrid writers")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ appendix intro sentence listing the sections
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "the capacity test, the memory designs, and the origin-based mitigations on Inkling and DeepSeek V4.1 Flash", "the capacity test, and the memory designs", "appendix intro list")
p.write_text(s, encoding="utf-8", newline="\n")

# dangling references
for f in sorted(ICLR.glob("*.tex")):
    t = f.read_text(encoding="utf-8")
    for lab in ("tab:added-writers-route", "app:added-writers", "app:added-writer-mitigations", "tab:added-gate", "tab:added-event"):
        if f"\\ref{{{lab}}}" in t:
            print("DANGLING", f.name, lab)
print("integration applied")
