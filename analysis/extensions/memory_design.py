"""Figure 2, two rows. Top: the four memory conditions on the paper's writer route (Table 4). Bottom: the design comparison on
its own runs (Table 34): typed incremental memory measured on those runs, the hybrid schema, rebuild every three blocks, and
the writer instruction. Every bar equals the corresponding table cell. Seven writers, three seeds, both executors."""

import argparse
import json
import matplotlib
import matplotlib.pyplot as plt

_parser = argparse.ArgumentParser(
    description="Archived extension analysis; use analysis.extension_results."
)
_parser.add_argument("out", help="output path (figure prefix for plots)")
OUT = _parser.parse_args().out

matplotlib.use("Agg")

S = json.load(open("results/extensions/snapshots/seven_summary.json", encoding="utf-8"))[
    "pooled_by_condition"
]
D = json.load(open("results/extensions/snapshots/parity_pool.json", encoding="utf-8"))["designs"]
DOMS = ["procurement", "cybersecurity", "finance"]
NAME = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance"}
CONDS = ["one_shot_text", "incremental_text", "one_shot_typed", "incremental_typed"]
TOP = ["Text one-shot", "Text incremental", "Typed one-shot", "Typed incremental"]
DESIGNS = ["typed", "hybrid", "rebuild", "instruction"]
BOTTOM = ["Typed incremental", "Hybrid incremental", "Rebuild every 3 blocks", "Writer instruction"]
blue, orange = "#4C72B0", "#DD8452"
plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 7.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
    }
)
fig, axes = plt.subplots(2, 3, figsize=(5.5, 3.6), sharey=True)
w = 0.38


def panel(ax, la, ua, labels, title):
    x = range(len(la))
    ax.bar([i - w / 2 for i in x], la, w, color=blue, zorder=3, label="Legitimate action rate")
    ax.bar([i + w / 2 for i in x], ua, w, color=orange, zorder=3, label="Unauthorized action rate")
    for i, v in enumerate(ua):
        ax.text(
            i + w / 2, v + 1.5, f"{v:.1f}", ha="center", va="bottom", fontsize=5.2, color="#7a3f10"
        )
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=38, ha="right", rotation_mode="anchor", fontsize=6.4)
    if title:
        ax.set_title(title, fontsize=8.5, pad=4)
    ax.set_ylim(0, 106)
    ax.set_yticks(range(0, 101, 20))
    ax.set_yticklabels([f"{v}%" for v in range(0, 101, 20)])
    ax.yaxis.grid(True, color="#dddddd", zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", length=0, pad=1)
    ax.set_xlim(-0.6, len(la) - 0.4)


for col, dom in enumerate(DOMS):
    la = [100 * S[f"{dom}|{c}"]["au_k"] / S[f"{dom}|{c}"]["au_n"] for c in CONDS]
    ua = [100 * S[f"{dom}|{c}"]["us_k"] / S[f"{dom}|{c}"]["us_n"] for c in CONDS]
    panel(axes[0, col], la, ua, TOP, NAME[dom])
    la2 = [D[dom][k]["la"] for k in DESIGNS]
    ua2 = [D[dom][k]["ua"] for k in DESIGNS]
    panel(axes[1, col], la2, ua2, BOTTOM, None)
axes[0, 0].set_ylabel("Memory conditions")
axes[1, 0].set_ylabel("Writer-side changes")
h, item = axes[0, 0].get_legend_handles_labels()
fig.tight_layout(rect=(0, 0.04, 1, 1), w_pad=1.2, h_pad=1.6)
axes[1, 1].legend(
    h,
    item,
    loc="upper center",
    ncol=2,
    frameon=False,
    bbox_to_anchor=(0.5, -0.52),
    columnspacing=3.0,
    handlelength=1.6,
    handletextpad=0.6,
    fontsize=7.5,
)
fig.savefig(OUT + ".pdf")
fig.savefig(OUT + ".png", dpi=200)
print("fig2 ok")
for dom in DOMS:
    print(
        dom,
        "bottom row:",
        [(k, round(D[dom][k]["ua"], 1), round(D[dom][k]["la"], 1)) for k in DESIGNS],
    )
