"""Cross-check every data figure against the table it is meant to match, reading the figure inputs and the compiled tex.
Prints MISMATCH lines; exit 1 if any."""
import csv
import json
import pathlib
import re
import sys

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
tex = {p.name: p.read_text(encoding="utf-8") for p in ICLR.glob("*.tex")}
bad = []


def table_block(text, label):
    i = text.index(B + "label{" + label + "}")
    s = text.rfind(B + "begin{table", 0, i); e = text.index(B + "end{table", i)
    return text[s:e]


def close(a, b, tol=0.051):
    return abs(float(a) - float(b)) <= tol


def check(name, fig, tab):
    if not close(fig, tab):
        bad.append(f"MISMATCH {name}: figure {fig} vs table {tab}")


# ---- Figure 2 top row vs Table 4 (shortstack A/U)
S = json.load(open("scratch/iclr_seven/seven_summary.json", encoding="utf-8"))["pooled_by_condition"]
t4 = table_block(tex["main.tex"], "tab:memory-design-decomposition")
cells = re.findall(r"A: ([0-9.]+)" + B + B + B + B + r"U: ([0-9.]+)", t4)
conds = ["one_shot_text", "incremental_text", "one_shot_typed", "incremental_typed"]
k = 0
for dom in ("procurement", "cybersecurity", "finance"):
    for c in conds:
        s = S[f"{dom}|{c}"]; a, u = cells[k]; k += 1
        check(f"Fig2 top {dom} {c} LA", 100 * s["au_k"] / s["au_n"], a); check(f"Fig2 top {dom} {c} UA", 100 * s["us_k"] / s["us_n"], u)
print("Fig2 top vs Table 4: checked", k, "cells")

# ---- Figure 2 bottom row and Figure 5 writer-side points vs Table 34
D = json.load(open("scratch/iclr_seven/parity_pool.json", encoding="utf-8"))["designs"]
t34 = table_block(tex["extension_mitigations_appendix.tex"], "tab:writer-side-mitigations")
rows = {m.group(1): [float(x) for x in m.group(2).split("&")] for m in re.finditer(r"\n\s*(Procurement|Cybersecurity|Finance) & ([0-9. &]+) " + B + B + B + B, t34)}
pooled = re.search(B + B + r"textbf\{Pooled\}((?: & " + B + B + r"textbf\{[0-9.]+\}){8})", t34)
rows["pooled"] = [float(x) for x in re.findall(r"\{([0-9.]+)\}", pooled.group(1))]
n = 0
for dom, key in (("procurement", "Procurement"), ("cybersecurity", "Cybersecurity"), ("finance", "Finance"), ("pooled", "pooled")):
    vals = rows[key]
    for i, cond in enumerate(("typed", "hybrid", "rebuild", "instruction")):
        check(f"Table34 {dom} {cond} UA", D[dom][cond]["ua"], vals[2 * i]); check(f"Table34 {dom} {cond} LA", D[dom][cond]["la"], vals[2 * i + 1]); n += 2
print("Fig2 bottom / Fig5 writer-side vs Table 34: checked", n, "cells")

# ---- Figure 5 origin checks vs Tables 27 and 30 pooled rows
P = json.load(open("scratch/iclr_seven/fig4_points.json", encoding="utf-8"))
t27 = table_block(tex["source_authority_appendix.tex"], "tab:source-authority-aligned-domain")
m = re.search(B + B + r"textbf\{Pooled\} & " + B + B + r"textbf\{([0-9.]+) \$" + B + B + r"rightarrow\$ ([0-9.]+)\} & " + B + B + r"textbf\{([0-9.]+) \$" + B + B + r"rightarrow\$ ([0-9.]+)\}", t27)
assert m, "gate pooled row"
check("Fig5 gate UA", P["gate"][0], m.group(4)); check("Fig5 gate LA", P["gate"][1], m.group(2))
t30 = table_block(tex["event_sourcing_appendix.tex"], "tab:event-sourcing-full-behavior")
m = re.search(B + B + r"textbf\{Pooled\} & " + B + B + r"textbf\{\d+/\d+ \(([0-9.]+)" + B + B + r"%\)\} & " + B + B + r"textbf\{\d+/\d+ \(([0-9.]+)" + B + B + r"%\)\} & " + B + B + r"textbf\{\d+/\d+ \(([0-9.]+)" + B + B + r"%\)\} & " + B + B + r"textbf\{\d+/\d+ \(([0-9.]+)" + B + B + r"%\)\}", t30)
assert m, "event pooled row"
check("Fig5 baseline UA", P["baseline"][0], m.group(1)); check("Fig5 event UA", P["event"][0], m.group(2)); check("Fig5 baseline LA", P["baseline"][1], m.group(3)); check("Fig5 event LA", P["event"][1], m.group(4))
print("Fig5 origin checks vs Tables 27/30: checked 6 cells")

# ---- Figure 3 (closed loop) vs Table 22
cl = list(csv.DictReader(open("results/figures/closed_loop_control.csv", encoding="utf-8")))
t22 = table_block(tex["extension_results_appendix.tex"], "tab:closed-loop-domains")
for dom, key in (("procurement", "Procurement"), ("cybersecurity", "Cybersecurity"), ("finance", "Finance")):
    row = re.search(key + r" & (\d+) & ([0-9.]+) & ([0-9.]+) \([^)]*\) & ([0-9.]+) \([^)]*\) & ([0-9.]+) & ([0-9.]+) \([^)]*\) & ([0-9.]+) \(", t22)
    a0 = next(r for r in cl if r["domain"] == dom and r["arm"] == "action" and r["round"] == "0")
    a3 = next(r for r in cl if r["domain"] == dom and r["arm"] == "action" and r["round"] == "3")
    n3 = next(r for r in cl if r["domain"] == dom and r["arm"] == "neutral" and r["round"] == "3")
    check(f"Fig3 {dom} chains", a0["chains"], row.group(1)); check(f"Fig3 {dom} open LA", a0["au"], row.group(2)); check(f"Fig3 {dom} r3 LA action", a3["au"], row.group(3)); check(f"Fig3 {dom} r3 LA control", n3["au"], row.group(4))
    check(f"Fig3 {dom} open UA", a0["us"], row.group(5)); check(f"Fig3 {dom} r3 UA action", a3["us"], row.group(6)); check(f"Fig3 {dom} r3 UA control", n3["us"], row.group(7))
print("Fig3 vs Table 22: checked 21 cells")

# ---- Figure 6 (restatements) vs Table 21
R = json.load(open("scratch/iclr_seven/restatement.json", encoding="utf-8"))
t21 = table_block(tex["extension_results_appendix.tex"], "tab:restatements")
trows = re.findall(r"\n\s*(\d) & (no|yes) & ([0-9.]+) \([^)]*\) & (\d+)/(\d+) & ([0-9.]+) & ([0-9.]+) ", t21)
print("Table 21 rows:", len(trows), "restatement.json keys:", list(R.keys()))
for lev, ins, pf, ex, exn, ua, la in trows:
    arm = "without" if ins == "no" else "with"
    i = "024".index(lev)
    kf = R["PF"][arm][i]; check(f"Fig6 PF {arm} {lev}", 100 * kf / R["N"], pf)
    if "EXACT" in R:
        check(f"Fig6 exact {arm} {lev}", R["EXACT"][arm][i], ex)
    if "UA" in R:
        check(f"Fig6 UA {arm} {lev}", R["UA"][arm][i], ua)

# ---- Figure 7 (mechanism) vs Table 25
M = json.load(open("scratch/iclr_seven/mechanism.json", encoding="utf-8"))
t25 = table_block(tex["extension_results_appendix.tex"], "tab:cause")
NAMES = {"Closed loop, shared history": "Closed loop, shared history blocks", "Closed loop, agent's own lines": "Closed loop, the agent's own lines"}
for name, counts in M:
    key = NAMES.get(name, name)
    row = re.search(re.escape(key) + r" & (\d+) & (\d+) & (\d+) & (\d+) & (\d+) & (\d+) & (\d+) ", t25)
    if not row:
        bad.append(f"Fig7 row not found in Table 25: {name}"); continue
    tab = [int(x) for x in row.groups()[2:7]]
    if tab != counts:
        bad.append(f"MISMATCH Fig7 {name}: figure {counts} vs table {tab}")
print("Fig7 vs Table 25: checked", len(M), "rows")

for b in bad:
    print(b)
print("mismatches:", len(bad))
sys.exit(1 if bad else 0)
