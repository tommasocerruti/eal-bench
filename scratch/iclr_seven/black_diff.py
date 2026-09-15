"""Compare the black (non-red) text of two main.tex versions."""
import difflib
import sys

sys.stdout.reconfigure(encoding="utf-8")


def strip_added(s):
    out = []
    i = 0
    while True:
        j = s.find("\\added{", i)
        if j < 0:
            out.append(s[i:]); break
        out.append(s[i:j]); k = j + 7; depth = 1
        while depth and k < len(s):
            depth += (s[k] == "{") - (s[k] == "}"); k += 1
        i = k
    return "".join(out)


a = strip_added(open(sys.argv[1], encoding="utf-8").read()).splitlines()
b = strip_added(open(sys.argv[2], encoding="utf-8").read()).splitlines()
for line in difflib.unified_diff(a, b, lineterm="", n=0):
    if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
        t = line[1:].strip()
        if t:
            print(line[0], t[:220])
