"""Closed-loop figure: the action arm (the executor's own log lines written back into the history) against the neutral
control (same number of updates, same schedule, neutral content) over three rounds, one panel per domain, in the style
of the paper's writer-side compute figure. Top of each panel: authorized use. Bottom: unauthorized submission. Round 0
is the frozen memory before any write-back, answered in the open loop, shared by both arms. Error bars are pointwise 95%
bootstrap intervals over chains (a chain is one case, writer, executor, and base memory; arms are paired within it).

    uv run python -m analysis.plot_closed_loop_figure "results/*/*rounds3v2-both-*" --out results/figures/closed_loop_control
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import random
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE = "#0072B2"
VERMILLION = "#D55E00"
LIGHT_GRAY = "#D9D9D9"
BOOTSTRAP_SEED = 20260913
BOOTSTRAP_RESAMPLES = 5_000
DOMAINS = ["procurement", "cybersecurity", "finance"]
DOMAIN_TITLE = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance"}
ARMS = ["action", "neutral"]


def load_runs(patterns: list[str]) -> list[tuple[str, dict[str, Any]]]:
    runs = []
    for pat in patterns:
        for d in sorted(glob.glob(pat)):
            if "superseded" in d:
                continue
            m = json.load(open(Path(d) / "manifest.json", encoding="utf-8"))
            if m.get("status") == "completed" and m["options"].get("loop_content") == "both":
                runs.append((d, m))
    return runs


def collect(runs: list[tuple[str, dict[str, Any]]]) -> dict[str, dict[tuple[str, int], dict[tuple[str, str], list[int]]]]:
    """domain -> (arm, round) -> chain key -> [au_n, au_k, us_n, us_k]. Round 0 (open loop) is copied to both arms."""
    out: dict[str, dict[tuple[str, int], dict[tuple[str, str], list[int]]]] = {d: {} for d in DOMAINS}
    for d, m in runs:
        dom = m["domain_id"]
        with open(Path(d) / "trials.jsonl", encoding="utf-8") as fh:
            for line in fh:
                t = json.loads(line)
                st = t["metadata"]["study"]
                if st.get("loop") == "closed":
                    keys = [(st["arm"], st["round"])]
                elif st.get("loop") == "open":
                    keys = [(arm, 0) for arm in ARMS]
                else:
                    continue
                for key in keys:
                    cell = out[dom].setdefault(key, {}).setdefault((d, st["chain"]), [0, 0, 0, 0])
                    if t["request_authorized"]:
                        cell[0] += 1
                        cell[1] += t["requested_action_taken"]
                    else:
                        cell[2] += 1
                        cell[3] += t["requested_action_taken"]
    return out


def rate_ci(chains: list[list[int]], n_idx: int, k_idx: int, rng: random.Random) -> tuple[float, float, float]:
    n = sum(c[n_idx] for c in chains)
    k = sum(c[k_idx] for c in chains)
    point = 100 * k / n if n else float("nan")
    boots = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = rng.choices(chains, k=len(chains))
        bn = sum(c[n_idx] for c in sample)
        bk = sum(c[k_idx] for c in sample)
        if bn:
            boots.append(100 * bk / bn)
    boots.sort()
    return point, boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots)) - 1]


def style_axis(ax: Any, *, show_xlabel: bool) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#777777")
    ax.spines["bottom"].set_color("#777777")
    ax.tick_params(colors="#333333", width=0.7, length=3)
    ax.grid(axis="y", color=LIGHT_GRAY, linewidth=0.55, alpha=0.75)
    ax.set_axisbelow(True)
    if not show_xlabel:
        ax.tick_params(labelbottom=False)


def series(ax: Any, xs: list[int], pts: list[tuple[float, float, float]], arm: str, label: str) -> None:
    ys = [p[0] for p in pts]
    lo = [p[0] - p[1] for p in pts]
    hi = [p[2] - p[0] for p in pts]
    kw = dict(color=BLUE, marker="o", linestyle="-") if arm == "action" else dict(color=VERMILLION, marker="s", linestyle="--", markerfacecolor="white", markeredgewidth=1.1)
    ax.errorbar(xs, ys, yerr=[lo, hi], capsize=2, elinewidth=0.8, ecolor=kw["color"], label=label, linewidth=1.3, **kw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns", nargs="+")
    ap.add_argument("--out", default="results/figures/closed_loop_control")
    args = ap.parse_args()
    runs = load_runs(args.patterns)
    data = collect(runs)
    rng = random.Random(BOOTSTRAP_SEED)

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "mathtext.fontset": "dejavusans", "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10.2,
        "xtick.labelsize": 9.5, "ytick.labelsize": 9.5, "legend.fontsize": 9.5, "axes.linewidth": 0.7,
        "lines.linewidth": 1.3, "lines.markersize": 4.5, "pdf.fonttype": 42, "ps.fonttype": 42,
        "savefig.facecolor": "white", "figure.facecolor": "white",
    })
    fig = plt.figure(figsize=(7.5, 2.85))
    outer = fig.add_gridspec(1, 3, wspace=0.34, left=0.085, right=0.99, top=0.88, bottom=0.18)
    table_rows = []
    for col, dom in enumerate(DOMAINS):
        inner = outer[col].subgridspec(2, 1, height_ratios=[1.0, 1.0], hspace=0.12)
        ax_top = fig.add_subplot(inner[0])
        ax_bot = fig.add_subplot(inner[1], sharex=ax_top)
        rounds = sorted({r for (_, r) in data[dom]})
        for arm, label in (("action", "Own log written back"), ("neutral", "Neutral control")):
            au, us = [], []
            for r in rounds:
                chains = list(data[dom][(arm, r)].values())
                a = rate_ci(chains, 0, 1, rng)
                u = rate_ci(chains, 2, 3, rng)
                au.append(a)
                us.append(u)
                table_rows.append({"domain": dom, "arm": arm, "round": r, "chains": len(chains), "au": f"{a[0]:.1f}", "au_lo": f"{a[1]:.1f}", "au_hi": f"{a[2]:.1f}", "us": f"{u[0]:.1f}", "us_lo": f"{u[1]:.1f}", "us_hi": f"{u[2]:.1f}"})
            series(ax_top, rounds, au, arm, label)
            series(ax_bot, rounds, us, arm, label)
        style_axis(ax_top, show_xlabel=False)
        style_axis(ax_bot, show_xlabel=True)
        ax_top.set_title(r"$\bf{" + "ABC"[col] + "}$  " + DOMAIN_TITLE[dom], loc="left", fontsize=11, pad=4)
        if col == 0:
            ax_top.legend(frameon=False, loc="lower left", handlelength=1.6, fontsize=8.5, borderaxespad=0.3, labelspacing=0.4)
        ax_top.set_ylim(18, 102)
        ax_top.set_yticks([40, 60, 80, 100])
        ax_bot.set_ylim(0, 50)
        ax_bot.set_yticks([0, 10, 20, 30, 40, 50])
        ax_top.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax_bot.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
        ax_bot.set_xticks(rounds)
        ax_bot.set_xticklabels(["open" + chr(10) + "loop" if r == 0 else "round" + chr(10) + str(r) for r in rounds])
        pass
        if col == 0:
            ax_top.set_ylabel("Legitimate\naction rate")
            ax_bot.set_ylabel("Unauthorized\naction rate")
            pass
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=220, bbox_inches="tight")
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table_rows[0].keys()))
        w.writeheader()
        w.writerows(table_rows)
    print(f"{len(runs)} two-arm runs -> {out.with_suffix('.pdf')}, {out.with_suffix('.png')}, {out.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
