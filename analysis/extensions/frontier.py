"""Figure 4 variant for the co-author: only the four strategies on the frontier (typed incremental baseline, source-authority
gate, bounded event sourcing, writer instruction) and the dashed line through them. No rebuild point, no one-shot reference.
Same data, styling, axes and canvas as fig4_final.py; written next to the figure in use as mitigation_pareto_frontier_four."""

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

PTS = {
    k: tuple(v)
    for k, v in json.load(
        open("results/extensions/snapshots/fig4_points.json", encoding="utf-8")
    ).items()
}
PTS["baseline"] = tuple(
    json.load(open("results/extensions/snapshots/table4_pooled.json", encoding="utf-8"))[
        "typed_incremental_pooled"
    ]
)
SPEC = {
    "baseline": ("o", "tab:blue", 8, "Typed incremental", (7, -16, "left")),
    "gate": ("s", "tab:orange", 7, "Source-authority gate", (7, -14, "left")),
    "event": ("s", "tab:green", 7, "Bounded event" + chr(10) + "sourcing", (7, -18, "left")),
    "instruction": ("D", "tab:red", 6.5, "Writer instruction", (-8, -22, "right")),
}
plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "mathtext.fontset": "dejavusans",
        "font.size": 8,
        "axes.labelsize": 8,
        "legend.fontsize": 7.5,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.facecolor": "white",
        "figure.facecolor": "white",
    }
)
fig, ax = plt.subplots(figsize=(5.5, 2.6))
ax.grid(True, color="#DDDDDD", linewidth=0.6)
ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
front = sorted(PTS[k] for k in SPEC)
ax.plot(
    [x for x, _ in front],
    [y for _, y in front],
    linestyle="--",
    color="#999999",
    linewidth=1.0,
    zorder=1,
)
for k, (mk, col, ms, lab, (dx, dy, ha)) in SPEC.items():
    x, y = PTS[k]
    ax.plot(x, y, marker=mk, markersize=ms, color=col, linestyle="none", zorder=3)
    ax.annotate(
        lab,
        (x, y),
        textcoords="offset points",
        xytext=(dx, dy),
        ha=ha,
        fontsize=7.5,
        color="#222222",
    )
ax.set_xlim(0, 34)
ax.set_ylim(45, 101)
ax.tick_params(axis="both", labelsize=7.5)
ax.set_xlabel("Unauthorized action rate (%)" + chr(10) + "[lower = more safety]", fontsize=8)
ax.set_ylabel("Legitimate action rate (%)" + chr(10) + "[higher = more utility]", fontsize=8)
handles = [
    plt.Line2D(
        [], [], marker="o", color="#444444", linestyle="none", markersize=7, label="Baseline"
    ),
    plt.Line2D(
        [], [], marker="s", color="#444444", linestyle="none", markersize=6, label="Origin checks"
    ),
    plt.Line2D(
        [],
        [],
        marker="D",
        color="#444444",
        linestyle="none",
        markersize=5.5,
        label="Writer-side change",
    ),
]
ax.legend(
    handles=handles,
    frameon=False,
    loc="lower right",
    ncol=1,
    fontsize=7.5,
    handlelength=1.3,
    handletextpad=0.6,
    labelspacing=0.7,
    borderaxespad=0.6,
)
fig.savefig(OUT + ".pdf", bbox_inches="tight")
fig.savefig(OUT + ".png", dpi=200, bbox_inches="tight")
print("points:", {k: (round(PTS[k][0], 1), round(PTS[k][1], 1)) for k in SPEC})
print("fig4 four-point variant ok")
