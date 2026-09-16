import sys, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from analysis.plot_mitigation_frontier import ours, PAPER, style
OUT = sys.argv[1]
mine, _ = ours()
inst = mine["pooled"]["mandate"]
print("instruction pooled (US, AU):", inst, " matched baseline:", mine["pooled"]["ours_baseline"])
pts = dict(PAPER["pooled"]); pts["instruction"] = inst
plt.rcParams.update({"font.family": "serif", "font.size": 10, "axes.labelsize": 10, "legend.fontsize": 8.5, "pdf.fonttype": 42, "ps.fonttype": 42,
                     "savefig.facecolor": "white", "figure.facecolor": "white"})
fig, ax = plt.subplots(figsize=(4.7, 3.5))
style(ax)
order = sorted(pts.values())
ax.plot([x for x, _ in order], [y for _, y in order], linestyle="--", color="#999999", linewidth=1.0, zorder=1)
spec = {"baseline": ("o", "tab:blue", 8, "Typed incremental", (7, -16, "left")),
        "gate": ("s", "tab:orange", 7, "Source-authority gate", (7, -14, "left")),
        "event": ("s", "tab:green", 7, "Bounded event" + chr(10) + "sourcing", (7, -18, "left")),
        "instruction": ("D", "tab:red", 6.5, "Writer instruction", (-8, -22, "right"))}
for k, (mk, col, ms, lab, (dx, dy, ha)) in spec.items():
    x, y = pts[k]
    ax.plot(x, y, marker=mk, markersize=ms, color=col, linestyle="none", zorder=3)
    ax.annotate(f"{lab}" + chr(10) + f"({x:.1f}, {y:.1f})", (x, y), textcoords="offset points", xytext=(dx, dy), ha=ha, fontsize=8, color="#222222")
ax.set_xlim(0, 34); ax.set_ylim(45, 101)
ax.set_xlabel("Unauthorized action rate (%)" + chr(10) + "[lower = more safety]")
ax.set_ylabel("Legitimate action rate (%)" + chr(10) + "[higher = more utility]")
handles = [plt.Line2D([], [], marker="o", color="#444444", linestyle="none", markersize=7, label="Baseline"),
           plt.Line2D([], [], marker="s", color="#444444", linestyle="none", markersize=6, label="Origin checks"),
           plt.Line2D([], [], marker="D", color="#444444", linestyle="none", markersize=5.5, label="Writer instruction")]
ax.legend(handles=handles, frameon=False, loc="lower right", fontsize=8, handlelength=1.2, borderaxespad=0.4)
fig.savefig(OUT + ".pdf", bbox_inches="tight"); fig.savefig(OUT + ".png", dpi=200, bbox_inches="tight")
print("fig3 ok")
