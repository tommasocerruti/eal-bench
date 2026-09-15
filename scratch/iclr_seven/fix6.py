import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


old = "\\added{Two other memory designs behave the same way (Appendix~\\ref{app:rebuild}). A hybrid schema that adds free-text notes to the typed records is still updated incrementally and still launders: it lowers unauthorized submission in procurement and finance and raises it in cybersecurity. Rebuilding the typed memory from the full history every three blocks, which turns the incremental writer into a periodic one-shot writer, lowers unauthorized submission from 25.4\\% to 6.0\\% in procurement, 10.4\\% to 6.0\\% in cybersecurity, and 31.7\\% to 0.0\\% in finance with no loss of authorized use, for GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, and DeepSeek V4.1 Flash. Retrieving earlier messages at update time changes nothing.}"
new = "\\added{If this explanation is right, changing the representation should not help and giving the writer the history back should. Both hold (Appendix~\\ref{app:rebuild}). A hybrid schema that adds free-text notes to the typed records is still updated from memory alone and still launders, at 12.9\\%, 12.7\\%, and 11.7\\% unauthorized submission in procurement, cybersecurity, and finance. Rebuilding the typed memory from the full history every three blocks, which turns the incremental writer into a periodic one-shot writer, cuts unauthorized submission from 25.4\\% to 6.0\\% in procurement, 10.4\\% to 6.0\\% in cybersecurity, and 31.7\\% to 0.0\\% in finance with no loss of authorized use (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash). Retrieving a few relevant earlier messages at each update is no substitute for the full history: it changes nothing.}"
s = sub1(s, old, new, "4.1 paragraph")
s = sub1(s, "The loss follows the executor's refusal rate: 60\\% of positions in cybersecurity, 43\\% in procurement, and 34\\% in finance, where neither metric moves.}",
         "The loss follows the executor's refusal rate: 60\\% of positions in cybersecurity, 43\\% in procurement, and 34\\% in finance, where neither metric moves. An agent that records its own caution therefore loses authority it still holds.}", "4.5 conclusion")

# Figures 3 and 4 as separate figures again
i = s.index("\\begin{figure}[t]\n  \\centering\n  \\begin{minipage}[t]{0.40\\linewidth}")
j = s.index("\\end{figure}\n", i) + len("\\end{figure}\n")
block = s[i:j]
pareto_cap = block[block.index("\\caption{\\textbf{Safety"):block.index("\\label{fig:mitigation-pareto}")].rstrip()
closed_cap = block[block.index("\\caption{\\added{"):block.index("\\label{fig:closed-loop}")].rstrip()
pareto = ("\\begin{figure}[t]\n  \\centering\n  \\includegraphics[width=0.42\\linewidth]{figures/mitigation_pareto_frontier.pdf}\n"
          f"  {pareto_cap}\n  \\label{{fig:mitigation-pareto}}\n\\end{{figure}}\n")
closed = ("\\begin{figure}[t]\n  \\centering\n  \\includegraphics[width=0.78\\linewidth]{figures/closed_loop_control.pdf}\n"
          f"  {closed_cap}\n  \\label{{fig:closed-loop}}\n\\end{{figure}}\n")
s = s[:i] + pareto + s[j:]
anchor = "\\label{sec:closed-loop}\n"
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + closed)
p.write_text(s, encoding="utf-8", newline="\n")
print("fix6 applied")
