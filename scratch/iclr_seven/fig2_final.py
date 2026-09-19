import json, sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
OUT = sys.argv[1]
S = json.load(open("scratch/iclr_seven/seven_summary.json", encoding="utf-8"))["pooled_by_condition"]
DOMS = ["procurement", "cybersecurity", "finance"]
NAME = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance"}
CONDS = ["one_shot_text", "incremental_text", "one_shot_typed", "incremental_typed"]
# five-writer pooled values from tab:writer-side-mitigations (US, AU)
FIVE = {"procurement": [(12.9, 97.5), (6.0, 95.6), (5.8, 98.2)],
        "cybersecurity": [(12.7, 86.5), (6.0, 93.0), (21.8, 77.9)],
        "finance": [(11.7, 99.3), (0.0, 100.0), (1.7, 99.2)]}
import os
if os.path.exists("scratch/iclr_seven/fig2_designs.json"):
    FIVE = {d: [tuple(x) for x in v] for d, v in json.load(open("scratch/iclr_seven/fig2_designs.json", encoding="utf-8")).items()}
LABELS = ["Text one-shot", "Text incremental", "Typed one-shot", "Typed incremental", "Hybrid incremental", "Rebuild every 3 blocks", "Writer instruction"]
blue, orange = "#4C72B0", "#DD8452"
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"], "mathtext.fontset": "stix",
                     "font.size": 7.5, "axes.spines.top": False, "axes.spines.right": False, "savefig.bbox": "tight", "pdf.fonttype": 42})
fig, axes = plt.subplots(1, 3, figsize=(5.5, 2.15), sharey=True)
w = 0.4
for ax, dom in zip(axes, DOMS):
    au = [100*S[f"{dom}|{c}"]["au_k"]/S[f"{dom}|{c}"]["au_n"] for c in CONDS] + [a for _, a in FIVE[dom]]
    us = [100*S[f"{dom}|{c}"]["us_k"]/S[f"{dom}|{c}"]["us_n"] for c in CONDS] + [u for u, _ in FIVE[dom]]
    x = range(7)
    ax.bar([i - w/2 for i in x], au, w, color=blue, zorder=3, label="Legitimate action rate")
    ax.bar([i + w/2 for i in x], us, w, color=orange, zorder=3, label="Unauthorized action rate")
    for i, v in enumerate(us):
        ax.text(i + w/2, v + 1.5, f"{v:.1f}", ha="center", va="bottom", fontsize=5.2, color="#7a3f10")
    ax.set_xticks(list(x)); ax.set_xticklabels(LABELS, rotation=38, ha="right", rotation_mode="anchor", fontsize=6.6)
    ax.set_title(NAME[dom], fontsize=8.5, pad=4); ax.set_ylim(0, 106); ax.set_yticks(range(0, 101, 20))
    ax.set_yticklabels([f"{v}%" for v in range(0, 101, 20)])
    ax.yaxis.grid(True, color="#dddddd", zorder=0); ax.set_axisbelow(True); ax.tick_params(axis="x", length=0, pad=1)
    ax.set_xlim(-0.6, 6.6)
axes[0].set_ylabel("Rate")
h, l = axes[0].get_legend_handles_labels()
fig.tight_layout(rect=(0, 0, 1, 1), w_pad=1.2)
fig.canvas.draw()
r = fig.canvas.get_renderer(); y0 = axes[1].xaxis.get_tightbbox(r).transformed(axes[1].transAxes.inverted()).y0
axes[1].legend(h, l, loc='upper center', ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.43), columnspacing=3.0, handlelength=1.6, handletextpad=0.6, fontsize=7.5)
fig.savefig(OUT + ".pdf"); fig.savefig(OUT + ".png", dpi=200)
print("fig2 ok")
