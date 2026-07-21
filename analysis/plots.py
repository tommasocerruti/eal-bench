#!/usr/bin/env python3
"""Plot a normalized behavioral rate from a saved run.

    uv run python -m analysis.plots results/<domain>/<run>
    uv run python -m analysis.plots results/<domain>/<run> \
        --metric authorized_use --by condition_id --series target_pair

Needs the `analysis` extra:  uv sync --extra analysis
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .common import analysis_value, group_by, load, outcome_fraction

plt.rcParams.update(
    {
        "font.size": 12,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
    }
)

_METRICS = {
    "compliant": ("Compliance rate", "compliance"),
    "authorized_use": ("Authorized-use rate", "authorized_use"),
    "unsafe_action": ("Unauthorized-action rate", "unsafe_action"),
}


def _distinct(rows: list[dict[str, Any]], field: str) -> list[Any]:
    values = {
        analysis_value(row, field)
        for row in rows
        if analysis_value(row, field) is not None
    }
    return sorted(values, key=str)


def _default_x(rows: list[dict[str, Any]]) -> str:
    if any(analysis_value(row, "condition_id") is not None for row in rows):
        return "condition_id"
    return "scenario"


def _default_series(rows: list[dict[str, Any]]) -> str | None:
    writer_targets = _distinct(rows, "writer_target")
    executor_targets = _distinct(rows, "executor_target")
    if len(writer_targets) > 1 or len(executor_targets) > 1:
        return "target_pair"
    if not writer_targets and not executor_targets and len(_distinct(rows, "model")) > 1:
        return "model"
    return None


def _metric_fraction(
    rows: list[dict[str, Any]],
    metric: str,
) -> tuple[int, int]:
    if metric == "authorized_use":
        return outcome_fraction(
            rows,
            "requested_action_taken",
            denominator_field="request_authorized",
        )
    if metric == "unsafe_action":
        return outcome_fraction(
            rows,
            "unauthorized_action_taken",
            denominator_field="request_authorized",
            denominator_value=False,
        )
    return outcome_fraction(rows, "compliant")


def _default_output(results: str, suffix: str) -> str:
    path = Path(results)
    if path.suffix:
        return str(path.with_name(f"{path.stem}_{suffix}.png"))
    return f"{path}_{suffix}.png"


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("results")
    p.add_argument(
        "--domain",
        default=None,
        help="required only when results JSONL has no sibling manifest",
    )
    p.add_argument(
        "--metric",
        choices=sorted(_METRICS),
        default="compliant",
    )
    p.add_argument(
        "--by",
        default=None,
        help=(
            "x-axis field; supports metadata keys, dotted paths, and aliases such "
            "as condition_id"
        ),
    )
    p.add_argument(
        "--series",
        default=None,
        help=(
            "optional bar-series field; useful aliases include writer_target, "
            "executor_target, and target_pair"
        ),
    )
    p.add_argument("-o", "--output", default=None)
    args = p.parse_args()

    rows = load(args.results, domain=args.domain)
    if not rows:
        raise ValueError("no trials found")
    x_field = args.by or _default_x(rows)
    series_field = args.series or _default_series(rows)
    x_values = _distinct(rows, x_field)
    if not x_values:
        raise ValueError(f"no values found for x-axis field {x_field!r}")
    series_values = _distinct(rows, series_field) if series_field else [None]
    if not series_values:
        series_values = [None]
    grouping = (x_field, series_field) if series_field else (x_field,)
    grouped = group_by(rows, *grouping)

    x = np.arange(len(x_values))
    width = min(0.8, 0.8 / len(series_values))
    fig, ax = plt.subplots(figsize=(max(7, 1.1 * len(x_values)), 4.8))
    palette = ["#2166ac", "#b2182b", "#1b7837", "#e08214", "#762a83"]
    for index, series in enumerate(series_values):
        rates = []
        for x_value in x_values:
            key = (x_value, series) if series_field else (x_value,)
            numerator, denominator = _metric_fraction(
                grouped.get(key, []),
                args.metric,
            )
            rates.append(
                100 * numerator / denominator if denominator else np.nan
            )
        offset = (index - (len(series_values) - 1) / 2) * width
        label = None if series is None else str(series)
        ax.bar(
            x + offset,
            rates,
            width,
            color=palette[index % len(palette)],
            label=label,
        )

    ax.set_ylim(0, 105)
    metric_label, suffix = _METRICS[args.metric]
    ax.set_ylabel(metric_label)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{v}%" for v in [0, 25, 50, 75, 100]])
    ax.set_xticks(x)
    ax.set_xticklabels([str(value) for value in x_values], rotation=35, ha="right")
    domains = _distinct(rows, "domain_id")
    domain_label = ", ".join(map(str, domains)) if domains else "saved run"
    title = f"{metric_label} by {x_field}\n{domain_label}"
    if series_field:
        title += f" · series: {series_field}"
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.2)
    if series_field:
        ax.legend(frameon=False, fontsize=10)

    out = args.output or _default_output(args.results, suffix)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
