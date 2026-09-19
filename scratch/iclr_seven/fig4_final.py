"""Figure 4: safety-utility frontier over all tested mitigations on one pooled population.
Points: typed incremental baseline, source-authority gate, bounded event sourcing (six writers, three seeds, both executors),
writer instruction and rebuild every three blocks (five writers, three seeds, both executors)."""
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = sys.argv[1]
PTS = {"baseline": (23.8, 93.4), "gate": (6.3, 54.4), "event": (8.0, 69.2), "instruction": (12.6, 88.6), "rebuild": (4.5, 95.6)}
import os, json
if os.path.exists("scratch/iclr_seven/fig4_points.json"):
    PTS = {k: tuple(v) for k, v in json.load(open("scratch/iclr_seven/fig4_points.json", encoding="utf-8")).items()}
if os.path.exists("scratch/iclr_seven/table4_pooled.json"):  # baseline = typed incremental memory of Table 4, pooled over domains
    PTS["baseline"] = tuple(json.load(open("scratch/iclr_seven/table4_pooled.json", encoding="utf-8"))["typed_incremental_pooled"])
SPEC = {"baseline": ("o", "tab:blue", 8, "Typed incremental", (7, -16, "left")),
        "gate": ("s", "tab:orange", 7, "Source-authority gate", (7, -14, "left")),
        "event": ("s", "tab:green", 7, "Bounded event" + chr(10) + "sourcing", (7, -18, "left")),
        "instruction": ("D", "tab:red", 6.5, "Writer instruction", (-8, -22, "right")),
        "rebuild": ("D", "tab:purple", 6.5, "Rebuild every 3 blocks", (7, 4, "left"))}
plt.rcParams.update({"font.family": "DejaVu Sans", "mathtext.fontset": "dejavusans", "font.size": 10, "axes.labelsize": 10.5, "legend.fontsize": 10.5, "pdf.fonttype": 42, "ps.fonttype": 42,
                     "savefig.facecolor": "white", "figure.facecolor": "white"})
fig, ax = plt.subplots(figsize=(3.9, 3.1))
ax.grid(True, color="#DDDDDD", linewidth=0.6); ax.set_axisbelow(True)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
# the frontier through the non-dominated points of the three-way comparison, and the rebuild point that dominates it
front = sorted([PTS[k] for k in ("gate", "event", "instruction", "baseline")])
ax.plot([x for x, _ in front], [y for _, y in front], linestyle="--", color="#999999", linewidth=1.0, zorder=1)
for k, (mk, col, ms, lab, (dx, dy, ha)) in SPEC.items():
    x, y = PTS[k]
    ax.plot(x, y, marker=mk, markersize=ms, color=col, linestyle="none", zorder=3)
    ax.annotate(lab, (x, y), textcoords="offset points", xytext=(dx, dy), ha=ha, fontsize=9, color="#222222")
# reference: one-shot typed memory on the paper's writer route (Table 4), pooled over domains
SS = json.load(open("scratch/iclr_seven/seven_summary.json", encoding="utf-8"))["pooled_by_condition"]
ok = sum(SS[f"{d}|one_shot_typed"]["us_k"] for d in ("procurement", "cybersecurity", "finance")); on = sum(SS[f"{d}|one_shot_typed"]["us_n"] for d in ("procurement", "cybersecurity", "finance"))
ak = sum(SS[f"{d}|one_shot_typed"]["au_k"] for d in ("procurement", "cybersecurity", "finance")); an = sum(SS[f"{d}|one_shot_typed"]["au_n"] for d in ("procurement", "cybersecurity", "finance"))
ox, oy = 100 * ok / on, 100 * ak / an
ax.plot(ox, oy, marker="o", markersize=8, markerfacecolor="none", markeredgecolor="#555555", linestyle="none", zorder=3)
ax.annotate("Typed one-shot", (ox, oy), textcoords="offset points", xytext=(7, -14), ha="left", fontsize=9, color="#222222")
print("one-shot reference:", round(ox, 1), round(oy, 1))
ax.set_xlim(0, 34); ax.set_ylim(45, 101)
ax.tick_params(axis="both", labelsize=10)
ax.set_xlabel("Unauthorized action rate (%)" + chr(10) + "[lower = more safety]", fontsize=10.5)
ax.set_ylabel("Legitimate action rate (%)" + chr(10) + "[higher = more utility]", fontsize=10.5)
handles = [plt.Line2D([], [], marker="o", color="#444444", linestyle="none", markersize=7, label="Baseline"),
           plt.Line2D([], [], marker="s", color="#444444", linestyle="none", markersize=6, label="Origin checks"),
           plt.Line2D([], [], marker="D", color="#444444", linestyle="none", markersize=5.5, label="Writer-side changes"),
           plt.Line2D([], [], marker="o", markerfacecolor="none", markeredgecolor="#555555", linestyle="none", markersize=7, label="One-shot reference")]
ax.legend(handles=handles, frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5), ncol=1, fontsize=10.5, handlelength=1.4, handletextpad=0.6, labelspacing=0.9, borderaxespad=0.0)
fig.savefig(OUT + ".pdf", bbox_inches="tight"); fig.savefig(OUT + ".png", dpi=200, bbox_inches="tight")
print("fig4 ok")
