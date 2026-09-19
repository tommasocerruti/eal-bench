"""Style pass after the rename: no sentence opens with a number, a four-line estimation paragraph,
larger closed-loop and frontier figures, and a paragraph-fill setting against single-word last lines."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:200]}"
    return text.replace(old, new)


p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
# hanging single words at paragraph ends: the last line must be at least a third full
s = sub1(s, "\\newcommand{\\revised}[1]{{\\color{green!50!black}#1}}  % rewritten in the second pass; remove the color once accepted",
         "\\newcommand{\\revised}[1]{{\\color{green!50!black}#1}}  % rewritten in the second pass; remove the color once accepted\n"
         "\\setlength{\\parfillskip}{0pt plus 0.67\\textwidth}  % no single-word last lines\n\\widowpenalty=10000 \\clubpenalty=10000", "parfillskip")
# abstract: no sentence opens with a number
s = sub1(s, "Two safeguards, requiring stored permissions to be backed by valid source events, and tracking permission changes through bounded event sourcing, substantially reduce laundering, but both also reject more legitimate actions, exposing a safety--utility tradeoff.",
         "\\revised{Requiring stored permissions to be backed by valid source events, or tracking permission changes through bounded event sourcing, substantially reduces laundering, but both safeguards also reject more legitimate actions, exposing a safety--utility tradeoff.}", "abstract two safeguards")
# related work
s = sub1(s, "Two benchmarks are closest, and Table~\\ref{tab:related-work-comparison} summarizes the comparison.",
         "\\revised{The closest benchmarks are \\textsc{AuthMem-Bench} and \\textsc{PPMF}, and Table~\\ref{tab:related-work-comparison} summarizes the comparison.}", "related two")
# methods
s = sub1(s, "\\revised{Three variants of the typed incremental writer separate the update strategy from the representation and from what the writer can see (Appendix~\\ref{app:rebuild}).",
         "\\revised{We test three variants of the typed incremental writer that separate the update strategy from the representation and from what the writer can see (Appendix~\\ref{app:rebuild}).", "variants")
s = sub1(s, "\\revised{Three protocols locate the writer's error. \\emph{Generated histories}",
         "\\revised{We use three protocols to locate the writer's error. \\emph{Generated histories}", "protocols")
# estimation paragraph: four lines
start = s.index("\\paragraph{Estimation and uncertainty.}")
end = s.index("\\paragraph{Reproducibility.}")
s = s[:start] + "\\paragraph{Estimation and uncertainty.}\n\n\\revised{We evaluate all four memory conditions across seven writers, two executors, and three writer-generation seeds per domain, pooling the equally sized seed counts and reporting each seed separately in Appendix~\\ref{app:three-seed-matrix}. Replays that share a memory are correlated, so every interval is a 95\\% paired bootstrap interval over matched writer--case trajectories, or over chains for the closed loop, pointwise and unadjusted for multiplicity \\citep{field2007bootstrap}.}\n\n" + s[end:]
# results
s = sub1(s, "\\revised{Two further comparisons confirm that the update strategy drives the failure (Figure~\\ref{fig:memory-design-across-domains}, last three bars; Appendix~\\ref{app:rebuild}).",
         "\\revised{The last three bars of Figure~\\ref{fig:memory-design-across-domains} confirm that the update strategy drives the failure (Appendix~\\ref{app:rebuild}).", "4.1 opener")
# limitations
s = sub1(s, "\\added{Three} analyses rest on a single fixed seed rather than the three-seed evaluation: the per-writer comparison",
         "\\revised{A single fixed seed, rather than the three-seed evaluation, underlies three analyses}: the per-writer comparison", "limitations three")
# figure sizes
s = sub1(s, "\\includegraphics[width=0.55\\linewidth]{figures/closed_loop_control.pdf}", "\\includegraphics[width=\\linewidth]{figures/closed_loop_control.pdf}", "loop width")
s = sub1(s, "\\includegraphics[width=0.3\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "\\includegraphics[width=0.5\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "pareto width")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "extension_results_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "form them for 15.4\\% once two restatements follow the change (Table~\\ref{tab:restatements}). Four restatements are not measurably different from two (10.8\\% against 15.4\\%, intervals overlapping); the data neither separate the two levels nor show them equal.",
         "form them for 15.4\\% once two restatements follow the change (Table~\\ref{tab:restatements}), and four restatements are not measurably different from two (10.8\\% against 15.4\\%, intervals overlapping), so the data neither separate the two levels nor show them equal.", "four restatements")
s = sub1(s, "\\added{Two further differences appear on the same corpus and are observed, not matched.", "\\added{The same corpus shows two further differences, which are observed rather than matched.", "two differences")
s = sub1(s, "Two arms are then forked from the same frozen memories and run in lockstep.", "From the same frozen memories, two arms are then forked and run in lockstep.", "two arms")
s = sub1(s, "\\added{Two effects appear only in the action arm. First,", "\\added{The action arm alone shows two effects. First,", "two effects")
s = sub1(s, "One judge, Nemotron 3 Ultra, is also a writer and labels failures of its own updates;", "The judge Nemotron 3 Ultra is also a writer and labels failures of its own updates;", "one judge")
s = sub1(s, "\\added{Three errors account for nearly all 2,250 judged failures, and they separate by domain and setting rather than by writer (Table~\\ref{tab:cause}).",
         "\\added{Nearly all 2,250 judged failures fall under three errors, which separate by domain and setting rather than by writer (Table~\\ref{tab:cause}).", "three errors")
s = sub1(s, "\\added{Three failures from the runs show the three errors.", "\\added{The three errors can each be illustrated by a failure from the runs.", "three failures")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "\\added{Three designs are compared with the paper's typed incremental memory on the same runs, writers, executors, and requests, so that only the design varies.",
         "\\added{We compare three designs with the paper's typed incremental memory on the same runs, writers, executors, and requests, so that only the design varies.", "three designs")
p.write_text(s, encoding="utf-8", newline="\n")
print("style applied")
