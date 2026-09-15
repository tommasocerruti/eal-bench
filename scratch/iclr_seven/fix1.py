import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
old = "finance the least safe for \\added{five of seven}"
assert s.count(old) == 1
s = s.replace(old, "finance the least safe for \\added{all but GLM 5.2 and Inkling}")
p.write_text(s, encoding="utf-8", newline="\n")

q = ICLR / "extension_appendix.tex"; a = q.read_text(encoding="utf-8")
reps = [
    ("  \\label{tab:cause}\n  \\footnotesize\n  \\setlength{\\tabcolsep}{4pt}", "  \\label{tab:cause}\n  \\scriptsize\n  \\setlength{\\tabcolsep}{3pt}"),
    ("    Closed loop, history blocks & 108", "    Closed loop, history & 108"),
    ("    Closed loop, the agent's own lines & 162", "    Closed loop, own lines & 162"),
    ("    With the instruction, procurement and finance & 67", "    Instruction, procurement and finance & 67"),
    ("    With the instruction, cybersecurity & 131", "    Instruction, cybersecurity & 131"),
    ("  \\label{tab:mandate-pooled}\n  \\footnotesize\n  \\setlength{\\tabcolsep}{4pt}", "  \\label{tab:mandate-pooled}\n  \\scriptsize\n  \\setlength{\\tabcolsep}{2.5pt}"),
]
for o, n in reps:
    assert a.count(o) == 1, o
    a = a.replace(o, n)
q.write_text(a, encoding="utf-8", newline="\n")
print("edited")
