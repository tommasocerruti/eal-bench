"""Install the seven-bar Figure 2 and the four-point Figure 3, with their red caption and text edits."""
import pathlib
import shutil
import sys

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
SRC = pathlib.Path(sys.argv[1])  # scratchpad holding fig2_final.pdf and fig3_final.pdf


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:200]}"
    return text.replace(old, new)


shutil.copy(SRC / "fig2_final.pdf", ICLR / "figures/EAL-Bench_memory_design.pdf")
shutil.copy(SRC / "fig3_final.pdf", ICLR / "figures/mitigation_pareto_frontier.pdf")

p = ICLR / "main.tex"
s = p.read_text(encoding="utf-8")

# Figure 2: full width, caption names the three added bars, section text points at them.
s = sub1(s, "\\includegraphics[width=0.82\\linewidth]{figures/EAL-Bench_memory_design.pdf}",
         "\\includegraphics[width=\\linewidth]{figures/EAL-Bench_memory_design.pdf}", "fig2 width")
s = sub1(s, "orange (right) bars show unauthorized submission for the four memory conditions in each domain. Results pool three seeds, \\added{seven} writers, and both executors. Exact percentages are reported in Table~\\ref{tab:memory-design-decomposition}.}",
         "orange (right) bars show unauthorized submission for the four memory conditions in each domain\\added{ and, in the last three bars, for three changes to the typed incremental writer: a hybrid schema, rebuilding from the history every three blocks, and the writer instruction of Section~\\ref{sec:mitigation-pareto-results}}. Results pool three seeds, \\added{seven} writers, and both executors. Exact percentages are reported in Table~\\ref{tab:memory-design-decomposition}\\added{ and Table~\\ref{tab:writer-side-mitigations}}.}", "fig2 caption")
s = sub1(s, "Both hold (Appendix~\\ref{app:rebuild}; GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash, both executors, three seeds except Inkling's cybersecurity rebuild).",
         "Both hold (Figure~\\ref{fig:memory-design-across-domains}, last three bars; Appendix~\\ref{app:rebuild}; GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash, both executors, three seeds except Inkling's cybersecurity rebuild).", "4.1 pointer")

# Figure 3: the writer instruction as a fourth point.
s = sub1(s, "The circle is the typed-incremental baseline, and the squares are the two mitigations. \\added{GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Grok 4.3, and Qwen-Plus, three seeds, both executors.}}",
         "The circle is the typed-incremental baseline, and the squares are the two mitigations. \\added{GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Grok 4.3, and Qwen-Plus, three seeds, both executors. The diamond is the writer instruction of Section~\\ref{sec:mitigation-pareto-results}, pooled over its three domains (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash, three seeds, both executors).}}", "fig3 caption")
s = sub1(s, "\\added{Among these three,} no configuration dominates another on the pooled estimates, so the three points form a discrete empirical Pareto frontier",
         "\\added{Among these four,} no configuration dominates another on the pooled estimates, so the \\added{four} points form a discrete empirical Pareto frontier", "4.4 four points")
s = sub1(s, "The instruction forbids what the procurement and finance failures are, a restatement applied, and cannot reach the cybersecurity failure, a write of the legitimate change that is never stored.",
         "The instruction forbids what the procurement and finance failures are, a restatement applied, and cannot reach the cybersecurity failure, a write of the legitimate change that is never stored. Pooled over the three domains it sits at 12.6\\% unauthorized submission and 88.6\\% authorized use, the one point on the frontier of Figure~\\ref{fig:mitigation-pareto} within five points of the baseline's authorized use.", "4.4 pooled sentence")
p.write_text(s, encoding="utf-8", newline="\n")
print("fig23 applied")
