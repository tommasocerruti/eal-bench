"""Executor-behavior gate table over seven writers: original and gated rows pooled with the added writers' primary-seed
trials (gate_behavior_added.json); the oracle-exact row moves to a cross-reference of the repair table."""
import json
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
c = json.load(open("scratch/iclr_seven/gate_behavior_added.json", encoding="utf-8"))
FIVE = {"ORIGINAL": (2535, 2640, 331, 2640), "GATED": (1983, 2640, 85, 2640)}


def cell(k, n):
    return f"{k}/{n} ({100 * k / n:.1f}" + B + "%)"


rows = {}
for v in ("ORIGINAL", "GATED"):
    lk, ln, uk, un = FIVE[v]
    rows[v] = (lk + c[v + "|la_k"], ln + c[v + "|la_n"], uk + c[v + "|ua_k"], un + c[v + "|ua_n"])
p = ICLR / "source_authority_appendix.tex"
t = p.read_text(encoding="utf-8")
old = ("    Original typed & 2535/2640 (96.0" + B + "%) & 331/2640 (12.5" + B + "%) " + B + B + "\n"
       "    Gold source-authority gated & 1983/2640 (75.1" + B + "%) & 85/2640 (3.2" + B + "%) " + B + B + "\n"
       "    Oracle exact & 264/264 (100.0" + B + "%) & 0/264 (0.0" + B + "%) " + B + B + "\n")
o, g = rows["ORIGINAL"], rows["GATED"]
new = ("    Original typed & " + cell(o[0], o[1]) + " & " + cell(o[2], o[3]) + " " + B + B + "\n"
       "    Gold source-authority gated & " + cell(g[0], g[1]) + " & " + cell(g[2], g[3]) + " " + B + B + "\n")
assert t.count(old) == 1, t.count(old)
t = t.replace(old, new)
oldcap = "Original and gated rows retain the full frozen typed writer/strategy matrix; oracle-exact rows use unique controls."
assert t.count(oldcap) == 1
t = t.replace(oldcap, "Both rows pool the primary-seed typed matrix, one-shot and incremental, over all writers and both executors; the oracle-exact controls are in Table~" + B + "ref{tab:natural-repair}.")
p.write_text(t, encoding="utf-8", newline="\n")
print("table 29:", rows)
