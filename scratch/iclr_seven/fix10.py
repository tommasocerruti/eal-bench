import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


s = sub1(s, "\\includegraphics[width=0.66\\linewidth]{figures/closed_loop_control.pdf}", "\\includegraphics[width=0.62\\linewidth]{figures/closed_loop_control.pdf}", "closed width")
s = sub1(s, " where neither metric moves. An agent that records its own caution therefore loses authority it still holds.}", " where neither metric moves.}", "4.5 last sentence")
p.write_text(s, encoding="utf-8", newline="\n")
print("fix10 applied")
