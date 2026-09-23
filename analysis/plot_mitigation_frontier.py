"""Safety-utility frontier with the two extension mitigations added to the paper's two provenance mitigations.

Two populations share the figure and are drawn with different marker fills:
  * the paper's (filled): typed-incremental baseline, source-authority gate, bounded event sourcing; five writers
    (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Grok 4.3, Qwen Plus), three seeds per domain, both executors. Numbers are the
    paper's appendix tables (aligned three-seed source-authority results by domain; complete paired event-sourcing
    comparison) and are constants below.
  * this branch's (hollow): typed-incremental baseline, the one-line mandate, rebuild-from-history every three blocks;
    the five writers available on Baseten (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash), both
    executors, three seeds per domain for the baseline and the mandate; rebuild at three seeds in procurement and the
    canonical seed in cybersecurity and finance. Read from the run manifests.

Panel layout: the pooled frontier in the style of the paper's figure, and a domain-faceted version.

    uv run python -m analysis.plot_mitigation_frontier --out results/figures/mitigation_frontier
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

W = ["glm_5_2_baseten", "kimi_baseten", "nemotron_3_ultra_baseten", "inkling_baseten", "deepseek_v4_1_flash_baseten"]
ADDED = {"inkling_baseten", "deepseek_v4_1_flash_baseten"}
SEEDS = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
DOMAINS = ["procurement", "cybersecurity", "finance"]
TITLE = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance", "pooled": "All domains"}

# The paper's numbers: (unauthorized submission %, authorized use %). Baseline is typed incremental on the shared
# three-seed population; gate and event sourcing are on that same population.
PAPER = {
    "procurement": {"baseline": (28.9, 96.8), "gate": (6.8, 13.6), "event": (10.7, 89.5)},
    "cybersecurity": {"baseline": (10.4, 88.8), "gate": (10.4, 88.8), "event": (9.1, 76.4)},
    "finance": {"baseline": (51.0, 98.3), "gate": (1.7, 29.2), "event": (6.9, 13.3)},
    "pooled": {"baseline": (25.3, 93.3), "gate": (7.3, 53.8), "event": (9.0, 64.7)},
}
LABEL = {"baseline": "Typed incremental", "gate": "Source-authority gate", "event": "Bounded event sourcing",
         "ours_baseline": "Typed incremental", "mandate": "One-line mandate", "rebuild": "Rebuild every 3 blocks"}
COLOR = {"baseline": "tab:blue", "gate": "tab:orange", "event": "tab:green", "ours_baseline": "tab:blue", "mandate": "tab:red", "rebuild": "tab:purple"}
# Label offsets (points) and alignment for the pooled panel, chosen so no two labels overlap.
OFFSET = {"baseline": (7, -16, "left"), "ours_baseline": (-9, 6, "right"), "gate": (7, -14, "left"), "event": (-9, -6, "right"),
          "mandate": (-9, -16, "right"), "rebuild": (7, 4, "left")}
ANNOTATION = {"event": "Bounded event\nsourcing"}  # line breaks for the pooled panel only
MARKER = {"baseline": "o", "gate": "s", "event": "s", "ours_baseline": "o", "mandate": "D", "rebuild": "D"}


def latest_completed(pattern: str) -> dict[str, Any] | None:
    found = []
    for d in sorted(glob.glob(pattern)):
        if "superseded" in d:
            continue
        try:
            m = json.load(open(Path(d) / "manifest.json", encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if m.get("status") == "completed":
            found.append(m)
    return found[-1] if found else None


def base_pattern(dom: str, seed: int, w: str) -> str:
    if dom == "procurement":
        return f"results/procurement/*__{'newwriter-s' if w in ADDED else 'seeds-'}{seed}-{w}"
    if seed == SEEDS[dom][0]:
        return f"results/{dom}/*__memtable-{dom}-{w}"
    return f"results/{dom}/*__memtable-s{seed}-{dom}-{w}"


def mandate_pattern(dom: str, seed: int, w: str) -> str:
    return f"results/{dom}/*__mandate-{dom}-{w}" if seed == SEEDS[dom][0] else f"results/{dom}/*__mandate-s{seed}-{dom}-{w}"


def add(acc: dict[str, int], m: dict[str, Any], cond: str) -> bool:
    b = m["summary"]["behavior_by_condition"].get(cond)
    if b is None:
        return False
    acc["us_k"] += b["unauthorized_action"]
    acc["us_n"] += b["unauthorized_n"]
    acc["au_k"] += b["authorized_use"]
    acc["au_n"] += b["authorized_n"]
    return True


def ours() -> tuple[dict[str, dict[str, tuple[float, float]]], list[dict[str, Any]]]:
    """Baseten-population points per domain and pooled, computed from manifests, plus a row table for the CSV."""
    acc: dict[str, dict[str, dict[str, int]]] = {d: {k: {"us_k": 0, "us_n": 0, "au_k": 0, "au_n": 0} for k in ("ours_baseline", "mandate", "rebuild")} for d in DOMAINS + ["pooled"]}
    runs: dict[str, set[str]] = {k: set() for k in ("ours_baseline", "mandate", "rebuild")}
    for dom, seeds in SEEDS.items():
        for seed in seeds:
            for w in W:
                bm = latest_completed(base_pattern(dom, seed, w))
                mm = latest_completed(mandate_pattern(dom, seed, w))
                if bm is None or mm is None or "incremental_typed" not in bm["summary"]["behavior_by_condition"] or "incremental_typed__mandate" not in mm["summary"]["behavior_by_condition"]:
                    continue  # the mandate comparison is paired: only seeds with both runs count for baseline and mandate
                for tgt in (dom, "pooled"):
                    add(acc[tgt]["ours_baseline"], bm, "incremental_typed")
                    add(acc[tgt]["mandate"], mm, "incremental_typed__mandate")
                    rm = bm if "incremental_typed__rebuild3" in bm["summary"]["behavior_by_condition"] else latest_completed(f"results/{dom}/*__rebuild3-s{seed}-{dom}-{w}")
                    if rm is not None and add(acc[tgt]["rebuild"], rm, "incremental_typed__rebuild3"):
                        runs["rebuild"].add(f"{dom}:{seed}:{w}")
                runs["ours_baseline"].add(f"{dom}:{seed}:{w}")
                runs["mandate"].add(f"{dom}:{seed}:{w}")
    pts: dict[str, dict[str, tuple[float, float]]] = {}
    rows = []
    for dom, per in acc.items():
        pts[dom] = {}
        for k, a in per.items():
            if a["us_n"] == 0:
                continue
            us = 100 * a["us_k"] / a["us_n"]
            au = 100 * a["au_k"] / a["au_n"]
            pts[dom][k] = (us, au)
            rows.append({"population": "baseten five writers", "domain": dom, "condition": k, "us": f"{us:.1f}", "au": f"{au:.1f}", "unauthorized_n": a["us_n"], "authorized_n": a["au_n"]})
    for dom, per in PAPER.items():
        for k, (us, au) in per.items():
            rows.append({"population": "paper five writers", "domain": dom, "condition": k, "us": f"{us:.1f}", "au": f"{au:.1f}", "unauthorized_n": "", "authorized_n": ""})
    print("runs per condition:", {k: len(v) for k, v in runs.items()})
    expected = {f"{dom}:{seed}:{writer}" for dom, seeds in SEEDS.items() for seed in seeds for writer in W}
    rebuild_expected = {f"{dom}:{seed}:{writer}" for dom, seeds in SEEDS.items() for seed in (seeds if dom == "procurement" else seeds[:1]) for writer in W}
    if not (expected <= runs["ours_baseline"] and expected <= runs["mandate"] and rebuild_expected <= runs["rebuild"]):
        raise ValueError("Incomplete legacy five-writer population. For the archived seven-writer figure, use analysis.extension_results --figure frontier.")
    return pts, rows


def style(ax: Any) -> None:
    ax.grid(True, color="#DDDDDD", linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def draw(ax: Any, paper: dict[str, tuple[float, float]], mine: dict[str, tuple[float, float]], *, annotate: bool, legend: bool) -> None:
    for fam, points in (("paper", paper), ("ours", mine)):
        hollow = fam == "ours"
        base_key = "baseline" if fam == "paper" else "ours_baseline"
        if base_key not in points:
            continue
        bx, by = points[base_key]
        for k, (x, y) in points.items():
            if k == base_key:
                continue
            ax.plot([bx, x], [by, y], linestyle="--", color="#999999", linewidth=0.9, zorder=1)
        for k, (x, y) in points.items():
            ax.plot(x, y, marker=MARKER[k], markersize=8 if MARKER[k] == "o" else 7, color=COLOR[k],
                    markerfacecolor="white" if hollow else COLOR[k], markeredgewidth=1.6, linestyle="none", zorder=3,
                    label=(LABEL[k] + (" (this branch)" if hollow else "")) if legend else None)
            if annotate:
                dx, dy, ha = OFFSET.get(k, (7, 6, "left"))
                ax.annotate(f"{ANNOTATION.get(k, LABEL[k])}\n({x:.1f}, {y:.1f})", (x, y), textcoords="offset points", xytext=(dx, dy),
                            ha=ha, fontsize=8, color="#222222")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/figures/mitigation_frontier")
    args = ap.parse_args()
    mine, rows = ours()
    plt.rcParams.update({"font.family": "serif", "font.size": 10, "axes.labelsize": 10, "legend.fontsize": 8.5,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.facecolor": "white", "figure.facecolor": "white"})

    # Pooled panel, the paper's layout.
    fig, ax = plt.subplots(figsize=(4.7, 3.5))
    style(ax)
    draw(ax, PAPER["pooled"], mine.get("pooled", {}), annotate=True, legend=False)
    ax.set_xlim(0, 37)
    ax.set_ylim(45, 101)
    ax.set_xlabel("Unauthorized submission (%)\n[lower = more safety]")
    ax.set_ylabel("Authorized use (%)\n[higher = more utility]")
    handles = [
        plt.Line2D([], [], marker="o", color="#444444", linestyle="none", markersize=7, label="Baseline"),
        plt.Line2D([], [], marker="s", color="#444444", linestyle="none", markersize=6, label="Paper's mitigations (filled: paper population)"),
        plt.Line2D([], [], marker="D", color="#444444", markerfacecolor="white", linestyle="none", markersize=6, label="Added mitigations (hollow: Baseten writers)"),
    ]
    ax.legend(handles=handles, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.3), ncol=1)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), dpi=220, bbox_inches="tight")

    # Domain facets.
    fig2, axes = plt.subplots(1, 3, figsize=(9.5, 3.2), sharey=True)
    for ax2, dom in zip(axes, DOMAINS):
        style(ax2)
        draw(ax2, PAPER[dom], mine.get(dom, {}), annotate=False, legend=dom == "procurement")
        ax2.set_title(TITLE[dom], fontsize=10)
        ax2.set_xlabel("Unauthorized submission (%)")
        ax2.set_ylim(0, 102)
        ax2.set_xlim(-1, 56)
    axes[0].set_ylabel("Authorized use (%)")
    h, labels = axes[0].get_legend_handles_labels()
    fig2.legend(h, labels, frameon=False, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.12))
    fig2.tight_layout()
    fig2.savefig(out.with_name(out.name + "_domains").with_suffix(".pdf"), bbox_inches="tight")
    fig2.savefig(out.with_name(out.name + "_domains").with_suffix(".png"), dpi=220, bbox_inches="tight")
    # One population per row: the paper's five writers with the provenance filters above, the five Baseten writers
    # with the writer-side changes below. Same axes in every panel; one baseline per panel; no mixed populations.
    ROWS = (("Paper's five writers, provenance filters", "paper", "baseline", ("gate", "event")),
            ("Five Baseten writers, writer-side changes", "ours", "ours_baseline", ("mandate", "rebuild")))
    fig3, axes3 = plt.subplots(2, 3, figsize=(9.5, 5.6), sharex=True, sharey=True)
    for r, (row_title, fam, base_key, keys) in enumerate(ROWS):
        for c, dom in enumerate(DOMAINS):
            ax3 = axes3[r][c]
            style(ax3)
            pts = PAPER[dom] if fam == "paper" else mine.get(dom, {})
            if base_key in pts:
                bx, by = pts[base_key]
                for k in keys:
                    if k in pts:
                        x, y = pts[k]
                        ax3.annotate("", xy=(x, y), xytext=(bx, by), arrowprops=dict(arrowstyle="->", color="#999999", linewidth=0.9, shrinkA=6, shrinkB=6), zorder=1)
                for k in (base_key, *keys):
                    if k in pts:
                        x, y = pts[k]
                        ax3.plot(x, y, marker=MARKER[k], markersize=8 if MARKER[k] == "o" else 7, color=COLOR[k], linestyle="none", zorder=3,
                                 label=LABEL[k] if (c == 0) else None)
            if r == 0:
                ax3.set_title(TITLE[dom], fontsize=10)
            if r == 1:
                ax3.set_xlabel("Unauthorized submission (%)")
            ax3.set_xlim(-1, 56)
            ax3.set_ylim(0, 102)
        axes3[r][0].set_ylabel(row_title.replace(", ", chr(10)), fontsize=9.5, labelpad=8)
        h3, l3 = axes3[r][0].get_legend_handles_labels()
        axes3[r][2].legend(h3, l3, frameon=False, loc="lower right", fontsize=8.5)
    fig3.supylabel("Authorized use (%)", fontsize=10, x=0.005)
    fig3.tight_layout(rect=(0.03, 0, 1, 1))
    fig3.savefig(out.with_name(out.name + "_rows").with_suffix(".pdf"), bbox_inches="tight")
    fig3.savefig(out.with_name(out.name + "_rows").with_suffix(".png"), dpi=220, bbox_inches="tight")
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)
    print(f"-> {out.with_suffix('.pdf')}, {out.with_name(out.name + '_domains').with_suffix('.pdf')}, {out.with_suffix('.csv')}")


if __name__ == "__main__":
    main()
