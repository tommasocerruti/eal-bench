import sys
from pathlib import Path

ICLR = Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
sys.stdout.reconfigure(encoding="utf-8")
for fn in ("main.tex", "extension_results_appendix.tex", "extension_mitigations_appendix.tex"):
    s = (ICLR / fn).read_text(encoding="utf-8")
    i = 0
    n = 0
    while True:
        i = s.find("\\added{", i)
        if i < 0:
            break
        j = i + 7
        depth = 1
        while depth and j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
            j += 1
        txt = s[i + 7:j - 1]
        n += 1
        if len(txt) > 40:
            print(f"[{fn}:{s[:i].count(chr(10)) + 1}] {txt}\n")
        i = j
    print(f"== {fn}: {n} added spans\n")
