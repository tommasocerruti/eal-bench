"""Appendix figure: where the failure enters and what the writer did there, from the judged failures (tab:cause)."""

import argparse
import matplotlib
import matplotlib.pyplot as plt
import json

_parser = argparse.ArgumentParser(
    description="Archived extension analysis; use analysis.extension_results."
)
_parser.add_argument("out", help="output path (figure prefix for plots)")
OUT = _parser.parse_args().out

matplotlib.use("Agg")

ROWS = [  # setting, failures per label: restatement applied, own action as approval, change misapplied, update rejected, other
    ("Open loop, procurement", [545, 0, 1, 0, 3]),
    ("Open loop, finance", [268, 0, 4, 0, 0]),
    ("Open loop, cybersecurity", [0, 0, 33, 270, 0]),
    ("Closed loop, shared history", [274, 0, 6, 29, 0]),
    ("Closed loop, agent's own lines", [1, 186, 2, 0, 3]),
    ("With instruction, procurement and finance", [141, 8, 6, 4, 0]),
    ("With instruction, cybersecurity", [0, 6, 42, 418, 0]),
]
if True:  # required input verified by analysis.extension_results
    ROWS = [
        (r[0], r[1])
        for r in json.load(
            open("results/extensions/snapshots/mechanism_det.json", encoding="utf-8")
        )
    ]
LABELS = [
    "Restatement applied",
    "Own action read as approval",
    "Authoritative change misapplied",
    "Update rejected",
    "Other",
]
COLORS = ["#DD8452", "#C44E52", "#8172B3", "#4C72B0", "#BBBBBB"]
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "mathtext.fontset": "dejavusans",
        "font.size": 7.5,
        "axes.labelsize": 7.5,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
    }
)
fig, ax = plt.subplots(figsize=(5.5, 2.6))
names = [r[0] for r in ROWS][::-1]
counts = [r[1] for r in ROWS][::-1]
totals = [sum(c) for c in counts]
left = [0.0] * len(ROWS)
for j, (lab, col) in enumerate(zip(LABELS, COLORS)):
    vals = [100 * c[j] / t for c, t in zip(counts, totals)]
    ax.barh(range(len(ROWS)), vals, left=left, color=col, label=lab, height=0.66, zorder=3)
    left = [item + v for item, v in zip(left, vals)]
for i, t in enumerate(totals):
    ax.text(101, i, f"n = {t:,}", va="center", ha="left", fontsize=7, color="#444444")
ax.set_yticks(range(len(ROWS)))
ax.set_yticklabels(names)
ax.set_xlim(0, 118)
ax.set_xticks([0, 25, 50, 75, 100])
ax.set_xticklabels([f"{v}%" for v in (0, 25, 50, 75, 100)])
ax.set_xlabel("Share of failures (final attribution label)")
ax.xaxis.grid(True, color="#dddddd", zorder=0)
ax.set_axisbelow(True)
ax.tick_params(axis="y", length=0)
ax.legend(
    loc="upper center",
    bbox_to_anchor=(0.42, -0.24),
    ncol=3,
    frameon=False,
    fontsize=7,
    handlelength=1.2,
    columnspacing=1.4,
)
fig.savefig(OUT + ".pdf")
fig.savefig(OUT + ".png", dpi=200)
print("mechanism figure ok")
