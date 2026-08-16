#!/usr/bin/env python3
"""Create the main-paper Procurement writer-TTC figure from frozen analyses."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter, NullLocator


SCHEMA_VERSION = "procurement_writer_ttc_figure_v4"
K_VALUES = (1, 2, 4, 8)
BOOTSTRAP_SEED = 20260814
BOOTSTRAP_RESAMPLES = 10_000
BLUE = "#0072B2"
VERMILLION = "#D55E00"
GRAY = "#4D4D4D"
LIGHT_GRAY = "#D9D9D9"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _rows_by_k(
    rows: Sequence[Mapping[str, str]], condition: str
) -> dict[int, Mapping[str, str]]:
    selected = {
        int(row["k"]): row for row in rows if row.get("condition_id") == condition
    }
    if set(selected) != set(K_VALUES):
        raise ValueError(f"incomplete k levels for {condition}: {sorted(selected)}")
    return selected


def _selection_by_k(
    rows: Sequence[Mapping[str, str]],
) -> dict[int, Mapping[str, str]]:
    selected = {int(row["k"]): row for row in rows}
    if set(selected) != set(K_VALUES):
        raise ValueError(f"incomplete selection levels: {sorted(selected)}")
    return selected


def _deepseek_selection_by_k(
    rows: Sequence[Mapping[str, str]],
    self_selection: Mapping[int, Mapping[str, str]],
) -> dict[int, Mapping[str, str]]:
    selected = {
        int(row["k"]): row
        for row in rows
        if row.get("condition_id") == "typed_pooled"
        and row.get("method") == "deepseek_review"
    }
    if set(selected) != {2, 4, 8}:
        raise ValueError(
            f"incomplete DeepSeek selection levels: {sorted(selected)}"
        )
    selected[1] = {
        "k": "1",
        "condition_id": "typed_pooled",
        "method": "single_candidate_identity",
        "typed_pools": self_selection[1]["typed_pools"],
        "selected_exact_rate": self_selection[1][
            "reviewer_selected_full_fidelity_exact_rate"
        ],
    }
    return selected


def _deepseek_writer_rows(
    independent_rows: Sequence[Mapping[str, str]],
    self_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    selected = [
        dict(row)
        for row in independent_rows
        if row.get("condition_id") == "typed_pooled"
        and row.get("method") == "deepseek_review"
    ]
    selected.extend(
        {
            "writer_target": row["writer_target"],
            "k": "1",
            "typed_pools": row["typed_pools"],
            "selected_exact_rate": row[
                "reviewer_selected_full_fidelity_exact_rate"
            ],
        }
        for row in self_rows
        if int(row["k"]) == 1
    )
    return selected


def _verify_manifest_files(directory: Path, manifest: Mapping[str, Any]) -> None:
    for name, metadata in manifest["files"].items():
        path = directory / name
        if _hash(path) != metadata["sha256"]:
            raise ValueError(f"analysis artifact hash mismatch: {path}")


def _verify_analysis_bundles(
    analysis_dir: Path,
    independent_dir: Path,
    audit_path: Path,
) -> dict[str, Any]:
    manifest_path = analysis_dir / "manifest.json"
    independent_manifest_path = independent_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    independent_manifest = json.loads(
        independent_manifest_path.read_text(encoding="utf-8")
    )
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "procurement_writer_ttc_multi_v2":
        raise ValueError("unexpected five-writer analysis schema")
    if (
        independent_manifest.get("schema_version")
        != "procurement_writer_ttc_independent_review_v2"
    ):
        raise ValueError("unexpected independent-review analysis schema")
    if audit.get("status") != "completed":
        raise ValueError("final experiment audit is not completed")
    if tuple(audit.get("levels", ())) != K_VALUES:
        raise ValueError("final audit does not cover k=1,2,4,8")
    expected_manifest_hash = audit["analysis"][
        "five_writer_scaling_manifest_sha256"
    ]
    if _hash(manifest_path) != expected_manifest_hash:
        raise ValueError("analysis manifest does not match final audit")
    expected_independent_hash = audit["analysis"][
        "independent_review_manifest_sha256"
    ]
    if _hash(independent_manifest_path) != expected_independent_hash:
        raise ValueError("independent-review manifest does not match final audit")
    _verify_manifest_files(analysis_dir, manifest)
    _verify_manifest_files(independent_dir, independent_manifest)
    return {
        "manifest": manifest,
        "independent_manifest": independent_manifest,
        "audit": audit,
    }


def _rounded_check(
    name: str,
    actual: Sequence[float],
    expected: Sequence[float],
    *,
    multiplier: float = 100.0,
    digits: int = 1,
) -> dict[str, Any]:
    actual_rounded = [round(value * multiplier, digits) for value in actual]
    expected_values = list(expected)
    match = actual_rounded == expected_values
    if not match:
        raise ValueError(
            f"authoritative value discrepancy for {name}: "
            f"expected {expected_values}, got {actual_rounded}"
        )
    return {
        "metric": name,
        "actual": list(actual),
        "actual_rounded": actual_rounded,
        "expected_rounded": expected_values,
        "match": match,
    }


def _bootstrap_intervals(
    rows: Sequence[Mapping[str, str]],
    value_field: str,
    weight_field: str,
    bootstrap_indices: np.ndarray,
) -> dict[int, tuple[float, float]]:
    writers = sorted({row["writer_target"] for row in rows})
    if len(writers) != 5:
        raise ValueError(f"expected five writer clusters, got {writers}")
    by_key = {
        (row["writer_target"], int(row["k"])): row
        for row in rows
    }
    if len(by_key) != len(writers) * len(K_VALUES):
        raise ValueError(f"incomplete writer-level rows for {value_field}")
    numerators = np.array(
        [
            [
                float(by_key[(writer, k)][value_field])
                * float(by_key[(writer, k)][weight_field])
                for k in K_VALUES
            ]
            for writer in writers
        ]
    )
    denominators = np.array(
        [
            [float(by_key[(writer, k)][weight_field]) for k in K_VALUES]
            for writer in writers
        ]
    )
    intervals = {}
    for index, k in enumerate(K_VALUES):
        estimates = (
            numerators[bootstrap_indices, index].sum(axis=1)
            / denominators[bootstrap_indices, index].sum(axis=1)
        )
        low, high = np.quantile(estimates, (0.025, 0.975))
        intervals[k] = (float(low), float(high))
    return intervals


def _draw_intervals(
    ax: Any,
    values: Sequence[float],
    intervals: Mapping[int, tuple[float, float]],
    color: str,
) -> None:
    lower = [value - intervals[k][0] * 100 for value, k in zip(values, K_VALUES)]
    upper = [intervals[k][1] * 100 - value for value, k in zip(values, K_VALUES)]
    ax.errorbar(
        K_VALUES,
        values,
        yerr=np.array([lower, upper]),
        fmt="none",
        ecolor=color,
        elinewidth=0.8,
        capsize=2.2,
        capthick=0.8,
        alpha=0.65,
        zorder=3,
    )


def _style_axis(ax: Any, *, show_xlabel: bool = True) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#777777")
    ax.spines["bottom"].set_color("#777777")
    ax.tick_params(colors="#333333", width=0.7, length=3)
    ax.grid(axis="y", color=LIGHT_GRAY, linewidth=0.55, alpha=0.75)
    ax.set_axisbelow(True)
    ax.set_xscale("log", base=2)
    ax.set_xlim(0.85, 9.0)
    ax.set_xticks(K_VALUES, [f"k={k}" for k in K_VALUES])
    ax.xaxis.set_minor_locator(NullLocator())
    if show_xlabel:
        ax.set_xlabel("Writer candidates", labelpad=4)
    else:
        ax.tick_params(axis="x", labelbottom=False)


def _plot(
    output_pdf: Path,
    output_png: Path,
    behavior: Mapping[int, Mapping[str, str]],
    selection: Mapping[int, Mapping[str, str]],
    deepseek_selection: Mapping[int, Mapping[str, str]],
    mechanisms: Mapping[int, Mapping[str, str]],
    intervals: Mapping[str, Mapping[int, tuple[float, float]]],
) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.5,
            "axes.titlesize": 9.0,
            "axes.labelsize": 7.7,
            "xtick.labelsize": 7.2,
            "ytick.labelsize": 7.2,
            "legend.fontsize": 6.7,
            "axes.linewidth": 0.7,
            "lines.linewidth": 1.7,
            "lines.markersize": 4.5,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
        }
    )
    fig = plt.figure(figsize=(7.5, 2.85))
    outer = fig.add_gridspec(
        1,
        3,
        left=0.065,
        right=0.985,
        bottom=0.20,
        top=0.82,
        wspace=0.42,
    )
    panel_a = outer[0].subgridspec(2, 1, hspace=0.12)
    ax_a_top = fig.add_subplot(panel_a[0])
    ax_a_bottom = fig.add_subplot(panel_a[1], sharex=ax_a_top)
    ax_b = fig.add_subplot(outer[1])
    ax_c = fig.add_subplot(outer[2])
    percent = FuncFormatter(lambda value, _: f"{value:.0f}%")

    # Panel A: stacked axes avoid slope comparisons across dual scales.
    _style_axis(ax_a_top, show_xlabel=False)
    _style_axis(ax_a_bottom)
    ax_a_top.set_title("Downstream behavior", loc="left", pad=8)
    ax_a_top.text(
        -0.20,
        1.25,
        "A",
        transform=ax_a_top.transAxes,
        fontsize=11,
        fontweight="bold",
    )
    authorized = [float(behavior[k]["authorized_use_rate"]) * 100 for k in K_VALUES]
    targeted = [
        float(behavior[k]["targeted_unauthorized_submission_rate"]) * 100
        for k in K_VALUES
    ]
    ax_a_top.plot(
        K_VALUES,
        authorized,
        color=BLUE,
        marker="o",
        linestyle="-",
        label="Authorized use",
        zorder=4,
    )
    _draw_intervals(ax_a_top, authorized, intervals["Authorized use"], BLUE)
    ax_a_top.set_ylim(88, 101)
    ax_a_top.set_yticks((90, 95, 100))
    ax_a_top.yaxis.set_major_formatter(percent)
    ax_a_top.set_ylabel("Authorized\nuse", labelpad=4)

    ax_a_bottom.plot(
        K_VALUES,
        targeted,
        color=VERMILLION,
        marker="s",
        markerfacecolor="white",
        markeredgewidth=1.1,
        linestyle="--",
        label="Targeted unauthorized submission",
        zorder=4,
    )
    _draw_intervals(
        ax_a_bottom,
        targeted,
        intervals["Targeted unauthorized submission"],
        VERMILLION,
    )
    ax_a_bottom.set_ylim(0, 20)
    ax_a_bottom.set_yticks((0, 10, 20))
    ax_a_bottom.yaxis.set_major_formatter(percent)
    ax_a_bottom.set_ylabel("Unauthorized\nsubmission", labelpad=4)
    ax_a_bottom.legend(
        loc="upper right",
        frameon=False,
        handlelength=2.6,
        borderaxespad=0.2,
    )

    # Panel B: the shaded band exposes the growing oracle-selection gap.
    ax = ax_b
    _style_axis(ax)
    ax.set_title("Generation vs. selection", loc="left", pad=8)
    ax.text(-0.20, 1.12, "B", transform=ax.transAxes, fontsize=11, fontweight="bold")
    oracle = [
        float(selection[k]["pool_contains_full_fidelity_exact_rate"]) * 100
        for k in K_VALUES
    ]
    self_selected = [
        float(selection[k]["reviewer_selected_full_fidelity_exact_rate"]) * 100
        for k in K_VALUES
    ]
    deepseek_selected = [
        float(deepseek_selection[k]["selected_exact_rate"]) * 100
        for k in K_VALUES
    ]
    ax.plot(
        K_VALUES,
        oracle,
        color=BLUE,
        marker="o",
        linestyle="-",
        label="Oracle-best available",
        zorder=4,
    )
    _draw_intervals(
        ax,
        oracle,
        intervals["Oracle-best exact-memory availability"],
        BLUE,
    )
    ax.plot(
        K_VALUES,
        self_selected,
        color=VERMILLION,
        marker="s",
        markerfacecolor="white",
        markeredgewidth=1.1,
        linestyle="--",
        label="Writer self-review",
        zorder=4,
    )
    _draw_intervals(
        ax,
        self_selected,
        intervals["Writer self-review"],
        VERMILLION,
    )
    ax.plot(
        K_VALUES,
        deepseek_selected,
        color=GRAY,
        marker="^",
        markerfacecolor="white",
        markeredgewidth=1.0,
        linestyle=":",
        label="DeepSeek independent review",
        zorder=4,
    )
    _draw_intervals(
        ax,
        deepseek_selected,
        intervals["DeepSeek independent review"],
        GRAY,
    )
    ax.set_ylim(0, 60)
    ax.set_yticks((0, 20, 40, 60))
    ax.yaxis.set_major_formatter(percent)
    ax.set_ylabel("Exact-memory rate", labelpad=3)
    ax.legend(loc="lower left", frameon=False, handlelength=2.6)
    # Panel C: show only the two plotted mechanism rates.
    ax = ax_c
    _style_axis(ax)
    ax.set_title("Incremental typed mechanism", loc="left", pad=8)
    ax.text(-0.20, 1.12, "C", transform=ax.transAxes, fontsize=11, fontweight="bold")
    introduction = [
        float(mechanisms[k]["error_introduction_rate"]) * 100 for k in K_VALUES
    ]
    final_error = [float(mechanisms[k]["final_error_rate"]) * 100 for k in K_VALUES]
    ax.plot(
        K_VALUES,
        final_error,
        color=BLUE,
        marker="o",
        linestyle="-",
        label="Final-state error",
        zorder=4,
    )
    _draw_intervals(ax, final_error, intervals["Final-state error"], BLUE)
    ax.plot(
        K_VALUES,
        introduction,
        color=VERMILLION,
        marker="s",
        markerfacecolor="white",
        markeredgewidth=1.1,
        linestyle="--",
        label="Error introduction",
        zorder=4,
    )
    _draw_intervals(ax, introduction, intervals["Error introduction"], VERMILLION)
    ax.set_ylim(0, 80)
    ax.set_yticks((0, 20, 40, 60, 80))
    ax.yaxis.set_major_formatter(percent)
    ax.set_ylabel("Error rate")
    ax.legend(loc="center left", bbox_to_anchor=(0.03, 0.54), frameon=False, handlelength=2.6)
    fig.savefig(
        output_pdf,
        format="pdf",
        bbox_inches="tight",
        metadata={
            "Title": "Five-writer Procurement writer-side TTC experiment",
            "Subject": "Behavior, candidate generation and selection, and incremental memory mechanism",
            "Creator": "EAL-Bench analysis",
        },
    )
    fig.savefig(output_png, format="png", dpi=600, bbox_inches="tight")
    plt.close(fig)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis-dir", type=Path, required=True)
    parser.add_argument("--independent-analysis-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analysis_dir = args.analysis_dir.resolve()
    independent_dir = args.independent_analysis_dir.resolve()
    audit_path = args.audit.resolve()
    output = args.output.resolve()
    allowed_existing = {
        "CAPTION.md",
        "README.md",
        "manifest.json",
        "plot_data.csv",
        "procurement_writer_ttc_five_writer.pdf",
        "procurement_writer_ttc_five_writer.png",
        "verification.json",
    }
    if output.exists():
        unexpected = {path.name for path in output.iterdir()} - allowed_existing
        if unexpected:
            raise FileExistsError(
                f"output contains non-figure artifacts: {sorted(unexpected)}"
            )
    _verify_analysis_bundles(analysis_dir, independent_dir, audit_path)

    report_path = analysis_dir / "REPORT.md"
    summary_path = analysis_dir / "summary.json"
    behavior_path = analysis_dir / "pooled_behavior_by_condition.csv"
    selection_path = analysis_dir / "pooled_selection_scaling.csv"
    mechanisms_path = analysis_dir / "pooled_incremental_mechanisms.csv"
    fidelity_path = analysis_dir / "pooled_typed_fidelity_by_condition.csv"
    behavior_writer_path = analysis_dir / "behavior_by_writer_condition.csv"
    selection_writer_path = analysis_dir / "selection_by_writer.csv"
    mechanisms_writer_path = analysis_dir / "incremental_mechanisms_by_writer.csv"
    independent_report_path = independent_dir / "REPORT.md"
    independent_summary_path = independent_dir / "summary.json"
    independent_selection_path = independent_dir / "selection_pooled.csv"
    independent_selection_writer_path = (
        independent_dir / "selection_by_writer_condition.csv"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    independent_summary = json.loads(
        independent_summary_path.read_text(encoding="utf-8")
    )
    behavior = _rows_by_k(_read_csv(behavior_path), "pooled")
    fidelity = _rows_by_k(_read_csv(fidelity_path), "typed_pooled")
    selection = _selection_by_k(_read_csv(selection_path))
    independent_selection_rows = _read_csv(independent_selection_path)
    deepseek_selection = _deepseek_selection_by_k(
        independent_selection_rows,
        selection,
    )
    mechanisms = _selection_by_k(_read_csv(mechanisms_path))
    behavior_writer = [
        row
        for row in _read_csv(behavior_writer_path)
        if row["condition_id"] == "pooled"
    ]
    selection_writer = _read_csv(selection_writer_path)
    deepseek_selection_writer = _deepseek_writer_rows(
        _read_csv(independent_selection_writer_path),
        selection_writer,
    )
    mechanisms_writer = _read_csv(mechanisms_writer_path)
    writer_count = len({row["writer_target"] for row in behavior_writer})
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    bootstrap_indices = rng.integers(
        0,
        writer_count,
        size=(BOOTSTRAP_RESAMPLES, writer_count),
    )
    intervals = {
        "Authorized use": _bootstrap_intervals(
            behavior_writer,
            "authorized_use_rate",
            "authorized_request_count",
            bootstrap_indices,
        ),
        "Targeted unauthorized submission": _bootstrap_intervals(
            behavior_writer,
            "targeted_unauthorized_submission_rate",
            "unauthorized_request_count",
            bootstrap_indices,
        ),
        "Oracle-best exact-memory availability": _bootstrap_intervals(
            selection_writer,
            "pool_contains_full_fidelity_exact_rate",
            "typed_pools",
            bootstrap_indices,
        ),
        "Writer self-review": _bootstrap_intervals(
            selection_writer,
            "reviewer_selected_full_fidelity_exact_rate",
            "typed_pools",
            bootstrap_indices,
        ),
        "DeepSeek independent review": _bootstrap_intervals(
            deepseek_selection_writer,
            "selected_exact_rate",
            "typed_pools",
            bootstrap_indices,
        ),
        "Error introduction": _bootstrap_intervals(
            mechanisms_writer,
            "error_introduction_rate",
            "correct_origin_transitions",
            bootstrap_indices,
        ),
        "Final-state error": _bootstrap_intervals(
            mechanisms_writer,
            "final_error_rate",
            "selected_trajectories",
            bootstrap_indices,
        ),
    }

    # Cross-check the plotting tables against the authoritative summary.
    summary_behavior = {
        int(row["k"]): row
        for row in summary["pooled_behavior"]
        if row["condition_id"] == "pooled"
    }
    summary_fidelity = {
        int(row["k"]): row
        for row in summary["pooled_typed_fidelity"]
        if row["condition_id"] == "typed_pooled"
    }
    summary_selection = {int(row["k"]): row for row in summary["pooled_selection"]}
    summary_mechanisms = {
        int(row["k"]): row for row in summary["pooled_incremental_mechanisms"]
    }
    summary_deepseek = {
        int(row["k"]): row
        for row in independent_summary["selection_pooled"]
        if row["condition_id"] == "typed_pooled"
        and row["method"] == "deepseek_review"
    }
    if set(summary_deepseek) != {2, 4, 8}:
        raise ValueError("independent summary does not cover k=2,4,8")
    for k in K_VALUES:
        for field in (
            "authorized_use_rate",
            "targeted_unauthorized_submission_rate",
            "broader_unsafe_action_rate",
        ):
            if float(behavior[k][field]) != float(summary_behavior[k][field]):
                raise ValueError(f"behavior table/summary mismatch: k={k}, {field}")
        for field in (
            "authorization_error_rate",
            "apparent_authority_rate",
        ):
            if float(fidelity[k][field]) != float(summary_fidelity[k][field]):
                raise ValueError(f"fidelity table/summary mismatch: k={k}, {field}")
        for field in (
            "pool_contains_full_fidelity_exact_rate",
            "reviewer_selected_full_fidelity_exact_rate",
            "mean_full_fidelity_selection_regret",
        ):
            if float(selection[k][field]) != float(summary_selection[k][field]):
                raise ValueError(f"selection table/summary mismatch: k={k}, {field}")
        for field in (
            "error_introduction_rate",
            "error_persistence_rate",
            "self_repair_rate",
            "final_error_rate",
        ):
            if float(mechanisms[k][field]) != float(summary_mechanisms[k][field]):
                raise ValueError(f"mechanism table/summary mismatch: k={k}, {field}")
        if k > 1:
            if float(deepseek_selection[k]["selected_exact_rate"]) != float(
                summary_deepseek[k]["selected_exact_rate"]
            ):
                raise ValueError(
                    f"DeepSeek selection table/summary mismatch: k={k}"
                )
    if float(deepseek_selection[1]["selected_exact_rate"]) != float(
        selection[1]["pool_contains_full_fidelity_exact_rate"]
    ):
        raise ValueError("DeepSeek k=1 identity does not equal the single candidate")

    checks = [
        _rounded_check(
            "Typed authorization error",
            [float(fidelity[k]["authorization_error_rate"]) for k in K_VALUES],
            (26.7, 24.2, 20.8, 18.3),
        ),
        _rounded_check(
            "Typed apparent authority",
            [float(fidelity[k]["apparent_authority_rate"]) for k in K_VALUES],
            (25.8, 24.2, 20.0, 18.3),
        ),
        _rounded_check(
            "Authorized use",
            [float(behavior[k]["authorized_use_rate"]) for k in K_VALUES],
            (94.2, 95.4, 96.5, 95.8),
        ),
        _rounded_check(
            "Targeted unauthorized submission",
            [
                float(behavior[k]["targeted_unauthorized_submission_rate"])
                for k in K_VALUES
            ],
            (13.2, 10.8, 9.2, 8.6),
        ),
        _rounded_check(
            "Broader unsafe action",
            [float(behavior[k]["broader_unsafe_action_rate"]) for k in K_VALUES],
            (7.6, 6.3, 5.4, 5.1),
        ),
        _rounded_check(
            "Oracle-best exact-memory availability",
            [
                float(selection[k]["pool_contains_full_fidelity_exact_rate"])
                for k in K_VALUES
            ],
            (31.7, 44.2, 50.8, 55.0),
        ),
        _rounded_check(
            "Writer self-review",
            [
                float(selection[k]["reviewer_selected_full_fidelity_exact_rate"])
                for k in K_VALUES
            ],
            (31.7, 35.0, 31.7, 26.7),
        ),
        _rounded_check(
            "DeepSeek independent review",
            [
                float(deepseek_selection[k]["selected_exact_rate"])
                for k in K_VALUES
            ],
            (31.7, 35.8, 33.3, 30.0),
        ),
        _rounded_check(
            "Selection regret",
            [
                float(selection[k]["mean_full_fidelity_selection_regret"])
                for k in K_VALUES
            ],
            (0.0, 0.392, 0.683, 0.9),
            multiplier=1.0,
            digits=3,
        ),
        _rounded_check(
            "Review failure",
            [float(selection[k]["reviewer_failure_rate"]) for k in (2, 4, 8)],
            (5.8, 22.5, 2.5),
        ),
        _rounded_check(
            "Incremental typed error introduction",
            [float(mechanisms[k]["error_introduction_rate"]) for k in K_VALUES],
            (15.2, 13.7, 14.0, 12.7),
        ),
        _rounded_check(
            "Incremental typed error persistence",
            [float(mechanisms[k]["error_persistence_rate"]) for k in K_VALUES],
            (100.0, 100.0, 100.0, 100.0),
        ),
        _rounded_check(
            "Incremental typed self-repair",
            [float(mechanisms[k]["self_repair_rate"]) for k in K_VALUES],
            (0.0, 0.0, 0.0, 0.0),
        ),
        _rounded_check(
            "Incremental typed final-state error",
            [float(mechanisms[k]["final_error_rate"]) for k in K_VALUES],
            (63.3, 56.7, 56.7, 51.7),
        ),
    ]

    output.mkdir(parents=True, exist_ok=True)
    plot_rows = []
    for k in K_VALUES:
        plot_rows.extend(
            [
                {
                    "panel": "A",
                    "metric": "Authorized use",
                    "k": k,
                    "value": behavior[k]["authorized_use_rate"],
                    "unit": "proportion",
                    "numerator": round(
                        float(behavior[k]["authorized_use_rate"])
                        * int(behavior[k]["authorized_request_count"])
                    ),
                    "denominator": behavior[k]["authorized_request_count"],
                    "visual_role": "line",
                    "source_file": behavior_path.name,
                    "source_field": "authorized_use_rate",
                },
                {
                    "panel": "A",
                    "metric": "Targeted unauthorized submission",
                    "k": k,
                    "value": behavior[k]["targeted_unauthorized_submission_rate"],
                    "unit": "proportion",
                    "numerator": round(
                        float(behavior[k]["targeted_unauthorized_submission_rate"])
                        * int(behavior[k]["unauthorized_request_count"])
                    ),
                    "denominator": behavior[k]["unauthorized_request_count"],
                    "visual_role": "line",
                    "source_file": behavior_path.name,
                    "source_field": "targeted_unauthorized_submission_rate",
                },
                {
                    "panel": "B",
                    "metric": "Oracle-best exact-memory availability",
                    "k": k,
                    "value": selection[k]["pool_contains_full_fidelity_exact_rate"],
                    "unit": "proportion",
                    "numerator": round(
                        float(selection[k]["pool_contains_full_fidelity_exact_rate"])
                        * int(selection[k]["typed_pools"])
                    ),
                    "denominator": selection[k]["typed_pools"],
                    "visual_role": "line",
                    "source_file": selection_path.name,
                    "source_field": "pool_contains_full_fidelity_exact_rate",
                },
                {
                    "panel": "B",
                    "metric": "Writer self-review",
                    "k": k,
                    "value": selection[k]["reviewer_selected_full_fidelity_exact_rate"],
                    "unit": "proportion",
                    "numerator": round(
                        float(selection[k]["reviewer_selected_full_fidelity_exact_rate"])
                        * int(selection[k]["typed_pools"])
                    ),
                    "denominator": selection[k]["typed_pools"],
                    "visual_role": "line",
                    "source_file": selection_path.name,
                    "source_field": "reviewer_selected_full_fidelity_exact_rate",
                },
                {
                    "panel": "B",
                    "metric": "DeepSeek independent review",
                    "k": k,
                    "value": deepseek_selection[k]["selected_exact_rate"],
                    "unit": "proportion",
                    "numerator": round(
                        float(deepseek_selection[k]["selected_exact_rate"])
                        * int(deepseek_selection[k]["typed_pools"])
                    ),
                    "denominator": deepseek_selection[k]["typed_pools"],
                    "visual_role": "line",
                    "source_file": (
                        selection_path.name
                        if k == 1
                        else independent_selection_path.name
                    ),
                    "source_field": (
                        "reviewer_selected_full_fidelity_exact_rate"
                        if k == 1
                        else "selected_exact_rate"
                    ),
                },
                {
                    "panel": "C",
                    "metric": "Error introduction",
                    "k": k,
                    "value": mechanisms[k]["error_introduction_rate"],
                    "unit": "proportion",
                    "numerator": mechanisms[k]["error_introductions"],
                    "denominator": mechanisms[k]["correct_origin_transitions"],
                    "visual_role": "line",
                    "source_file": mechanisms_path.name,
                    "source_field": "error_introduction_rate",
                },
                {
                    "panel": "C",
                    "metric": "Final-state error",
                    "k": k,
                    "value": mechanisms[k]["final_error_rate"],
                    "unit": "proportion",
                    "numerator": round(
                        float(mechanisms[k]["final_error_rate"])
                        * int(mechanisms[k]["selected_trajectories"])
                    ),
                    "denominator": mechanisms[k]["selected_trajectories"],
                    "visual_role": "line",
                    "source_file": mechanisms_path.name,
                    "source_field": "final_error_rate",
                },
                {
                    "panel": "C",
                    "metric": "Error persistence",
                    "k": k,
                    "value": mechanisms[k]["error_persistence_rate"],
                    "unit": "proportion",
                    "numerator": mechanisms[k]["error_persistences"],
                    "denominator": mechanisms[k]["incorrect_origin_transitions"],
                    "visual_role": "annotation",
                    "source_file": mechanisms_path.name,
                    "source_field": "error_persistence_rate",
                },
                {
                    "panel": "C",
                    "metric": "Self-repair",
                    "k": k,
                    "value": mechanisms[k]["self_repair_rate"],
                    "unit": "proportion",
                    "numerator": mechanisms[k]["self_repairs"],
                    "denominator": mechanisms[k]["incorrect_origin_transitions"],
                    "visual_role": "annotation",
                    "source_file": mechanisms_path.name,
                    "source_field": "self_repair_rate",
                },
            ]
        )

    for row in plot_rows:
        interval = intervals.get(str(row["metric"]))
        if row["visual_role"] == "line" and interval is not None:
            low, high = interval[int(row["k"])]
            row["ci_lower_95"] = low
            row["ci_upper_95"] = high
            row["uncertainty_method"] = "paired_writer_cluster_bootstrap_percentile"
            row["bootstrap_resamples"] = BOOTSTRAP_RESAMPLES
            row["bootstrap_seed"] = BOOTSTRAP_SEED
            row["writer_clusters"] = writer_count
        else:
            row["ci_lower_95"] = ""
            row["ci_upper_95"] = ""
            row["uncertainty_method"] = ""
            row["bootstrap_resamples"] = ""
            row["bootstrap_seed"] = ""
            row["writer_clusters"] = ""

    plot_data_path = output / "plot_data.csv"
    verification_path = output / "verification.json"
    pdf_path = output / "procurement_writer_ttc_five_writer.pdf"
    png_path = output / "procurement_writer_ttc_five_writer.png"
    caption_path = output / "CAPTION.md"
    notes_path = output / "README.md"
    _write_csv(plot_data_path, plot_rows)
    verification_path.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "status": "passed",
                "discrepancies": [],
                "checks": checks,
                "uncertainty": {
                    "method": "paired_writer_cluster_bootstrap_percentile",
                    "confidence_level": 0.95,
                    "writer_clusters": writer_count,
                    "resamples": BOOTSTRAP_RESAMPLES,
                    "seed": BOOTSTRAP_SEED,
                    "paired_across_k": True,
                    "intervals": {
                        metric: {
                            str(k): {"lower": low, "upper": high}
                            for k, (low, high) in by_k.items()
                        }
                        for metric, by_k in intervals.items()
                    },
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _plot(
        pdf_path,
        png_path,
        behavior,
        selection,
        deepseek_selection,
        mechanisms,
        intervals,
    )
    caption_path.write_text(
        """# Caption draft

**Figure X | Writer-side test-time compute improves behavioral safety but exposes a selection bottleneck in Procurement.** Results pool five writers over the same frozen Procurement histories, with GPT-OSS-120B fixed as executor (log2-scaled k axis). **A,** Authorized use and targeted unauthorized submission are evaluated on authorized and unauthorized requests, respectively; vertically stacked axes show utility and safety without a dual-axis comparison. **B,** Exact-memory availability is the fraction of typed candidate pools containing at least one deterministically exact memory. Writer self-review and DeepSeek independent review are the fractions for which each blinded selector chose an exact existing candidate; at k=1 they coincide because only one candidate is available. **C,** Error introduction is the fraction of correct-origin incremental transitions that become erroneous; final-state error is the fraction of selected incremental typed trajectories ending in error. Persistence is the fraction of incorrect-origin transitions that remain erroneous, and self-repair is the fraction that become correct; persistence is 100% and self-repair is 0% at every k. Error bars are pointwise 95% paired writer-cluster bootstrap percentile intervals (10,000 resamples; five writers; the same resampled writers at each k). With only five writer clusters, the intervals summarize across-writer robustness rather than population-level inference.
""",
        encoding="utf-8",
    )
    notes_path.write_text(
        f"""# Procurement writer-TTC figure notes

## Authoritative sources

- `{report_path}`
- `{summary_path}`
- `{audit_path}`
- `{behavior_path}`
- `{selection_path}`
- `{mechanisms_path}`
- `{fidelity_path}`
- `{behavior_writer_path}`
- `{selection_writer_path}`
- `{mechanisms_writer_path}`
- `{independent_report_path}`
- `{independent_summary_path}`
- `{independent_selection_path}`
- `{independent_selection_writer_path}`

The final audit pins the five-writer analysis manifest at `{_hash(analysis_dir / 'manifest.json')}` and the independent-review manifest at `{_hash(independent_dir / 'manifest.json')}`. Every file hash in both manifests was rechecked before plotting. `verification.json` confirms that all requested k=8 values match the authoritative files after the stated rounding; no discrepancies were found.

## Pooling and denominators

Panel A uses the already-pooled analysis rows, not a new recomputation: 1,440 executor trials per k, including 720 authorized and 720 unauthorized requests. Authorized use is conditioned on authorized requests; targeted unauthorized submission is conditioned on unauthorized requests.

Panel B uses 120 typed candidate pools per k for full-fidelity exact-memory availability and selected exactness. DeepSeek's k=1 point is the same single available candidate by identity; k=2,4,8 use the independent-review analysis. Failed reviews retain the preregistered prior selection and remain in selected-outcome denominators.

Panel C pools 60 selected incremental typed trajectories per k. Error introduction uses correct-origin transitions as its denominator; final-state error uses selected trajectories. Persistence and self-repair use incorrect-origin transitions.

## Uncertainty and design choices

Pointwise 95% percentile intervals use a paired writer-cluster bootstrap with 10,000 resamples and seed {BOOTSTRAP_SEED}. Each resample draws five writers with replacement, uses the same resampled writers at every k, and recomputes each pooled rate as the ratio of resampled numerator and denominator sums. This preserves pairing across the nested k pools. With only five writer clusters and 12 fixed histories per condition, the intervals are best read as a descriptive across-writer robustness check, not population-level inference.

Panel A uses vertically stacked mini-axes because authorized use is near 95% while targeted unauthorized submission is below 14%; a single 0–100% scale would suppress the safety change, while a dual axis would make slopes hard to compare. Distinct markers and line styles preserve interpretation in grayscale. Panel B leaves the three selection curves unshaded so neither practical selector is visually privileged. Panel C plots only introduction and final-state error; persistence and self-repair are reported in the caption and machine-readable data. Every x-axis is base-2 logarithmic with labeled ticks only at k=1,2,4,8.
""",
        encoding="utf-8",
    )

    source_paths = (
        analysis_dir / "manifest.json",
        independent_dir / "manifest.json",
        report_path,
        summary_path,
        audit_path,
        behavior_path,
        selection_path,
        mechanisms_path,
        fidelity_path,
        behavior_writer_path,
        selection_writer_path,
        mechanisms_writer_path,
        independent_report_path,
        independent_summary_path,
        independent_selection_path,
        independent_selection_writer_path,
    )
    files = {
        path.name: {"sha256": _hash(path), "bytes": path.stat().st_size}
        for path in (
            pdf_path,
            png_path,
            plot_data_path,
            verification_path,
            caption_path,
            notes_path,
        )
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at": "2026-08-15",
        "analysis_module": "analysis.plot_writer_ttc_figure",
        "model_calls": 0,
        "status": "completed",
        "sources": [
            {"path": str(path), "sha256": _hash(path)} for path in source_paths
        ],
        "verification_status": "passed",
        "discrepancies": [],
        "x_axis": {
            "scale": "log",
            "base": 2,
            "labeled_ticks": list(K_VALUES),
        },
        "uncertainty": {
            "method": "paired_writer_cluster_bootstrap_percentile",
            "confidence_level": 0.95,
            "writer_clusters": writer_count,
            "resamples": BOOTSTRAP_RESAMPLES,
            "seed": BOOTSTRAP_SEED,
            "paired_across_k": True,
        },
        "files": files,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
