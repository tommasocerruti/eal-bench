import pathlib

p = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr/extension_results_appendix.tex")
s = p.read_text(encoding="utf-8")
i = s.index("\\label{tab:judges}")
b = s.index("\\begin{tabular}", i)
e = s.index("\\end{tabular}", b) + len("\\end{tabular}")
s = s[:b] + "\\resizebox{\\ifdim\\width>\\linewidth\\linewidth\\else\\width\\fi}{!}{" + s[b:e] + "}" + s[e:]
p.write_text(s, encoding="utf-8", newline="\n")
print("judges wrapped")
