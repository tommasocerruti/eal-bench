"""Writer-side compute figure over all seven writers, in the layout of the paper's figure.
A: pooled legitimate action rate and targeted unauthorized action rate against k.
B: exact memory available in the pool, selected by writer self-review, and selected by the independent reviewer.
C: incremental typed memory final-state error and error introduction.
Error bars: 95% writer-cluster bootstrap percentile intervals (10,000 resamples of writers)."""
import csv
import random
import sys
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SEVEN = "results/procurement/20260913__seven_writer_ttc_k8_analysis"
INDEP = "results/procurement/20260815__deepseek_independent_ttc_k8_analysis_v2"
OUT = sys.argv[1]
K = [1, 2, 4, 8]
BLUE, ORANGE, GRAY = "#4C72B0", "#DD8452", "#555555"


def rows(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def boot(by_writer, weights=None, n=10000, seed=0):
    """by_writer: list of (value, weight) per writer; returns (lo, hi) of the weighted mean over writer resamples."""
    rnd = random.Random(seed)
    vals = [(v, w) for v, w in by_writer if v is not None]
    if len(vals) < 2:
        return None
    est = []
    for _ in range(n):
        s = [vals[rnd.randrange(len(vals))] for _ in vals]
        tw = sum(w for _, w in s)
        est.append(sum(v * w for v, w in s) / tw if tw else 0.0)
    est.sort()
    return est[int(0.025 * n)], est[int(0.975 * n) - 1]


# ---- panel A: pooled behavior
pooled = {int(r["k"]): r for r in rows(f"{SEVEN}/pooled_behavior_by_condition.csv") if r["condition_id"] == "pooled"}
au = [100 * f(pooled[k]["authorized_use_rate"]) for k in K]
us = [100 * f(pooled[k]["targeted_unauthorized_submission_rate"]) for k in K]
byw = defaultdict(list)
for r in rows(f"{SEVEN}/behavior_by_writer_condition.csv"):
    if r["condition_id"] == "pooled":
        byw[int(r["k"])].append(r)
au_ci = [boot([(100 * f(r["authorized_use_rate"]), f(r["authorized_request_count"])) for r in byw[k]]) for k in K]
us_ci = [boot([(100 * f(r["targeted_unauthorized_submission_rate"]), f(r["unauthorized_request_count"])) for r in byw[k]]) for k in K]

# ---- panel B: selection
sel = {int(r["k"]): r for r in rows(f"{SEVEN}/pooled_selection_scaling.csv")}
avail = [100 * f(sel[k]["pool_contains_full_fidelity_exact_rate"]) for k in K]
selfsel = [100 * f(sel[k]["reviewer_selected_full_fidelity_exact_rate"]) for k in K]
sbw = defaultdict(list)
for r in rows(f"{SEVEN}/selection_by_writer.csv"):
    sbw[int(r["k"])].append(r)
avail_ci = [boot([(100 * f(r["pool_contains_full_fidelity_exact_rate"]), f(r.get("typed_pools") or 24)) for r in sbw[k]]) for k in K]
self_ci = [boot([(100 * f(r.get("reviewer_selected_full_fidelity_exact_rate")), f(r.get("typed_pools") or 24)) for r in sbw[k]]) for k in K]
# independent review: per pool rows, typed pools only, method deepseek_review
ind = defaultdict(lambda: [0, 0])
ind_w = defaultdict(lambda: defaultdict(lambda: [0, 0]))
for r in rows(f"{INDEP}/selection_by_pool.csv"):
    if r["method"] != "deepseek_review" or "typed" not in r["condition_id"]:
        continue
    k = int(r["k"]); hit = r["selected_exact"] == "True"
    ind[k][0] += hit; ind[k][1] += 1
    ind_w[k][r["writer_target"]][0] += hit; ind_w[k][r["writer_target"]][1] += 1
indep = [100 * ind[k][0] / ind[k][1] if ind[k][1] else None for k in K]
indep_ci = [boot([(100 * a / b, b) for a, b in ind_w[k].values() if b]) if ind[k][1] else None for k in K]
import os, json as _json
if os.path.exists("scratch/iclr_seven/parity_pool.json"):
    _ir = _json.load(open("scratch/iclr_seven/parity_pool.json", encoding="utf-8"))["independent_review_selected_exact"]
    indep = [None] + [_ir[str(k)]["rate"] for k in (2, 4, 8)]; indep_ci = [None] * 4
if indep[0] is None:  # k=1 has a single candidate, so selection equals availability
    indep[0] = avail[0]; indep_ci[0] = avail_ci[0]

# ---- panel C: incremental mechanisms
mech = {int(r["k"]): r for r in rows(f"{SEVEN}/pooled_incremental_mechanisms.csv")}
final_err = [100 * f(mech[k]["final_error_rate"]) for k in K]
intro = [100 * f(mech[k]["error_introduction_rate"]) for k in K]
mbw = defaultdict(list)
for r in rows(f"{SEVEN}/incremental_mechanisms_by_writer.csv"):
    if r["condition_id"] == "incremental_typed":
        mbw[int(r["k"])].append(r)
final_ci = [boot([(100 * f(r["final_error_rate"]), f(r["selected_trajectories"])) for r in mbw[k]]) for k in K]
intro_ci = [boot([(100 * f(r["error_introduction_rate"]), f(r["correct_origin_transitions"])) for r in mbw[k]]) for k in K]


def draw(ax, y, ci, color, marker, label, ls="-"):
    x = range(len(K))
    lo = [y[i] - ci[i][0] if ci[i] else 0 for i in x]
    hi = [ci[i][1] - y[i] if ci[i] else 0 for i in x]
    ax.errorbar(list(x), y, yerr=[lo, hi], color=color, marker=marker, linestyle=ls, capsize=2.5, linewidth=1.2, markersize=4.5, label=label, zorder=3)


plt.rcParams.update({"font.family": "DejaVu Sans", "mathtext.fontset": "dejavusans", "font.size": 9.5, "axes.labelsize": 9.5, "xtick.labelsize": 9, "ytick.labelsize": 9,
                     "axes.spines.top": False, "axes.spines.right": False, "savefig.bbox": "tight", "pdf.fonttype": 42})
fig = plt.figure(figsize=(7.2, 2.5))
gs = fig.add_gridspec(2, 3, height_ratios=[1, 1], hspace=0.12, wspace=0.55)
a_top = fig.add_subplot(gs[0, 0]); a_bot = fig.add_subplot(gs[1, 0], sharex=a_top)
b = fig.add_subplot(gs[:, 1]); c = fig.add_subplot(gs[:, 2])
draw(a_top, au, au_ci, BLUE, "o", "Legitimate action rate")
draw(a_bot, us, us_ci, ORANGE, "s", "Targeted unauthorized action rate", ls="--")
a_top.set_ylim(88, 100); a_top.set_yticks([90, 95, 100]); a_bot.set_ylim(0, 20); a_bot.set_yticks([0, 10, 20])
a_top.set_ylabel("Legitimate\naction rate"); a_bot.set_ylabel("Unauthorized\naction rate")
a_top.tick_params(labelbottom=False); a_top.set_title(r"$\bf{A}$  Downstream behavior", loc="left", fontsize=10)
draw(b, avail, avail_ci, BLUE, "o", "Exact memory in pool")
draw(b, selfsel, self_ci, ORANGE, "s", "Writer self-review selects it", ls="--")
draw(b, indep, indep_ci, GRAY, "^", "Independent review selects it", ls=":")
b.set_ylim(0, 75); b.set_ylabel("Exact-memory rate"); b.set_title(r"$\bf{B}$  Generation vs. selection", loc="left", fontsize=10)
b.legend(frameon=False, fontsize=8, loc="upper left")
draw(c, final_err, final_ci, BLUE, "o", "Final-state error")
draw(c, intro, intro_ci, ORANGE, "s", "Error introduction", ls="--")
c.set_ylim(0, 100); c.set_ylabel("Error rate"); c.set_title(r"$\bf{C}$  Incremental typed memory", loc="left", fontsize=10)
c.legend(frameon=False, fontsize=8, loc="upper right")
for ax in (a_bot, b, c):
    ax.set_xticks(range(len(K))); ax.set_xticklabels([f"k={k}" for k in K]); ax.set_xlabel("Writer candidates")
for ax in (a_top, a_bot, b, c):
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.yaxis.grid(True, color="#dddddd", zorder=0); ax.set_axisbelow(True)
fig.savefig(OUT + ".pdf"); fig.savefig(OUT + ".png", dpi=200)
print("ttc seven ok")
print("A:", [f"{v:.1f}" for v in au], [f"{v:.1f}" for v in us])
print("B:", [f"{v:.1f}" for v in avail], [f"{v:.1f}" for v in selfsel], [f"{v:.1f}" if v is not None else "-" for v in indep])
print("C:", [f"{v:.1f}" for v in final_err], [f"{v:.1f}" for v in intro])
