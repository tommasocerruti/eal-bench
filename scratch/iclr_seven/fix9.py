import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


s = sub1(s, "\\includegraphics[width=0.4\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "\\includegraphics[width=0.34\\linewidth]{figures/mitigation_pareto_frontier.pdf}", "pareto width")
s = sub1(s, "\\includegraphics[width=0.7\\linewidth]{figures/closed_loop_control.pdf}", "\\includegraphics[width=0.66\\linewidth]{figures/closed_loop_control.pdf}", "closed width")
s = sub1(s, "\\includegraphics[width=\\linewidth]{figures/EAL-Bench_memory_design.pdf}", "\\includegraphics[width=0.92\\linewidth]{figures/EAL-Bench_memory_design.pdf}", "fig2 width")
s = sub1(s, "\\added{Across writers the two metrics largely move together: GLM 5.2 achieves the highest average authorized use with the fourth-lowest unauthorized submission, DeepSeek V4.1 Flash the lowest unauthorized submission with the third-highest authorized use, and Qwen-Plus the highest unauthorized submission; Inkling is the exception, with the lowest authorized use and the second-lowest unauthorized submission.}",
         "\\added{GLM 5.2 has the highest average authorized use, DeepSeek V4.1 Flash the lowest unauthorized submission, Qwen-Plus the highest, and Inkling the lowest authorized use.}", "4.3 trim")
s = sub1(s, "the stricter instruction makes those writes fail more often (376 of 403 failures, against 212 of 216 without it).", "the stricter instruction makes those writes fail more often.", "4.4 trim")
p.write_text(s, encoding="utf-8", newline="\n")
print("fix9 applied")
