"""Mark the remaining black-text changes in red: captions, headings, the mechanism numbers, the moved-table caption."""
import pathlib
import re

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "Across three seeds, formation tracks unauthorized submission in all three domains (Appendix Table~\\ref{tab:formation-vs-submission})",
         "Across three seeds, formation \\added{tracks} unauthorized submission in all three domains (\\added{Appendix} Table~\\ref{tab:formation-vs-submission})", "4.2 tracks")
s = sub1(s, "\\subsection{Writing the agent's own actions back into the history lowers authorized use}",
         "\\subsection{\\added{Writing the agent's own actions back into the history lowers authorized use}}", "4.5 heading")
s = sub1(s, "\\caption{\\textbf{False-authority formation tracks downstream\n  unauthorized submission.}",
         "\\caption{\\textbf{False-authority formation \\added{tracks} downstream\n  unauthorized submission.}", "t2 caption tracks")
old = ("The three-seed typed-incremental analysis covers 756 final writer--case trajectories and 7,770 saved update positions. Free-text memory is excluded from deterministic semantic scoring. Among typed states, 4,614/7,770 (59.4\\%) contain a semantic error and 581/7,770 (7.5\\%) contain an authority-gaining error; 543/756 (71.8\\%) final states are not exact, and request-level false authority is 733/2,772 (26.4\\%).")
new = ("The three-seed typed-incremental analysis covers \\added{756} final writer--case trajectories and \\added{7,770} saved update positions. Free-text memory is excluded from deterministic semantic scoring. Among typed states, \\added{4,614/7,770 (59.4\\%)} contain a semantic error and \\added{581/7,770 (7.5\\%)} contain an authority-gaining error; \\added{543/756 (71.8\\%)} final states are not exact, and request-level false authority is \\added{733/2,772 (26.4\\%)}.")
s = sub1(s, old, new, "mechanism numbers")
p.write_text(s, encoding="utf-8", newline="\n")

q = ICLR / "multiseed_appendix.tex"; t = q.read_text(encoding="utf-8")
t = sub1(t, "Values pool\n  seven writers and both executors within a seed.", "Values pool\n  \\added{seven} writers and both executors within a seed.", "ms cap 1")
t = sub1(t, "Values pool all seven\n  writers and all four memory conditions.", "Values pool all \\added{seven}\n  writers and all four memory conditions.", "ms cap 3")
q.write_text(t, encoding="utf-8", newline="\n")

q = ICLR / "memory_design_appendix.tex"; t = q.read_text(encoding="utf-8")
t = sub1(t, "One fixed seed's $2\\times2$ disaggregation for all seven writers.", "One fixed seed's $2\\times2$ disaggregation for all \\added{seven} writers.", "md cap")
q.write_text(t, encoding="utf-8", newline="\n")

q = ICLR / "transfer_pressure_appendix.tex"; t = q.read_text(encoding="utf-8")
t = sub1(t, "averages pool the underlying counts across all seven writers.", "averages pool the underlying counts across all \\added{seven} writers.", "tp cap")
q.write_text(t, encoding="utf-8", newline="\n")

for fn in ("extension_results_appendix.tex", "extension_mitigations_appendix.tex"):
    q = ICLR / fn; t = q.read_text(encoding="utf-8")
    t, n = re.subn(r"\\subsection\{([^{}]+)\}", r"\\subsection{\\added{\1}}", t)
    assert n == 3, (fn, n)
    q.write_text(t, encoding="utf-8", newline="\n")
print("fix5 applied")
