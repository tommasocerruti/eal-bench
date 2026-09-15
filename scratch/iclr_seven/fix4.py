import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


s = sub1(s, "We run \\textsc{EAL-Bench} with five memory writers and two calibrated executors", "We run \\textsc{EAL-Bench} with \\added{seven} memory writers and two calibrated executors", "intro seven")
s = sub1(s, "while replacing the erroneous memory with the exact authorization state eliminates the failure.", "while replacing the erroneous memory with the exact authorization state \\added{all but} eliminates the failure.", "conclusion eliminates")
s = sub1(s, "\\added{Two further interventions change the writer rather than the memory: rebuilding", "\\added{Two further interventions change how the writer writes rather than what it keeps: rebuilding", "3.2 wording")
p.write_text(s, encoding="utf-8", newline="\n")
print("fix4 applied")
