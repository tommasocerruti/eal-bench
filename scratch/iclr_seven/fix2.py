"""Second pass on the ICLR clone: move Table 2 to the appendix, put Figures 3 and 4 side by side, update the
pressure paragraph for seven writers, split the new appendix into the paper's existing four-part structure,
and tighten the memory-design plates so seven writers fit on one page."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


def cut(text, start_marker, end_marker, label):
    i = text.index(start_marker)
    j = text.index(end_marker, i) + len(end_marker)
    assert text.count(start_marker) == 1, label
    return text[:i] + text[j:], text[i:j]


main = (ICLR / "main.tex").read_text(encoding="utf-8")

# ---- Table 2 -> appendix, replacing the commented-out copy
main, t2 = cut(main, "\\begin{table}[htbp]\n  \\caption{\\textbf{False-authority formation closely tracks", "\\end{table}\n\\FloatBarrier\n", "table 2 block")
t2 = t2.replace("\\FloatBarrier\n", "")
t2 = sub1(t2, "False-authority formation closely tracks downstream\n  unauthorized submission.", "False-authority formation tracks downstream\n  unauthorized submission.", "t2 caption")
cs = main.index("% \\begin{table}[htbp]\n%   \\caption{\\textbf{Exact pooled values underlying")
ce = main.index("% \\FloatBarrier\n", cs) + len("% \\FloatBarrier\n")
main = main[:cs] + t2 + main[ce:]
main = sub1(main, "formation tracks unauthorized submission in all three domains (Table~\\ref{tab:formation-vs-submission})",
            "formation tracks unauthorized submission in all three domains (Appendix Table~\\ref{tab:formation-vs-submission})", "t2 ref")

# ---- Figures 3 and 4 side by side
main, pareto = cut(main, "\\begin{figure}[htbp]\n  \\centering\n  \\includegraphics[width=0.5\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "\\end{figure}\n\\FloatBarrier\n", "pareto block")
_, closed = cut(main, "\\begin{figure}[!t]\n  \\centering\n  \\includegraphics[width=0.8\\linewidth]{figures/closed_loop_control.pdf}", "\\end{figure}\n", "closed-loop block")
main = main.replace(closed, "", 1)
pareto_cap = pareto[pareto.index("\\caption{"):pareto.index("\\label{fig:mitigation-pareto}")].rstrip()
closed_cap = closed[closed.index("\\caption{"):closed.index("\\label{fig:closed-loop}")].rstrip()
combined = ("\\begin{figure}[t]\n  \\centering\n"
            "  \\begin{minipage}[t]{0.36\\linewidth}\n    \\centering\n"
            "    \\includegraphics[width=\\linewidth]{figures/mitigation_pareto_frontier.pdf}\n"
            f"    {pareto_cap}\n    \\label{{fig:mitigation-pareto}}\n  \\end{{minipage}}\\hfill\n"
            "  \\begin{minipage}[t]{0.61\\linewidth}\n    \\centering\n"
            "    \\includegraphics[width=\\linewidth]{figures/closed_loop_control.pdf}\n"
            f"    {closed_cap}\n    \\label{{fig:closed-loop}}\n  \\end{{minipage}}\n\\end{{figure}}\n")
anchor = "\\subsection{Mitigations form a discrete safety--utility Pareto frontier}\n\\label{sec:mitigation-pareto-results}\n"
main = sub1(main, anchor, anchor + "\n" + combined, "combined figure placement")

# ---- Section 4.3 for seven writers
main = sub1(main, "Cybersecurity is the safest domain for \\added{every writer}, finance",
            "Cybersecurity is the safest domain for \\added{every writer (Inkling ties it with finance)}, finance", "safest")
main = sub1(main, "Across writers the two metrics move together: GLM 5.2 achieves the highest average authorized use with close to the lowest unauthorized submission (within 0.2 points of Nemotron 3 Ultra at baseline), and Qwen-Plus is weakest on both.",
            "\\added{Across writers the two metrics largely move together: GLM 5.2 achieves the highest average authorized use with the fourth-lowest unauthorized submission, DeepSeek V4.1 Flash the lowest unauthorized submission with the third-highest authorized use, and Qwen-Plus the highest unauthorized submission; Inkling is the exception, with the lowest authorized use and the second-lowest unauthorized submission.}", "move together")
main = sub1(main, "pooled authorized use falls by 27.2 points in procurement, 15.1 in cybersecurity, and 19.1 in finance",
            "pooled authorized use falls by \\added{26.4} points in procurement, \\added{16.0} in cybersecurity, and \\added{17.8} in finance", "AU drops")
main = sub1(main, "whose authorized use falls by 21 to 41 points in every domain, while DeepSeek falls by 13 to 18 points in procurement and finance",
            "whose authorized use falls by \\added{20 to 41} points in every domain, while DeepSeek falls by \\added{12 to 16} points in procurement and finance", "executor drops")
main = sub1(main, "raises it in finance from 18.0\\% to 23.9\\%", "raises it in finance from \\added{18.0\\%} to \\added{23.9\\%}", "finance rise")

# ---- mark the other changed numbers and words in red
marks = [
    ("writers create false authority for up to 51.3\\% of unauthorized requests; once false authority is present, executors act on it in 99.0\\% of trials.",
     "writers create false authority for up to \\added{51.3\\%} of unauthorized requests; once false authority is present, executors act on it in \\added{99.0\\%} of trials."),
    ("for up to 51.3\\% of unauthorized requests, and, once present, propagates to unauthorized action in 99.0\\% of matched trials. Exact-state repair removes these actions in all but 1 of 390 trials, localizing",
     "for up to \\added{51.3\\%} of unauthorized requests, and, once present, propagates to unauthorized action in \\added{99.0\\%} of matched trials. Exact-state repair \\added{removes these actions in all but 1 of 390 trials}, localizing"),
    ("We evaluate seven writers:", "We evaluate \\added{seven} writers:"),
    ("Qwen-Plus (2025-07-28) \\citep{alibabacloud2025qwenplus}, Inkling \\citep{thinkingmachines2026inkling}, and DeepSeek V4.1 Flash \\citep{deepseekai2026deepseekv41flash}.",
     "Qwen-Plus (2025-07-28) \\citep{alibabacloud2025qwenplus}\\added{, Inkling \\citep{thinkingmachines2026inkling}, and DeepSeek V4.1 Flash \\citep{deepseekai2026deepseekv41flash}}."),
    ("with a 4,096-token output limit, except that Inkling and DeepSeek V4.1 Flash reason inside the completion and run with 32,768- and 16,384-token limits.",
     "with a 4,096-token output limit\\added{, except that Inkling and DeepSeek V4.1 Flash reason inside the completion and run with 32,768- and 16,384-token limits}."),
    ("across seven writers, two executors, and three fixed writer-generation seeds", "across \\added{seven} writers, two executors, and three fixed writer-generation seeds"),
    ("Results pool three seeds, seven writers, and both executors.", "Results pool three seeds, \\added{seven} writers, and both executors."),
    ("reaching 45.9\\% unauthorized submission in finance", "reaching \\added{45.9\\%} unauthorized submission in finance"),
    ("pooled $P(F)$ is 27.1\\% in procurement, 13.6\\% in cybersecurity, and 51.3\\% in finance, against submission rates of 26.6\\%, 10.5\\%, and 45.9\\%.",
     "\\added{pooled $P(F)$ is 27.1\\% in procurement, 13.6\\% in cybersecurity, and 51.3\\% in finance, against submission rates of 26.6\\%, 10.5\\%, and 45.9\\%}."),
    ("unauthorized submission occurs in 99.0\\% of trials; after exact-state repair it occurs in 1 of 390 (Table~",
     "unauthorized submission occurs in \\added{99.0\\%} of trials; after exact-state repair it occurs in \\added{1 of 390} (Table~"),
    ("Oracle-exact memory removes unauthorized execution in all but 1 of 390 trials, isolating", "Oracle-exact memory \\added{removes unauthorized execution in all but 1 of 390 trials}, isolating"),
    ("within 0.9 percentage points in each domain, with per-replay agreement between 98.0\\% and 99.4\\%",
     "within \\added{0.9} percentage points in each domain, with per-replay agreement between \\added{98.0\\%} and \\added{99.4\\%}"),
    ("and seven writers; unauthorized-submission rates also pool both executors.", "and \\added{seven} writers; unauthorized-submission rates also pool both executors."),
    ("Results pool all three seeds,\n  seven writers, and both executors.", "Results pool all three seeds,\n  \\added{seven} writers, and both executors."),
]
for old, new in marks:
    main = sub1(main, old, new, old[:40])

# ---- appendix structure: split the new sections into the existing parts
main = sub1(main, "\\input{transfer_pressure_appendix.tex}\n", "\\input{transfer_pressure_appendix.tex}\n\n\\input{extension_results_appendix.tex}\n", "results input")
main = sub1(main, "\\input{extension_appendix.tex}\n", "\\input{extension_mitigations_appendix.tex}\n", "mitigations input")
main = sub1(main, "  results} provides the writer-side inference-scaling analysis, complete seed-level\n  results, writer--executor matrices, the capacity ablation, and the pressure\n  results.",
            "  results} provides the writer-side inference-scaling analysis, complete seed-level\n  results, writer--executor matrices, the capacity ablation, the pressure\n  results\\added{, the generated histories, the closed loop, and the failure labels}.", "guide 2")
main = sub1(main, "  and deployment scope} gives the full source-authority and event-sourcing\n  evaluations, followed by the benchmark's deployment-oriented design and\n  remaining simplifications.",
            "  and deployment scope} gives the full source-authority and event-sourcing\n  evaluations\\added{, the writer instruction, the memory designs, and the provenance mitigations on Inkling and DeepSeek V4.1 Flash}, followed by the benchmark's deployment-oriented design and\n  remaining simplifications.", "guide 3")
(ICLR / "main.tex").write_text(main, encoding="utf-8", newline="\n")

ext = (ICLR / "extension_appendix.tex").read_text(encoding="utf-8")
ext = ext.replace("\\section{", "\\subsection{")
head, body = ext.split("\n\n", 1)
k = body.index("\\subsection{Writer instruction}")
res = ("% Appendix subsections for the generated histories, the closed loop, and the failure labels. Marked \\added (red) while under review.\n\n" + body[:k].rstrip() + "\n")
mit = ("% Appendix subsections for the writer instruction, the memory designs, and the provenance mitigations on Inkling and\n% DeepSeek V4.1 Flash. Marked \\added (red) while under review.\n\n" + body[k:].rstrip() + "\n")
(ICLR / "extension_results_appendix.tex").write_text(res, encoding="utf-8", newline="\n")
(ICLR / "extension_mitigations_appendix.tex").write_text(mit, encoding="utf-8", newline="\n")
(ICLR / "extension_appendix.tex").unlink()

# ---- memory-design plates: tighter so seven writers fit one page
md = (ICLR / "memory_design_appendix.tex").read_text(encoding="utf-8")
md = sub1(md, "    \\renewcommand{\\arraystretch}{1.24}", "    \\renewcommand{\\arraystretch}{1.0}", "plate stretch")
md = sub1(md, "  \\addlinespace[0.34em]", "  \\addlinespace[0.1em]", "plate addlinespace")
md = sub1(md, "    \\par\\vspace{1.45em}", "    \\par\\vspace{0.5em}", "plate vspace")
md = sub1(md, "  {\\small\n    \\setlength{\\tabcolsep}{8.0pt}", "  {\\footnotesize\n    \\setlength{\\tabcolsep}{8.0pt}", "plate size")
(ICLR / "memory_design_appendix.tex").write_text(md, encoding="utf-8", newline="\n")
print("fix2 applied")
