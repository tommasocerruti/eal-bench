"""Remove the change-tracking macros (added, revised, updated) from every tex file: unwrap each use brace-aware and delete
the three definitions. Also set the figure widths the restyled figures assume. Idempotent."""
import glob
import pathlib
import re

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
NAMES = ("added", "revised", "updated")
total = 0
for f in glob.glob(str(ICLR / "*.tex")):
    t = pathlib.Path(f).read_text(encoding="utf-8"); orig = t
    for name in NAMES:
        pat = B + name + "{"
        pos = 0
        while True:
            i = t.find(pat, pos)
            if i < 0:
                break
            k = i + len(pat); d = 1
            while k < len(t) and d:
                if t[k] == B:
                    k += 2; continue
                d += (t[k] == "{") - (t[k] == "}"); k += 1
            t = t[:i] + t[i + len(pat):k - 1] + t[k:]; total += 1
    if t != orig:
        pathlib.Path(f).write_text(t, encoding="utf-8", newline="\n"); print("unwrapped in", pathlib.Path(f).name)
print("macro uses removed:", total)
p = ICLR / "main.tex"; t = p.read_text(encoding="utf-8")
lines = t.split(chr(10))
keep = [l for l in lines if not re.match(re.escape(B + "newcommand{" + B) + r"(added|revised|updated)\}", l)]
print("macro definitions removed:", len(lines) - len(keep))
t = chr(10).join(keep)
for old, new in ((B + "includegraphics[width=0.62" + B + "linewidth]{figures/mitigation_pareto_frontier.pdf}", B + "includegraphics[width=0.72" + B + "linewidth]{figures/mitigation_pareto_frontier.pdf}"),
                 ("[width=0.76" + B + "linewidth]{evaluation_cue_appendix_writer_fidelity.pdf}", "[width=" + B + "linewidth]{evaluation_cue_appendix_writer_fidelity.pdf}"),
                 ("[width=0.76" + B + "linewidth]{evaluation_cue_appendix_writer_behavior.pdf}", "[width=" + B + "linewidth]{evaluation_cue_appendix_writer_behavior.pdf}"),
                 ("[width=0.8" + B + "linewidth]{evaluation_cue_appendix_executor_behavior.pdf}", "[width=" + B + "linewidth]{evaluation_cue_appendix_executor_behavior.pdf}")):
    if t.count(old) == 1:
        t = t.replace(old, new); print("width set:", new[-45:])
p.write_text(t, encoding="utf-8", newline="\n")
left = sum(pathlib.Path(f).read_text(encoding="utf-8").count(B + n + "{") for f in glob.glob(str(ICLR / "*.tex")) for n in NAMES)
print("remaining macro uses:", left)
