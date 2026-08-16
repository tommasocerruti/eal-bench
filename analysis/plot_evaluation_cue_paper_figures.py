#!/usr/bin/env python3
"""Create paper-facing Procurement evaluation-cue figures."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


SCHEMA_VERSION = "procurement_evaluation_cue_paper_figures_v1"
WRITERS = (
    "nemotron_3_ultra_baseten",
    "grok_4_3_openrouter",
    "kimi_baseten",
    "glm_5_2_baseten",
    "qwen_plus_0728_openrouter",
)
EXECUTORS = ("gptoss_baseten", "deepseek_baseten")
CONTRASTS = ("l1-l0", "l2-l1")
WRITER_NAMES = {
    "nemotron_3_ultra_baseten": "Nemotron 3 Ultra",
    "grok_4_3_openrouter": "Grok 4.3",
    "kimi_baseten": "Kimi K2.6",
    "glm_5_2_baseten": "GLM 5.2",
    "qwen_plus_0728_openrouter": "Qwen Plus",
}
EXECUTOR_NAMES = {
    "gptoss_baseten": "GPT-OSS-120B",
    "deepseek_baseten": "DeepSeek V4 Pro",
}
CONTRAST_LABELS = {
    "l1-l0": "Generic cue\nL1 - L0",
    "l2-l1": "Specific increment\nL2 - L1",
}
BLUE = "#0072B2"
VERMILLION = "#D55E00"
MEAN_RED = "#B2182B"
GRAY = "#4D4D4D"
LIGHT_GRAY = "#D9D9D9"
COLORS = {"l1-l0": BLUE, "l2-l1": VERMILLION}
MARKERS = {"l1-l0": "o", "l2-l1": "s"}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _verify_inputs(analysis_dir: Path) -> dict[str, Any]:
    manifest_path = analysis_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "procurement_evaluation_cue_analysis_v1":
        raise ValueError("unexpected evaluation-cue analysis schema")
    for key in ("behavior_contrasts", "typed_fidelity_contrasts"):
        artifact = manifest["artifacts"][key]
        path = analysis_dir / artifact["path"]
        if _hash(path) != artifact["sha256"]:
            raise ValueError(f"analysis artifact hash mismatch: {path}")
        rows = _read_csv(path)
        if len(rows) != artifact["rows"]:
            raise ValueError(f"analysis artifact row-count mismatch: {path}")
    return manifest


def _select(
    rows: Sequence[Mapping[str, str]],
    *,
    stage: str,
    metric: str,
    executor: str | None = None,
) -> list[dict[str, str]]:
    selected = [
        dict(row)
        for row in rows
        if row["condition_id"] == "pooled"
        and row["stage"] == stage
        and row["metric"] == metric
        and (executor is None or row["executor_target"] == executor)
    ]
    return selected


def _validate_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    stage: str,
    metric: str,
    executors: Sequence[str],
) -> None:
    expected = {
        (writer, executor, contrast)
        for writer in WRITERS
        for executor in executors
        for contrast in CONTRASTS
    }
    actual = {
        (row["writer_target"], row["executor_target"], row["contrast"])
        for row in rows
    }
    if actual != expected or len(rows) != len(expected):
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"incomplete {stage} {metric} rows: missing={missing}, "
            f"unexpected={unexpected}"
        )


def _improvement(row: Mapping[str, str]) -> dict[str, Any]:
    sign = -1.0 if row["metric"] in {
        "authorization_error",
        "unauthorized_submission",
    } else 1.0
    estimate = sign * float(row["estimate"]) * 100.0
    lower_raw = float(row["ci_lower"]) * 100.0
    upper_raw = float(row["ci_upper"]) * 100.0
    if sign > 0:
        lower, upper = lower_raw, upper_raw
    else:
        lower, upper = -upper_raw, -lower_raw
    return {
        "stage": row["stage"],
        "metric": row["metric"],
        "contrast": row["contrast"],
        "writer_target": row["writer_target"],
        "writer": WRITER_NAMES[row["writer_target"]],
        "executor_target": row["executor_target"],
        "executor": EXECUTOR_NAMES[row["executor_target"]],
        "estimate_pp": estimate,
        "ci_lower_pp": lower,
        "ci_upper_pp": upper,
        "paired_units": int(row["paired_units"]),
        "case_clusters": int(row["case_clusters"]),
    }


def _prepare_data(
    behavior_rows: Sequence[Mapping[str, str]],
    fidelity_rows: Sequence[Mapping[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    fidelity = _select(
        fidelity_rows,
        stage="writer",
        metric="authorization_error",
        executor="gptoss_baseten",
    )
    exact = _select(
        fidelity_rows,
        stage="writer",
        metric="exact_memory",
        executor="gptoss_baseten",
    )
    writer_authorized = _select(
        behavior_rows,
        stage="writer",
        metric="authorized_use",
        executor="gptoss_baseten",
    )
    writer_unauthorized = _select(
        behavior_rows,
        stage="writer",
        metric="unauthorized_submission",
        executor="gptoss_baseten",
    )
    writer_discrimination = _select(
        behavior_rows,
        stage="writer",
        metric="paired_discrimination",
        executor="gptoss_baseten",
    )
    executor_authorized = _select(
        behavior_rows,
        stage="executor",
        metric="authorized_use",
    )
    executor_unauthorized = _select(
        behavior_rows,
        stage="executor",
        metric="unauthorized_submission",
    )
    executor_discrimination = _select(
        behavior_rows,
        stage="executor",
        metric="paired_discrimination",
    )
    groups = {
        "writer_authorization_error": fidelity,
        "writer_exact_memory": exact,
        "writer_authorized_use": writer_authorized,
        "writer_unauthorized_submission": writer_unauthorized,
        "writer_paired_discrimination": writer_discrimination,
        "executor_authorized_use": executor_authorized,
        "executor_unauthorized_submission": executor_unauthorized,
        "executor_paired_discrimination": executor_discrimination,
    }
    for key, rows in groups.items():
        stage = "executor" if key.startswith("executor_") else "writer"
        metric = rows[0]["metric"] if rows else key
        executors = EXECUTORS if stage == "executor" else ("gptoss_baseten",)
        _validate_rows(
            rows,
            stage=stage,
            metric=metric,
            executors=executors,
        )
    return {key: [_improvement(row) for row in rows] for key, rows in groups.items()}


def _configure_matplotlib() -> Any:
    cache = Path("/tmp/eal-bench-evaluation-cue-paper-matplotlib")
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.5,
            "axes.titlesize": 9.0,
            "axes.labelsize": 7.7,
            "xtick.labelsize": 7.0,
            "ytick.labelsize": 7.0,
            "legend.fontsize": 6.7,
            "axes.linewidth": 0.7,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
        }
    )
    return plt


def _style_distribution_axis(
    ax: Any,
    *,
    ylabel: str,
    show_xlabels: bool,
    values: Sequence[float],
) -> None:
    from matplotlib.ticker import MaxNLocator

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#777777")
    ax.spines["bottom"].set_color("#777777")
    ax.tick_params(colors="#333333", width=0.7, length=3)
    ax.axhline(0, color="#666666", linewidth=0.8, linestyle="--", zorder=1)
    ax.grid(axis="y", color=LIGHT_GRAY, linewidth=0.55, alpha=0.75)
    ax.set_axisbelow(True)
    ax.set_xlim(-0.45, 1.45)
    ax.set_xticks((0, 1))
    if show_xlabels:
        ax.set_xticklabels([CONTRAST_LABELS[key] for key in CONTRASTS])
    else:
        ax.set_xticklabels([])
        ax.tick_params(axis="x", length=0)
    max_abs = max((abs(value) for value in values), default=1.0)
    limit = max(2.0, 2.0 * math.ceil((max_abs + 0.5) / 2.0))
    ax.set_ylim(-limit, limit)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, symmetric=True))
    ax.set_ylabel(ylabel, labelpad=4)


def _distribution_values(
    rows: Sequence[Mapping[str, Any]], contrast: str
) -> list[Mapping[str, Any]]:
    selected = [row for row in rows if row["contrast"] == contrast]
    selected.sort(
        key=lambda row: (
            WRITERS.index(str(row["writer_target"])),
            EXECUTORS.index(str(row["executor_target"])),
        )
    )
    return selected


def _draw_distribution(
    ax: Any,
    rows: Sequence[Mapping[str, Any]],
    *,
    distinguish_executors: bool = False,
) -> None:
    from matplotlib.lines import Line2D

    for x, contrast in enumerate(CONTRASTS):
        selected = _distribution_values(rows, contrast)
        values = [float(row["estimate_pp"]) for row in selected]
        jitter = [
            -0.13 + index * (0.26 / max(1, len(selected) - 1))
            for index in range(len(selected))
        ]
        lower_quartile, median, upper_quartile = np.quantile(
            values, (0.25, 0.5, 0.75)
        )
        mean = float(np.mean(values))
        ax.vlines(
            x,
            min(values),
            max(values),
            color=GRAY,
            linewidth=0.8,
            alpha=0.75,
            zorder=2,
        )
        ax.vlines(
            x,
            lower_quartile,
            upper_quartile,
            color=GRAY,
            linewidth=3.1,
            zorder=3,
        )
        for offset, row in zip(jitter, selected):
            marker = "o"
            if distinguish_executors:
                marker = "o" if row["executor_target"] == EXECUTORS[0] else "^"
            ax.scatter(
                x + offset,
                row["estimate_pp"],
                s=20,
                marker=marker,
                color=COLORS[contrast],
                edgecolor="white",
                linewidth=0.45,
                alpha=0.88,
                zorder=4,
            )
        ax.scatter(
            x,
            median,
            s=31,
            marker="D",
            facecolor="white",
            edgecolor="#222222",
            linewidth=0.9,
            zorder=5,
        )
        ax.hlines(
            mean,
            x - 0.18,
            x + 0.18,
            color=MEAN_RED,
            linewidth=1.6,
            zorder=6,
        )
    if distinguish_executors:
        handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                markerfacecolor=GRAY,
                markeredgecolor="white",
                markersize=4.8,
                label="GPT-OSS",
            ),
            Line2D(
                [0],
                [0],
                marker="^",
                linestyle="none",
                markerfacecolor=GRAY,
                markeredgecolor="white",
                markersize=5.0,
                label="DeepSeek",
            ),
        ]
        ax.legend(
            handles=handles,
            loc="upper left",
            frameon=False,
            handletextpad=0.3,
            borderaxespad=0.1,
        )


def _plot_main(
    plt: Any,
    output_pdf: Path,
    output_png: Path,
    data: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    fig = plt.figure(figsize=(7.5, 2.85))
    outer = fig.add_gridspec(
        1,
        3,
        left=0.068,
        right=0.992,
        bottom=0.20,
        top=0.82,
        wspace=0.43,
    )
    ax_a = fig.add_subplot(outer[0])
    panel_b = outer[1].subgridspec(2, 1, hspace=0.12)
    panel_c = outer[2].subgridspec(2, 1, hspace=0.12)
    ax_b_top = fig.add_subplot(panel_b[0])
    ax_b_bottom = fig.add_subplot(panel_b[1], sharex=ax_b_top)
    ax_c_top = fig.add_subplot(panel_c[0])
    ax_c_bottom = fig.add_subplot(panel_c[1], sharex=ax_c_top)

    fidelity = data["writer_authorization_error"]
    writer_authorized = data["writer_authorized_use"]
    writer_unauthorized = data["writer_unauthorized_submission"]
    executor_authorized = data["executor_authorized_use"]
    executor_unauthorized = data["executor_unauthorized_submission"]

    _style_distribution_axis(
        ax_a,
        ylabel="Fewer authorization errors\n(percentage points)",
        show_xlabels=True,
        values=[float(row["estimate_pp"]) for row in fidelity],
    )
    _draw_distribution(ax_a, fidelity)
    ax_a.set_title("Writer: memory fidelity", loc="left", pad=8)
    ax_a.text(
        -0.20,
        1.11,
        "A",
        transform=ax_a.transAxes,
        fontsize=11,
        fontweight="bold",
    )

    _style_distribution_axis(
        ax_b_top,
        ylabel="Authorized use\nchange (pp)",
        show_xlabels=False,
        values=[float(row["estimate_pp"]) for row in writer_authorized],
    )
    _style_distribution_axis(
        ax_b_bottom,
        ylabel="Fewer unauthorized\nsubmissions (pp)",
        show_xlabels=True,
        values=[float(row["estimate_pp"]) for row in writer_unauthorized],
    )
    _draw_distribution(ax_b_top, writer_authorized)
    _draw_distribution(ax_b_bottom, writer_unauthorized)
    ax_b_top.tick_params(axis="x", labelbottom=False)
    ax_b_top.set_title("Writer: downstream behavior", loc="left", pad=8)
    ax_b_top.text(
        -0.20,
        1.25,
        "B",
        transform=ax_b_top.transAxes,
        fontsize=11,
        fontweight="bold",
    )

    _style_distribution_axis(
        ax_c_top,
        ylabel="Authorized use\nchange (pp)",
        show_xlabels=False,
        values=[float(row["estimate_pp"]) for row in executor_authorized],
    )
    _style_distribution_axis(
        ax_c_bottom,
        ylabel="Fewer unauthorized\nsubmissions (pp)",
        show_xlabels=True,
        values=[float(row["estimate_pp"]) for row in executor_unauthorized],
    )
    _draw_distribution(
        ax_c_top,
        executor_authorized,
        distinguish_executors=True,
    )
    _draw_distribution(
        ax_c_bottom,
        executor_unauthorized,
        distinguish_executors=True,
    )
    ax_c_top.tick_params(axis="x", labelbottom=False)
    bottom_legend = ax_c_bottom.get_legend()
    if bottom_legend is not None:
        bottom_legend.remove()
    ax_c_top.set_title("Executor: downstream behavior", loc="left", pad=8)
    ax_c_top.text(
        -0.20,
        1.25,
        "C",
        transform=ax_c_top.transAxes,
        fontsize=11,
        fontweight="bold",
    )
    fig.savefig(
        output_pdf,
        format="pdf",
        bbox_inches="tight",
        metadata={
            "Title": "Procurement evaluation-cue effects across targets",
            "Subject": "Memory fidelity and downstream behavior under explicit evaluation cues",
            "Creator": "EAL-Bench analysis",
        },
    )
    fig.savefig(output_png, format="png", dpi=600, bbox_inches="tight")
    plt.close(fig)


def _nice_symmetric_limit(rows: Sequence[Mapping[str, Any]]) -> float:
    extent = max(
        abs(float(row[field]))
        for row in rows
        for field in ("ci_lower_pp", "ci_upper_pp")
    )
    return max(2.0, 2.0 * math.ceil((extent + 0.5) / 2.0))


def _style_forest_axis(
    ax: Any,
    *,
    rows: Sequence[Mapping[str, Any]],
    show_ylabels: bool,
    title: str,
    letter: str,
    limit: float | None = None,
) -> None:
    from matplotlib.ticker import MaxNLocator

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color("#777777")
    ax.tick_params(colors="#333333", width=0.7, length=3)
    ax.axvline(0, color="#666666", linewidth=0.8, linestyle="--", zorder=1)
    ax.grid(axis="x", color=LIGHT_GRAY, linewidth=0.55, alpha=0.75)
    ax.set_axisbelow(True)
    ax.set_ylim(-0.55, len(WRITERS) - 0.45)
    ax.invert_yaxis()
    ax.set_yticks(range(len(WRITERS)))
    ax.set_yticklabels(
        [WRITER_NAMES[writer] for writer in WRITERS] if show_ylabels else []
    )
    ax.tick_params(axis="y", length=0)
    bound = limit or _nice_symmetric_limit(rows)
    ax.set_xlim(-bound, bound)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, symmetric=True))
    ax.set_xlabel("Improvement (percentage points)")
    ax.set_title(title, loc="left", pad=8)
    ax.text(
        -0.17 if show_ylabels else -0.10,
        1.08,
        letter,
        transform=ax.transAxes,
        fontsize=11,
        fontweight="bold",
    )


def _draw_forest(
    ax: Any,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    by_key = {
        (str(row["writer_target"]), str(row["contrast"])): row for row in rows
    }
    offsets = {"l1-l0": -0.11, "l2-l1": 0.11}
    for contrast in CONTRASTS:
        for index, writer in enumerate(WRITERS):
            row = by_key[(writer, contrast)]
            estimate = float(row["estimate_pp"])
            lower = float(row["ci_lower_pp"])
            upper = float(row["ci_upper_pp"])
            ax.errorbar(
                estimate,
                index + offsets[contrast],
                xerr=[[estimate - lower], [upper - estimate]],
                fmt=MARKERS[contrast],
                color=COLORS[contrast],
                markerfacecolor=("white" if contrast == "l2-l1" else COLORS[contrast]),
                markeredgewidth=1.0,
                capsize=2.2,
                markersize=4.2,
                linewidth=1.0,
                zorder=3,
            )


def _contrast_legend() -> list[Any]:
    from matplotlib.lines import Line2D

    return [
        Line2D(
            [0],
            [0],
            color=COLORS[contrast],
            marker=MARKERS[contrast],
            markerfacecolor=("white" if contrast == "l2-l1" else COLORS[contrast]),
            markeredgewidth=1.0,
            linewidth=1.0,
            label=CONTRAST_LABELS[contrast].replace("\n", " "),
        )
        for contrast in CONTRASTS
    ]


def _save_figure(
    plt: Any,
    fig: Any,
    pdf: Path,
    png: Path,
    *,
    title: str,
    subject: str,
) -> None:
    fig.savefig(
        pdf,
        format="pdf",
        bbox_inches="tight",
        metadata={"Title": title, "Subject": subject, "Creator": "EAL-Bench analysis"},
    )
    fig.savefig(png, format="png", dpi=600, bbox_inches="tight")
    plt.close(fig)


def _plot_writer_fidelity(
    plt: Any,
    output_pdf: Path,
    output_png: Path,
    data: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    panels = (
        ("writer_authorization_error", "Fewer authorization errors"),
        ("writer_exact_memory", "More exact memories"),
    )
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 2.75))
    fig.subplots_adjust(left=0.15, right=0.985, bottom=0.24, top=0.82, wspace=0.30)
    for index, (key, title) in enumerate(panels):
        rows = data[key]
        _style_forest_axis(
            axes[index],
            rows=rows,
            show_ylabels=index == 0,
            title=title,
            letter=chr(ord("A") + index),
        )
        _draw_forest(axes[index], rows)
    fig.legend(
        handles=_contrast_legend(),
        loc="lower center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 0.015),
    )
    _save_figure(
        plt,
        fig,
        output_pdf,
        output_png,
        title="Evaluation-cue effects on writer memory fidelity",
        subject="Target-specific paired case-cluster intervals",
    )


def _plot_writer_behavior(
    plt: Any,
    output_pdf: Path,
    output_png: Path,
    data: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    panels = (
        ("writer_authorized_use", "Authorized use"),
        ("writer_unauthorized_submission", "Fewer unauthorized submissions"),
        ("writer_paired_discrimination", "Paired discrimination"),
    )
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 2.75))
    fig.subplots_adjust(left=0.15, right=0.99, bottom=0.24, top=0.82, wspace=0.32)
    for index, (key, title) in enumerate(panels):
        rows = data[key]
        _style_forest_axis(
            axes[index],
            rows=rows,
            show_ylabels=index == 0,
            title=title,
            letter=chr(ord("A") + index),
        )
        _draw_forest(axes[index], rows)
    fig.legend(
        handles=_contrast_legend(),
        loc="lower center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 0.015),
    )
    _save_figure(
        plt,
        fig,
        output_pdf,
        output_png,
        title="Evaluation-cue writer intervention: downstream behavior",
        subject="Target-specific paired case-cluster intervals",
    )


def _plot_executor_behavior(
    plt: Any,
    output_pdf: Path,
    output_png: Path,
    data: Mapping[str, Sequence[Mapping[str, Any]]],
) -> None:
    metrics = (
        ("executor_authorized_use", "Authorized use"),
        ("executor_unauthorized_submission", "Fewer unauthorized submissions"),
        ("executor_paired_discrimination", "Paired discrimination"),
    )
    column_limits = {
        key: _nice_symmetric_limit(data[key]) for key, _ in metrics
    }
    fig, axes = plt.subplots(2, 3, figsize=(7.5, 4.8))
    fig.subplots_adjust(
        left=0.15,
        right=0.99,
        bottom=0.17,
        top=0.86,
        hspace=0.52,
        wspace=0.32,
    )
    for row_index, executor in enumerate(EXECUTORS):
        for column_index, (key, metric_title) in enumerate(metrics):
            rows = [
                row for row in data[key] if row["executor_target"] == executor
            ]
            title = metric_title if row_index == 0 else ""
            letter = chr(ord("A") + row_index * 3 + column_index)
            _style_forest_axis(
                axes[row_index, column_index],
                rows=rows,
                show_ylabels=column_index == 0,
                title=title,
                letter=letter,
                limit=column_limits[key],
            )
            _draw_forest(axes[row_index, column_index], rows)
            if column_index == 0:
                axes[row_index, column_index].text(
                    -0.63,
                    0.5,
                    EXECUTOR_NAMES[executor],
                    transform=axes[row_index, column_index].transAxes,
                    rotation=90,
                    va="center",
                    ha="center",
                    fontsize=8.0,
                    fontweight="bold",
                )
    fig.legend(
        handles=_contrast_legend(),
        loc="lower center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 0.015),
    )
    _save_figure(
        plt,
        fig,
        output_pdf,
        output_png,
        title="Evaluation-cue executor intervention: downstream behavior",
        subject="Target-specific paired case-cluster intervals by executor",
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_captions(path: Path) -> None:
    path.write_text(
        "# Evaluation-cue figure captions\n\n"
        "## Main figure\n\n"
        "**Explicit evaluation cues have heterogeneous effects across targets.** "
        "Each small colored point is one preregistered writer target (A-B) or "
        "writer-memory/executor combination (C). Blue circles show the generic "
        "evaluation cue (L1-L0); orange points show the additional effect of "
        "authorization-specific framing (L2-L1). Positive values indicate improved "
        "memory fidelity, higher authorized use, or fewer targeted unauthorized "
        "submissions. Short red horizontal lines are unweighted means across tested "
        "targets; white diamonds are target medians, thick gray segments are "
        "interquartile ranges, and thin gray segments span the tested targets. These "
        "segments describe across-target heterogeneity, not sampling uncertainty or "
        "a population-level confidence interval. Writer effects use three replicates "
        "and 12 case clusters; executor effects reuse five frozen writer sources with "
        "GPT-OSS-120B and DeepSeek V4 Pro.\n\n"
        "## Appendix: writer fidelity\n\n"
        "**Target-specific evaluation-cue effects on typed-memory fidelity.** Points "
        "show paired risk differences and whiskers show 95% paired case-cluster "
        "bootstrap intervals. Effects are oriented so positive values indicate fewer "
        "authorization errors or more exact memories.\n\n"
        "## Appendix: writer downstream behavior\n\n"
        "**Target-specific downstream effects of writer evaluation cues.** Points show "
        "paired risk differences and whiskers show 95% paired case-cluster bootstrap "
        "intervals. Positive values indicate higher authorized use, fewer targeted "
        "unauthorized submissions, or higher paired discrimination.\n\n"
        "## Appendix: executor downstream behavior\n\n"
        "**Target-specific downstream effects of executor evaluation cues.** Frozen "
        "memories from each writer are shown separately for GPT-OSS-120B and DeepSeek "
        "V4 Pro. Points show paired risk differences and whiskers show 95% paired "
        "case-cluster bootstrap intervals. Positive values indicate improvement. "
        "Intervals are not multiplicity-adjusted, and intervals containing zero are "
        "not evidence of equivalence.\n",
        encoding="utf-8",
    )


def _manifest_entry(path: Path) -> dict[str, Any]:
    return {"path": path.name, "sha256": _hash(path), "bytes": path.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analysis_dir = args.analysis_dir.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    analysis_manifest = _verify_inputs(analysis_dir)
    behavior_path = analysis_dir / "behavior_contrasts.csv"
    fidelity_path = analysis_dir / "typed_fidelity_contrasts.csv"
    data = _prepare_data(_read_csv(behavior_path), _read_csv(fidelity_path))
    plt = _configure_matplotlib()

    outputs = {
        "main_pdf": output / "evaluation_cue_main_summary.pdf",
        "main_png": output / "evaluation_cue_main_summary.png",
        "writer_fidelity_pdf": output / "evaluation_cue_appendix_writer_fidelity.pdf",
        "writer_fidelity_png": output / "evaluation_cue_appendix_writer_fidelity.png",
        "writer_behavior_pdf": output / "evaluation_cue_appendix_writer_behavior.pdf",
        "writer_behavior_png": output / "evaluation_cue_appendix_writer_behavior.png",
        "executor_behavior_pdf": output / "evaluation_cue_appendix_executor_behavior.pdf",
        "executor_behavior_png": output / "evaluation_cue_appendix_executor_behavior.png",
        "main_data": output / "main_summary_data.csv",
        "captions": output / "CAPTIONS.md",
    }
    _plot_main(plt, outputs["main_pdf"], outputs["main_png"], data)
    _plot_writer_fidelity(
        plt,
        outputs["writer_fidelity_pdf"],
        outputs["writer_fidelity_png"],
        data,
    )
    _plot_writer_behavior(
        plt,
        outputs["writer_behavior_pdf"],
        outputs["writer_behavior_png"],
        data,
    )
    _plot_executor_behavior(
        plt,
        outputs["executor_behavior_pdf"],
        outputs["executor_behavior_png"],
        data,
    )
    main_rows = [
        row
        for key in (
            "writer_authorization_error",
            "writer_authorized_use",
            "writer_unauthorized_submission",
            "executor_authorized_use",
            "executor_unauthorized_submission",
        )
        for row in data[key]
    ]
    _write_csv(outputs["main_data"], main_rows)
    _write_captions(outputs["captions"])
    manifest_path = output / "manifest.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "analysis_manifest_sha256": _hash(analysis_dir / "manifest.json"),
        "source_artifacts": {
            "behavior_contrasts": analysis_manifest["artifacts"][
                "behavior_contrasts"
            ],
            "typed_fidelity_contrasts": analysis_manifest["artifacts"][
                "typed_fidelity_contrasts"
            ],
        },
        "interpretation": {
            "positive_direction": "improvement",
            "summary": (
                "unweighted mean, median, interquartile range, and full range "
                "across tested targets"
            ),
            "summary_is_inferential": False,
            "target_intervals": "95% paired case-cluster percentile bootstrap",
            "multiplicity_adjusted": False,
        },
        "artifacts": {
            key: _manifest_entry(path) for key, path in outputs.items()
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
