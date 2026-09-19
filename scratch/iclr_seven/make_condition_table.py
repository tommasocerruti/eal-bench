"""Replace Figure 2 with a shaded table in the style of Table 2: memory conditions and writer-side changes as rows, each domain
and the unweighted average as UA/LA column pairs. Also: Table 34 takes its typed-incremental cells from Table 4, the frontier
caption names Table 4 as the baseline, and Section 4.6 quotes the Table 4 baseline."""
import json
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
S = json.load(open("scratch/iclr_seven/seven_summary.json", encoding="utf-8"))["pooled_by_condition"]
D = json.load(open("scratch/iclr_seven/parity_pool.json", encoding="utf-8"))["designs"]
DOMS = ["procurement", "cybersecurity", "finance"]
CONDS = [("one_shot_text", "Text one-shot"), ("incremental_text", "Text incremental"), ("one_shot_typed", "Typed one-shot"), ("incremental_typed", "Typed incremental")]
DESIGNS = [("hybrid", "Hybrid incremental"), ("rebuild", "Rebuild every 3 blocks"), ("instruction", "Writer instruction")]


def rd(name):
    return (ICLR / name).read_text(encoding="utf-8")


def wr(name, t):
    (ICLR / name).write_text(t, encoding="utf-8", newline="\n")


def sub1(name, old, new, count=1):
    t = rd(name); assert t.count(old) == count, (name, old[:70], t.count(old)); wr(name, t.replace(old, new)); print("ok", name, old[:55])


rows = []  # (label, {dom: (ua, la)})
for c, lab in CONDS:
    rows.append((lab, {d: (100 * S[f"{d}|{c}"]["us_k"] / S[f"{d}|{c}"]["us_n"], 100 * S[f"{d}|{c}"]["au_k"] / S[f"{d}|{c}"]["au_n"]) for d in DOMS}))
for k, lab in DESIGNS:
    rows.append((lab, {d: (D[d][k]["ua"], D[d][k]["la"]) for d in DOMS}))
for lab, v in rows:
    v["average"] = (sum(v[d][0] for d in DOMS) / 3, sum(v[d][1] for d in DOMS) / 3)
rows = sorted(rows[:4], key=lambda r: r[1]["average"][0]) + sorted(rows[4:], key=lambda r: r[1]["average"][0])  # lowest average UA first within each block
print("row order:", [lab for lab, _ in rows])
cols = DOMS + ["average"]
best_ua = {c: min(v[c][0] for _, v in rows) for c in cols}
best_la = {c: max(v[c][1] for _, v in rows) for c in cols}


def ua_cell(v, best):
    s = f"{v:.1f}"
    if abs(v - best) < 0.05:
        s = B + "textbf{" + s + "}"
    return B + "cellcolor{usorange!" + str(max(0, round(v * 0.9))) + "}" + s


def la_cell(v, best):
    s = f"{v:.1f}"
    if abs(v - best) < 0.05:
        s = B + "textbf{" + s + "}"
    return B + "cellcolor{aublue!" + str(max(0, round((v - 50) / 50 * 35))) + "}" + s


lines = []
for i, (lab, v) in enumerate(rows):
    if i == 4:
        lines.append("    " + B + "midrule")
    cells = []
    for c in cols:
        cells.append(ua_cell(v[c][0], best_ua[c])); cells.append(la_cell(v[c][1], best_la[c]))
    lines.append("    " + lab + " & " + " & ".join(cells) + " " + B + B)
table = "\n".join([
    B + "begin{table}[t]",
    "  " + B + "caption{" + B + "textbf{Unauthorized action rate (UA, lower is better) and legitimate action rate (LA, higher is better) by memory condition and domain.} Each cell pools three seeds, seven writers, and both executors; the Average block is the unweighted mean of the three domain rates. The first four rows are the memory conditions of Section~" + B + "ref{sec:memory-design-results}, the last three the writer-side changes of Section~" + B + "ref{sec:mitigation-pareto-results}. Exact counts appear in Appendix Table~" + B + "ref{tab:memory-design-decomposition}.}",
    "  " + B + "label{tab:memory-design-across-domains}",
    "  " + B + "centering",
    "  " + B + "footnotesize",
    "  " + B + "setlength{" + B + "tabcolsep}{3pt}",
    "  " + B + "renewcommand{" + B + "arraystretch}{1.1}",
    "  " + B + "begin{tabular*}{" + B + "linewidth}{@{" + B + "extracolsep{" + B + "fill}}l*{6}{c}!{" + B + "hspace{5pt}}*{2}{c}@{}}",
    "    " + B + "toprule",
    "    & " + B + "multicolumn{2}{c}{Procurement} & " + B + "multicolumn{2}{c}{Cybersecurity} & " + B + "multicolumn{2}{c}{Finance} & " + B + "multicolumn{2}{c}{" + B + "textit{Average}} " + B + B,
    "    " + B + "cmidrule(lr){2-3}" + B + "cmidrule(lr){4-5}" + B + "cmidrule(lr){6-7}" + B + "cmidrule(lr){8-9}",
    "    Memory & UA $" + B + "downarrow$ & LA $" + B + "uparrow$ & UA $" + B + "downarrow$ & LA $" + B + "uparrow$ & UA $" + B + "downarrow$ & LA $" + B + "uparrow$ & UA $" + B + "downarrow$ & LA $" + B + "uparrow$ " + B + B,
    "    " + B + "midrule",
    *lines,
    "    " + B + "bottomrule",
    "  " + B + "end{tabular*}",
    B + "end{table}",
])

# replace the figure block
t = rd("main.tex")
i = t.index(B + "begin{figure}[t]" + chr(10) + "  " + B + "centering" + chr(10) + "  " + B + "includegraphics[width=" + B + "linewidth]{figures/EAL-Bench_memory_design.pdf}")
j = t.index(B + "end{figure}", i) + len(B + "end{figure}")
t = t[:i] + table + t[j:]
assert "sec:memory-design-results" in t
n = t.count("Figure~" + B + "ref{fig:memory-design-across-domains}")
t = t.replace("Figure~" + B + "ref{fig:memory-design-across-domains}", "Table~" + B + "ref{tab:memory-design-across-domains}")
t = t.replace("The last three bars of Table~", "The last three rows of Table~")
wr("main.tex", t); print("figure replaced by table; refs changed:", n)
for name in ("extension_mitigations_appendix.tex", "extension_results_appendix.tex", "multiseed_appendix.tex", "memory_design_appendix.tex"):
    tt = rd(name)
    if "fig:memory-design-across-domains" in tt:
        wr(name, tt.replace("Figure~" + B + "ref{fig:memory-design-across-domains}", "Table~" + B + "ref{tab:memory-design-across-domains}")); print("refs changed in", name)

import sys
if "--table-only" in sys.argv:
    print("table only"); sys.exit(0)
# Table 34: typed-incremental cells from Table 4
t4 = {d: (100 * S[f"{d}|incremental_typed"]["us_k"] / S[f"{d}|incremental_typed"]["us_n"], 100 * S[f"{d}|incremental_typed"]["au_k"] / S[f"{d}|incremental_typed"]["au_n"]) for d in DOMS}
pk = sum(S[f"{d}|incremental_typed"]["us_k"] for d in DOMS); pn = sum(S[f"{d}|incremental_typed"]["us_n"] for d in DOMS)
ak = sum(S[f"{d}|incremental_typed"]["au_k"] for d in DOMS); an = sum(S[f"{d}|incremental_typed"]["au_n"] for d in DOMS)
t4["pooled"] = (100 * pk / pn, 100 * ak / an)
f1 = lambda v: f"{v:.1f}"
for d, lab in (("procurement", "Procurement"), ("cybersecurity", "Cybersecurity"), ("finance", "Finance")):
    old = f"    {lab} & {f1(D[d]['typed']['ua'])} & {f1(D[d]['typed']['la'])} & "
    new = f"    {lab} & {f1(t4[d][0])} & {f1(t4[d][1])} & "
    sub1("extension_mitigations_appendix.tex", old, new)
sub1("extension_mitigations_appendix.tex", B + "textbf{Pooled} & " + B + "textbf{" + f1(D["pooled"]["typed"]["ua"]) + "} & " + B + "textbf{" + f1(D["pooled"]["typed"]["la"]) + "} & ",
     B + "textbf{Pooled} & " + B + "textbf{" + f1(t4["pooled"][0]) + "} & " + B + "textbf{" + f1(t4["pooled"][1]) + "} & ")
print("Table 4 typed incremental:", {k: (f1(v[0]), f1(v[1])) for k, v in t4.items()})

# Section 4.6 baseline numbers and the frontier caption
sub1("main.tex", "from 25.7" + B + "% to 8.5" + B + "% and from 42.8" + B + "% to 11.8" + B + "%", "from " + f1(t4["procurement"][0]) + B + "% to 8.5" + B + "% and from " + f1(t4["finance"][0]) + B + "% to 11.8" + B + "%")
sub1("main.tex",
     "Every point is a pooled table cell: the baseline and the origin checks come from Tables~" + B + "ref{tab:source-authority-aligned-domain} and~" + B + "ref{tab:event-sourcing-full-behavior}, the writer-side changes from the pooled row of Table~" + B + "ref{tab:writer-side-mitigations}, whose own typed-incremental baseline lies within 0.2 points in unauthorized and 1.6 points in legitimate action rate of the one drawn. The hollow circle is one-shot typed memory from Table~" + B + "ref{tab:memory-design-decomposition}, drawn as the reference that rebuilding approaches.",
     "Every point is a pooled table cell: the baseline is typed incremental memory from Table~" + B + "ref{tab:memory-design-decomposition}, the origin checks come from Tables~" + B + "ref{tab:source-authority-aligned-domain} and~" + B + "ref{tab:event-sourcing-full-behavior}, and the writer-side changes from the pooled row of Table~" + B + "ref{tab:writer-side-mitigations}. The hollow circle is one-shot typed memory from the same table, the reference that rebuilding approaches.")
json.dump({"typed_incremental_pooled": t4["pooled"]}, open("scratch/iclr_seven/table4_pooled.json", "w"), indent=1)
print("done")
