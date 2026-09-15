import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:200]}"
    return text.replace(old, new)


def wrap(s, label):
    """Wrap the tabular of the table carrying `label` in a linewidth resizebox."""
    i = s.index(f"\\label{{{label}}}")
    b = s.index("\\begin{tabular}", i)
    e = s.index("\\end{tabular}", b) + len("\\end{tabular}")
    return s[:b] + "\\resizebox{\\linewidth}{!}{" + s[b:e] + "}" + s[e:]


p = ICLR / "extension_results_appendix.tex"; s = p.read_text(encoding="utf-8")
s = wrap(s, "tab:closed-loop-writers")
s = wrap(s, "tab:cause")
s = sub1(s, "\\begin{tabular}{@{}p{0.24\\linewidth}p{0.66\\linewidth}@{}}", "\\begin{tabular}{@{}p{0.22\\linewidth}p{0.64\\linewidth}@{}}", "labels widths")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "\\includegraphics[width=0.92\\linewidth]{figures/EAL-Bench_memory_design.pdf}", "\\includegraphics[width=0.82\\linewidth]{figures/EAL-Bench_memory_design.pdf}", "fig2 width")
s = sub1(s, "\\includegraphics[width=0.34\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "\\includegraphics[width=0.3\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "pareto width")
s = sub1(s, "\\includegraphics[width=0.62\\linewidth]{figures/closed_loop_control.pdf}", "\\includegraphics[width=0.55\\linewidth]{figures/closed_loop_control.pdf}", "closed width")
p.write_text(s, encoding="utf-8", newline="\n")
print("fix_tables2 applied")
