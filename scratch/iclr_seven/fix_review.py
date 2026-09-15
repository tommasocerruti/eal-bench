"""Resolve the brief's discrepancies (numbers and captions only), fix table widths, apply the section-5 page cuts."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:200]}"
    return text.replace(old, new)


# ------------------------------------------------------------------ main.tex
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
# 3.1 cybersecurity rebuild sits next to its matched baseline
s = sub1(s, "cuts unauthorized submission from 25.4\\% to 6.0\\%, from 10.4\\% to 6.0\\%, and from 31.7\\% to 0.0\\% with no loss of authorized use.",
         "cuts unauthorized submission from 25.4\\% to 6.0\\%, from 10.0\\% to 6.0\\%, and from 31.7\\% to 0.0\\% with no loss of authorized use.", "4.1 rebuild baseline")
# black-text byte identity: keep the sentence's period outside the red span
s = sub1(s, "and the gap is requests the executor escalated or declined despite the memory.} Most of the behavioral",
         "and the gap is requests the executor escalated or declined despite the memory}. Most of the behavioral", "4.2 period")
# cut 1: intro paragraph to first and last sentence
s = sub1(s, "\\added{Measuring the failure is not the same as knowing what causes it, and the two provenance defenses we test show why the distinction matters: both cut laundering, both cost legitimate use, and neither says which message the writer misread. We therefore also ask what the writer reacts to. Generated histories that vary one feature at a time locate the trigger in later messages that restate a superseded permission. Attributing each failure to the memory update that introduced it shows that the writer's error differs by domain. A closed loop in which the agent's own log is written back into its history shows that the agent supplies such messages itself. Which error a deployment faces decides whether a given defense helps, costs utility, or backfires.}",
         "\\added{Measuring the failure is not the same as knowing what causes it, and the two provenance defenses we test show why the distinction matters: both cut laundering, both cost legitimate use, and neither says which message the writer misread. Which error a deployment faces decides whether a given defense helps, costs utility, or backfires.}", "cut 1")
# cut 2: pressure paragraph to the appendix
i = s.index("Pressure leaves unauthorized submission essentially unchanged in procurement and cybersecurity")
j = s.index("\n", i)
pressure_par = s[i:j]
assert pressure_par.endswith("(Appendix~\\ref{app:full-transfer}).")
s = s[:i] + "\\added{Pressure lowers authorized use by 16 to 26 points in every domain and raises unauthorized submission only in finance (Appendix~\\ref{app:full-transfer}).}" + s[j:]
tp = ICLR / "transfer_pressure_appendix.tex"; t = tp.read_text(encoding="utf-8")
anchor = "Appendix~\\ref{app:memory-design-detail} gives the corresponding breakdown by memory representation and update strategy.\n"
t = sub1(t, anchor, anchor + "\n" + pressure_par + "\n", "pressure paragraph into appendix")
tp.write_text(t, encoding="utf-8", newline="\n")
# cut 3
s = sub1(s, " The writer records the restatement in place of the change that preceded it. Attributing every failure", " Attributing every failure", "cut 3a")
s = sub1(s, " Additional writer-side compute avoids some errors before they are stored but repairs none afterwards (Appendix~\\ref{app:writer-ttc-details}).}", "}", "cut 3b")
# cut 4
s = sub1(s, " An agent that logs its own actions into the history its memory writer reads therefore loses legitimate authority round over round, and Section~\\ref{sec:mitigation-pareto-results}'s instruction stops the minted records without recovering that loss.}", "}", "cut 4")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ results appendix
p = ICLR / "extension_results_appendix.tex"; s = p.read_text(encoding="utf-8")
# 3.4 one interval
s = sub1(s, "GLM 5.2, Kimi K2.6, Nemotron 3 Ultra & 216 & $+2.9$ ($-0.1$, $+6.0$) & $-23.9$ ($-30.5$, $-17.5$) & 93 / 1 \\\\",
         "GLM 5.2, Kimi K2.6, Nemotron 3 Ultra & 216 & $+2.9$ ($-0.1$, $+5.9$) & $-23.9$ ($-30.2$, $-17.4$) & 93 / 1 \\\\", "3.4 table")
s = sub1(s, "($+2.9$, 95\\% CI $-0.0$ to $+5.8$, at round 3)", "($+2.9$, 95\\% CI $-0.1$ to $+5.9$, at round 3)", "3.4 text")
# 3.3 the 127 and the 117 are the same records
s = sub1(s, "127 records cite nothing but written-back lines, against 4 in the control, and Appendix~\\ref{app:diagnosis} labels all but a few of them the same way,",
         "127 records cite nothing but written-back lines, against 4 in the control; Appendix~\\ref{app:diagnosis} counts the same 131 records as 117 new records and 14 existing records whose cited sources were replaced by the agent's lines, and labels all but a few of them the same way,", "3.3")
# 3.2 caption: pooling and double counting
s = sub1(s, "Every judged failure in this paper's extension runs: distinct memory updates, the failures (requests or records) they caused, and the judges' majority label. The instruction rows include open- and closed-loop runs with the writer instruction.}}",
         "Every judged failure in this paper's extension runs: distinct memory updates, the failures (requests or records) they caused, and the judges' majority label. The open-loop rows pool the memory-design grid, the added writers' route, the instruction baselines at the other two seeds, and, in procurement, the generated histories with and without the instruction; the instruction rows pool the open-loop instruction runs at three seeds and the closed loop with the instruction. An update whose failures fall in more than one row is counted in each row, so the rows sum to 874 updates against 861 distinct.}}", "3.2 caption")
# table widths
s = sub1(s, "  \\label{tab:restatements}\n  \\small\n  \\setlength{\\tabcolsep}{4pt}\n  \\begin{tabular}{@{}llccccc@{}}", "  \\label{tab:restatements}\n  \\small\n  \\setlength{\\tabcolsep}{4pt}\n  \\resizebox{\\linewidth}{!}{\\begin{tabular}{@{}llccccc@{}}", "restatements open")
i = s.index("\\label{tab:restatements}"); j = s.index("  \\end{tabular}\n\\end{table}", i)
s = s[:j] + "  \\end{tabular}}\n\\end{table}" + s[j + len("  \\end{tabular}\n\\end{table}"):]
s = sub1(s, "  \\label{tab:closed-loop-domains}\n  \\scriptsize\n  \\setlength{\\tabcolsep}{3pt}\n  \\begin{tabular}{@{}lrccccccc@{}}", "  \\label{tab:closed-loop-domains}\n  \\scriptsize\n  \\setlength{\\tabcolsep}{3pt}\n  \\resizebox{\\linewidth}{!}{\\begin{tabular}{@{}lrccccccc@{}}", "cl domains open")
i = s.index("\\label{tab:closed-loop-domains}"); j = s.index("  \\end{tabular}\n\\end{table}", i)
s = s[:j] + "  \\end{tabular}}\n\\end{table}" + s[j + len("  \\end{tabular}\n\\end{table}"):]
s = sub1(s, "\\begin{tabular}{@{}p{0.27\\linewidth}p{0.68\\linewidth}@{}}", "\\begin{tabular}{@{}p{0.24\\linewidth}p{0.66\\linewidth}@{}}", "labels widths")
s = sub1(s, "  \\label{tab:cause}\n  \\scriptsize\n  \\setlength{\\tabcolsep}{3pt}", "  \\label{tab:cause}\n  \\scriptsize\n  \\setlength{\\tabcolsep}{2pt}", "cause colsep")
p.write_text(s, encoding="utf-8", newline="\n")

# ------------------------------------------------------------------ mitigations appendix
p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "both executors, three seeds per domain except Inkling's cybersecurity rebuild (canonical seed).}}",
         "both executors, three seeds per domain except Inkling's cybersecurity rebuild (canonical seed). The rebuild column's matched typed-incremental baseline, from the same writers, seeds, and executors, is 25.4 / 90.6 in procurement, 10.0 / 88.9 in cybersecurity, and 31.7 / 99.9 in finance.}}", "3.1 caption")
s = sub1(s, "  \\label{tab:capacity}\n  \\scriptsize\n  \\setlength{\\tabcolsep}{3pt}\n  \\begin{tabular}{@{}llccccc@{}}", "  \\label{tab:capacity}\n  \\scriptsize\n  \\setlength{\\tabcolsep}{3pt}\n  \\resizebox{\\linewidth}{!}{\\begin{tabular}{@{}llccccc@{}}", "capacity open")
i = s.index("\\label{tab:capacity}"); j = s.index("  \\end{tabular}\n\\end{table}", i)
s = s[:j] + "  \\end{tabular}}\n\\end{table}" + s[j + len("  \\end{tabular}\n\\end{table}"):]
p.write_text(s, encoding="utf-8", newline="\n")
print("fix_review applied")
