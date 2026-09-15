import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


start = "\\begin{table}[t]\n\\caption{\\textbf{Unauthorized action rate under erroneous and exact memory.}"
i = s.index(start); j = s.index("\\end{table}\n", i) + len("\\end{table}\n")
block = s[i:j].replace("\\begin{table}[t]", "\\begin{table}[htbp]", 1)
s = s[:i] + s[j:]
s = sub1(s, "after exact-state repair it occurs in \\added{1 of 390} (Table~\\ref{tab:natural-repair})", "after exact-state repair it occurs in \\added{1 of 390} (\\added{Appendix} Table~\\ref{tab:natural-repair})", "repair ref")
# place it right after the formation table in the appendix
k = s.index("\\label{tab:formation-vs-submission}")
k = s.index("\\end{table}\n", k) + len("\\end{table}\n")
s = s[:k] + "\n" + block + s[k:]
p.write_text(s, encoding="utf-8", newline="\n")
print("fix8 applied")
