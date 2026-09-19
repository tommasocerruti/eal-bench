"""Audit fixes: compute figure back into Section 4.5; Figure 2 caption for the two-row layout; pooled row in the writer-side
designs table and the Figure 4 caption tied to it; three sentences corrected against the tables."""
import json
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
D = json.load(open("scratch/iclr_seven/parity_pool.json", encoding="utf-8"))["designs"]["pooled"]
f1 = lambda v: f"{v:.1f}"


def rd(name):
    return (ICLR / name).read_text(encoding="utf-8")


def wr(name, t):
    (ICLR / name).write_text(t, encoding="utf-8", newline="\n")


def sub1(name, old, new):
    t = rd(name)
    assert t.count(old) == 1, (name, old[:70], t.count(old))
    wr(name, t.replace(old, new)); print("ok", name, old[:55].replace(chr(10), " "))


# 1. compute figure: appendix block -> Section 4.5, placed before its paragraph
t = rd("main.tex")
i = t.index(B + "begin{figure}[htbp]" + chr(10) + "  " + B + "centering" + chr(10) + "  " + B + "includegraphics[width=" + B + "linewidth]{figures/TTC-scale.pdf}")
j = t.index(B + "end{figure}", i) + len(B + "end{figure}") + 1
block = t[i:j]
t = t[:i] + t[j:]
block = block.replace(B + "begin{figure}[htbp]", B + "begin{figure}[t]", 1)
anchor = B + "label{sec:writer-ttc}" + chr(10)
assert t.count(anchor) == 1
t = t.replace(anchor, anchor + chr(10) + block, 1)
wr("main.tex", t); print("ok compute figure moved into Section 4.5")

# 2. Figure 2 caption (two rows)
sub1("main.tex",
     "Blue (left) bars show legitimate action rate and orange (right) bars show unauthorized action rate for the four memory conditions in each domain " + B + "revised{ and, in the last three bars, for the hybrid schema, rebuild every three blocks, and the writer instruction of Section~" + B + "ref{sec:mitigation-pareto-results}}. Results pool three seeds, " + B + "added{seven} writers, and both executors. Exact percentages are reported in Table~" + B + "ref{tab:memory-design-decomposition} " + B + "added{and Table~" + B + "ref{tab:writer-side-mitigations}}.}",
     "Blue (left) bars show legitimate action rate and orange (right) bars show unauthorized action rate. " + B + "updated{The top row compares the four memory conditions on the paper's writer route; the bottom row compares, on the runs of Appendix~" + B + "ref{app:rebuild}, typed incremental memory with the hybrid schema, rebuild every three blocks, and the writer instruction of Section~" + B + "ref{sec:mitigation-pareto-results}.} Results pool three seeds, " + B + "added{seven} writers, and both executors. Exact percentages are reported in Table~" + B + "ref{tab:memory-design-decomposition} " + B + "added{and Table~" + B + "ref{tab:writer-side-mitigations}}.}")

# 3. pooled row in the designs table, and the Figure 4 caption tied to the tables
sub1("extension_mitigations_appendix.tex",
     "    Finance & 42.8 & 99.9 & 16.2 & 97.9 & 0.7 & 98.8 & 11.8 & 99.4 " + B + B + chr(10) + "    " + B + "bottomrule",
     "    Finance & 42.8 & 99.9 & 16.2 & 97.9 & 0.7 & 98.8 & 11.8 & 99.4 " + B + B + chr(10) + "    " + B + "midrule" + chr(10)
     + "    " + B + "textbf{Pooled} & " + " & ".join(B + "textbf{" + f1(D[k][m]) + "}" for k in ("typed", "hybrid", "rebuild", "instruction") for m in ("ua", "la")) + " " + B + B + chr(10) + "    " + B + "bottomrule")
sub1("main.tex",
     "the dashed line joins the frontier of the first four, and rebuilding lies above and to the left of it.}}",
     "the dashed line joins the frontier of the first four, and rebuilding lies above and to the left of it.} " + B + "updated{Every point is a pooled table cell: the baseline and the origin checks come from Tables~" + B + "ref{tab:source-authority-aligned-domain} and~" + B + "ref{tab:event-sourcing-full-behavior}, the writer-side changes from the pooled row of Table~" + B + "ref{tab:writer-side-mitigations}, whose own typed-incremental baseline lies within 0.2 points in unauthorized and 1.6 points in legitimate action rate of the one drawn.}}")

# 4. sentences corrected against the tables
sub1("main.tex", "Cybersecurity is the safest domain for " + B + "revised{every writer}, finance the least safe for " + B + "revised{most},",
     "Cybersecurity is the safest domain for " + B + "revised{every writer}" + B + "updated{, with Inkling equally safe in finance}, finance the least safe for " + B + "revised{most},")
sub1("main.tex", "Pressure lowers legitimate action rate by 16 to 26 points in every domain and raises unauthorized action rate only in finance",
     "Pressure lowers legitimate action rate by 16 to 26 points in every domain, leaves unauthorized action rate within a point of baseline in procurement and cybersecurity, and raises it by six points in finance")
sub1("main.tex", "under it the writer's updates at the critical block fail nearly twice as often", "under it the writer's updates at the critical block fail roughly 1.7 times as often")
sub1("extension_mitigations_appendix.tex", "The instruction does not change how a cybersecurity failure looks but nearly doubles how often one happens,",
     "The instruction does not change how a cybersecurity failure looks but raises how often one happens by about two thirds,")
print("done")
