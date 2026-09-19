"""After the Inkling chain: pool the event-sourcing table over seven writers (when all nine reruns are analysed), and
refresh the rebuild cells (when the two cybersecurity rebuild seeds are in). Regenerates Figures 2 and 4 and copies them.
Run from the eal-bench root after event_inkling_analysis.py and parity_pool.py. Prints every number it writes."""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

ICLR = pathlib.Path(os.environ.get("ICLR_DIR", r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr"))
S = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("results/figures")
B = chr(92)
POOL = json.load(open("scratch/iclr_seven/parity_pool.json", encoding="utf-8"))
DOMS = ["procurement", "cybersecurity", "finance"]
DOMNAME = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance"}
pct = lambda k, n: 100 * k / n
f1 = lambda v: f"{v:.1f}"


def sub1(name, old, new):
    p = ICLR / name
    t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (name, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n")
    print("ok", name, old[:60])


def resub_(pattern, repl, s, count=1):
    n = len(re.findall(pattern, s))
    assert n >= 1, ("pattern not found", pattern[:60])
    return re.sub(pattern, lambda m: repl, s, count=count)


# ------------------------------------------------------------------ events
event5 = {"procurement": (312, 116, 1045, 967, 1080), "cybersecurity": (200, 175, 1704, 1466, 1920), "finance": (490, 66, 944, 128, 960)}
EV = POOL["event_by_writer"]
analysed = len(list(pathlib.Path("results/analysis/event_sourcing").glob("event-s*-inkling")))
ink_ok = all(f"{d}|unauthorized_submission" in EV.get("inkling_baseten", {}) for d in DOMS) and analysed == 9
print("inkling event seeds analysed:", analysed, "-> seven writers" if ink_ok else "-> not yet")
fig4 = json.load(open("scratch/iclr_seven/fig4_points.json", encoding="utf-8"))
if ink_ok and os.environ.get("SKIP_EVENTS") != "1":
    EVENT = {}; tote = [0] * 5
    for dom in DOMS:
        uo, ue, lo, le, n = event5[dom]
        for w in ("deepseek_v4_1_flash_baseten", "inkling_baseten"):
            a = EV[w][f"{dom}|unauthorized_submission"]; b = EV[w][f"{dom}|authorized_use"]
            uo += a[0]; ue += a[2]; lo += b[0]; le += b[2]; n += a[1]
        EVENT[dom] = (n, uo, ue, lo, le)
        for i, v in enumerate((uo, ue, lo, le, n)):
            tote[i] += v
    EVENT["pooled"] = (tote[4], tote[0], tote[1], tote[2], tote[3])
    e = EVENT; pe = e["pooled"]
    print("EVENT", EVENT)
    p = ICLR / "event_sourcing_appendix.tex"; s = p.read_text(encoding="utf-8")
    s = resub_(r"Values pool " + B + B + r"updated\{six\} writers, three seeds, and both executors\.\}", "Values pool " + B + "updated{all writers, three seeds, and both executors}.}", s)
    rows_e = [f"    {DOMNAME[d]} & {e[d][1]}/{e[d][0]} ({f1(pct(e[d][1], e[d][0]))}" + B + f"%) & {e[d][2]}/{e[d][0]} ({f1(pct(e[d][2], e[d][0]))}" + B + f"%) & {e[d][3]}/{e[d][0]} ({f1(pct(e[d][3], e[d][0]))}" + B + f"%) & {e[d][4]}/{e[d][0]} ({f1(pct(e[d][4], e[d][0]))}" + B + "%) " + B + B for d in DOMS]
    i = s.index("    Procurement & 332/1296 (25.6" + B + "%)"); j = s.index("    " + B + "midrule", i)
    s = s[:i] + "\n".join(rows_e) + "\n" + s[j:]
    tb = B + B + "textbf"  # regex form
    tbl = B + "textbf"  # literal form
    s = resub_(tb + r"\{Pooled\} & " + tb + r"\{[^}]+\} & " + tb + r"\{[^}]+\} & " + tb + r"\{[^}]+\} & " + tb + r"\{[^}]+\} " + B + B + B + B,
               tbl + "{Pooled} & " + tbl + "{" + f"{pe[1]}/{pe[0]} ({f1(pct(pe[1], pe[0]))}" + B + "%)} & " + tbl + "{" + f"{pe[2]}/{pe[0]} ({f1(pct(pe[2], pe[0]))}" + B + "%)} & " + tbl + "{" + f"{pe[3]}/{pe[0]} ({f1(pct(pe[3], pe[0]))}" + B + "%)} & " + tbl + "{" + f"{pe[4]}/{pe[0]} ({f1(pct(pe[4], pe[0]))}" + B + "%)} " + B + B, s)
    s = resub_(r" " + B + B + r"revised\{Inkling's event writer reasons inside the completion[^}]*\}", "", s)
    s = resub_(r"is about \d+ percentage points, with a 95" + B + B + r"% interval that excludes zero by a wide margin\.",
               f"is about {abs(pct(pe[2], pe[0]) - pct(pe[1], pe[0])):.0f} percentage points, with a 95" + B + "% interval that excludes zero by a wide margin.", s)
    p.write_text(s, encoding="utf-8", newline="\n"); print("event appendix updated")
    # main text, Section 4.6 origin-check sentence (blue)
    m = ICLR / "main.tex"; t = m.read_text(encoding="utf-8")
    pat = (r"and bounded event sourcing cuts it from [0-9.]+" + B + B + r"% to [0-9.]+" + B + B + r"%\. Both pay in legitimate use: the legitimate action rate falls to ([0-9.]+" + B + B + r"%) under the gate and to [0-9.]+" + B + B + r"% under event sourcing, from ([0-9.]+" + B + B + r"%) and [0-9.]+" + B + B + r"%\.")
    mm = re.search(pat, t); assert mm, "4.6 sentence not found"
    new = (f"and bounded event sourcing cuts it from {f1(pct(pe[1], pe[0]))}" + B + f"% to {f1(pct(pe[2], pe[0]))}" + B + "%. Both pay in legitimate use: the legitimate action rate falls to " + mm.group(1)
           + f" under the gate and to {f1(pct(pe[4], pe[0]))}" + B + "% under event sourcing, from " + mm.group(2) + f" and {f1(pct(pe[3], pe[0]))}" + B + "%.")
    t = t[:mm.start()] + new + t[mm.end():]; m.write_text(t, encoding="utf-8", newline="\n"); print("4.6 event numbers:", new[:120])
    fig4["baseline"] = (pct(pe[1], pe[0]), pct(pe[3], pe[0])); fig4["event"] = (pct(pe[2], pe[0]), pct(pe[4], pe[0]))

# ------------------------------------------------------------------ rebuild
D = POOL["designs"]
missing = POOL["missing"]
print("missing:", missing)
if not missing:
    c = D["cybersecurity"]
    sub1("extension_mitigations_appendix.tex", "    Cybersecurity & 12.2 & 86.8 & 14.0 & 84.8 & 6.2 & 93.3 & 20.4 & 78.7 " + B + B,
         f"    Cybersecurity & {f1(c['typed']['ua'])} & {f1(c['typed']['la'])} & {f1(c['hybrid']['ua'])} & {f1(c['hybrid']['la'])} & {f1(c['rebuild']['ua'])} & {f1(c['rebuild']['la'])} & {f1(c['instruction']['ua'])} & {f1(c['instruction']['la'])} " + B + B)
    print("rebuild cells:", {d: (f1(D[d]["rebuild"]["ua"]), f1(D[d]["rebuild"]["la"]), D[d]["rebuild"]["ua_n"]) for d in DOMS}, "pooled", (f1(D["pooled"]["rebuild"]["ua"]), f1(D["pooled"]["rebuild"]["la"])))
    fig4["rebuild"] = (D["pooled"]["rebuild"]["ua"], D["pooled"]["rebuild"]["la"])
json.dump({d: [[D[d]["hybrid"]["ua"], D[d]["hybrid"]["la"]], [D[d]["rebuild"]["ua"], D[d]["rebuild"]["la"]], [D[d]["instruction"]["ua"], D[d]["instruction"]["la"]]] for d in DOMS}, open("scratch/iclr_seven/fig2_designs.json", "w"), indent=1)
json.dump(fig4, open("scratch/iclr_seven/fig4_points.json", "w"), indent=1)

# ------------------------------------------------------------------ figures
PY = sys.executable
for script, out in (("fig2_final.py", "fig2_final"), ("fig4_final.py", "fig4_final")):
    r = subprocess.run([PY, f"scratch/iclr_seven/{script}", str(S / out)], capture_output=True, text=True)
    assert r.returncode == 0, (script, r.stderr[-800:])
shutil.copy(S / "fig2_final.pdf", ICLR / "figures/EAL-Bench_memory_design.pdf")
shutil.copy(S / "fig4_final.pdf", ICLR / "figures/mitigation_pareto_frontier.pdf")
print("figures regenerated; fig4 points:", {k: (round(v[0], 1), round(v[1], 1)) for k, v in fig4.items()})
