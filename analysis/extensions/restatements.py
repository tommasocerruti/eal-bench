"""Appendix figure: false authority against the number of later restatements of a superseded permission,
with and without the writer instruction; five writers pooled (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash).
Counts from scratch/section4_v2.py on the generated-v2 and mandate-generated-v2 runs."""

import argparse
import math
import matplotlib
import matplotlib.pyplot as plt
import json

_parser = argparse.ArgumentParser(
    description="Archived extension analysis; use analysis.extension_results."
)
_parser.add_argument("out", help="output path (figure prefix for plots)")
OUT = _parser.parse_args().out

matplotlib.use("Agg")

LEVELS = [0, 2, 4]
N = 540
PF = {
    "without": [4, 84, 59],
    "with": [0, 12, 8],
}  # false authority formed, of 540 unauthorized requests
UA = {"without": [1.1, 17.2, 11.5], "with": [0.6, 2.2, 1.9]}  # unauthorized action rate, %
EXACT = {"without": [32, 13, 16], "with": [56, 49, 54]}  # exact memories, of 180


if True:  # required input verified by analysis.extension_results
    _j = json.load(open("results/extensions/snapshots/restatement.json", encoding="utf-8"))
    N = _j["N"]
    PF = _j["PF"]
    UA = _j["UA"]
    EXACT = _j["EXACT"]
    M = _j["M"]
else:
    M = 180


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * max(0.0, c - h), 100 * min(1.0, c + h)


plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "mathtext.fontset": "dejavusans",
        "font.size": 9.5,
        "axes.labelsize": 9.8,
        "xtick.labelsize": 9.2,
        "ytick.labelsize": 9.2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
    }
)
fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.2))
x = range(3)
for arm, color, marker, ls in (("without", "#DD8452", "o", "-"), ("with", "#4C72B0", "s", "--")):
    label = "Without instruction" if arm == "without" else "With writer instruction"
    y = [100 * k / N for k in PF[arm]]
    ci = [wilson(k, N) for k in PF[arm]]
    axes[0].errorbar(
        list(x),
        y,
        yerr=[[max(0.0, y[i] - ci[i][0]) for i in x], [max(0.0, ci[i][1] - y[i]) for i in x]],
        color=color,
        marker=marker,
        linestyle=ls,
        capsize=2.5,
        linewidth=1.2,
        markersize=4.5,
        label=label,
        zorder=3,
    )
    axes[1].plot(
        list(x),
        UA[arm],
        color=color,
        marker=marker,
        linestyle=ls,
        linewidth=1.2,
        markersize=4.5,
        label=label,
        zorder=3,
    )
    axes[2].plot(
        list(x),
        [100 * k / M for k in EXACT[arm]],
        color=color,
        marker=marker,
        linestyle=ls,
        linewidth=1.2,
        markersize=4.5,
        label=label,
        zorder=3,
    )
axes[0].set_title(r"$\bf{A}$  False-authority rate", loc="left", fontsize=10.5)
axes[0].set_ylim(0, 22)
axes[1].set_title(r"$\bf{B}$  Unauthorized action rate", loc="left", fontsize=10.5)
axes[1].set_ylim(0, 22)
axes[2].set_title(r"$\bf{C}$  Exact memories", loc="left", fontsize=10.5)
axes[2].set_ylim(0, 40)
for ax in axes:
    ax.set_xticks(list(x))
    ax.set_xticklabels(["0", "2", "4"])
    ax.set_xlabel("Later restatements")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.yaxis.grid(True, color="#dddddd", zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlim(-0.3, 2.3)
axes[1].legend(frameon=False, fontsize=9, loc="upper left")
fig.tight_layout(w_pad=1.5)
fig.savefig(OUT + ".pdf")
fig.savefig(OUT + ".png", dpi=200)
print("restatement figure ok")
