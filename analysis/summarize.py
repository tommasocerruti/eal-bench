#!/usr/bin/env python3
"""Print domain-neutral behavioral outcomes from a saved run.

    uv run python -m analysis.summarize results/<domain>/<run>
    uv run python -m analysis.summarize results/<domain>/<run> \
        --by condition_id writer_target executor_target
"""

from __future__ import annotations

import argparse
from typing import Any

from .common import (
    analysis_value,
    group_by,
    load,
    outcome_fraction,
    wilson_ci,
)


def _distinct(rows: list[dict[str, Any]], field: str) -> list[Any]:
    values = {
        analysis_value(row, field)
        for row in rows
        if analysis_value(row, field) is not None
    }
    return sorted(values, key=str)


def _default_grouping(rows: list[dict[str, Any]]) -> list[str]:
    fields = [
        "condition_id"
        if any(analysis_value(row, "condition_id") is not None for row in rows)
        else "scenario"
    ]
    if len(_distinct(rows, "writer_target")) > 1:
        fields.append("writer_target")
    if len(_distinct(rows, "executor_target")) > 1:
        fields.append("executor_target")
    return fields


def _format_fraction(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "—"
    return f"{numerator}/{denominator} ({numerator / denominator:.1%})"


def _label(values: tuple[Any, ...], width: int) -> str:
    text = " / ".join("—" if value is None else str(value) for value in values)
    if len(text) <= width:
        return text
    return f"{text[: width - 1]}…"


def _print_provenance(rows: list[dict[str, Any]]) -> None:
    domains = _distinct(rows, "domain_id")
    print(f"\nDomain: {', '.join(map(str, domains)) or 'unrecorded'}")
    for role in ("writer", "executor"):
        targets = _distinct(rows, f"{role}_target")
        providers = _distinct(rows, f"{role}_provider")
        models = _distinct(rows, f"{role}_model")
        details = []
        if targets:
            details.append(f"targets={', '.join(map(str, targets))}")
        if providers:
            details.append(f"providers={', '.join(map(str, providers))}")
        if models and not targets:
            details.append(f"models={', '.join(map(str, models))}")
        if details:
            print(f"{role.title()}: {'; '.join(details)}")


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
        "--by",
        nargs="+",
        default=None,
        help=(
            "fields to group on; supports metadata keys, dotted paths, and aliases "
            "condition_id, writer_target, executor_target, and target_pair"
        ),
    )
    args = p.parse_args()

    rows = load(args.results, domain=args.domain)
    if not rows:
        print("\nNo trials found.\n")
        return
    by = args.by or _default_grouping(rows)
    groups = group_by(rows, *by)
    _print_provenance(rows)

    labels = [" / ".join(map(str, key)) for key in groups]
    label_width = min(64, max(len(" / ".join(by)), *(len(item) for item in labels)))
    heading = " / ".join(by)
    columns = (
        f"{heading:<{label_width}}"
        f"{'N':>6}"
        f"{'Parsed':>17}"
        f"{'Compliant':>17}"
        f"{'95% CI':>16}"
        f"{'Authorized use':>20}"
        f"{'Unsafe action':>20}"
    )
    print(f"\nGrouped by: {' / '.join(by)}")
    print(columns)
    print("-" * len(columns))
    for key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        g = groups[key]
        parsed = outcome_fraction(g, "parseable")
        compliant = outcome_fraction(g, "compliant")
        authorized_use = outcome_fraction(
            g,
            "requested_action_taken",
            denominator_field="request_authorized",
        )
        unsafe = outcome_fraction(
            g,
            "unauthorized_action_taken",
            denominator_field="request_authorized",
            denominator_value=False,
        )
        lo, hi = wilson_ci(*compliant)
        ci = f"[{lo:.1%}, {hi:.1%}]"
        print(
            f"{_label(key, label_width):<{label_width}}"
            f"{len(g):>6}"
            f"{_format_fraction(*parsed):>17}"
            f"{_format_fraction(*compliant):>17}"
            f"{ci:>16}"
            f"{_format_fraction(*authorized_use):>20}"
            f"{_format_fraction(*unsafe):>20}"
        )
    decisions: dict[str, int] = {}
    for row in rows:
        decision = str(analysis_value(row, "decision", default="unrecorded"))
        decisions[decision] = decisions.get(decision, 0) + 1
    rendered = ", ".join(
        f"{decision}={count}" for decision, count in sorted(decisions.items())
    )
    print(f"\nDecisions: {rendered}")
    print(
        "Denominators retain invalid and no-action trials; authorized use is "
        "conditioned on authorized requests, and unsafe action on unauthorized requests."
    )
    print()


if __name__ == "__main__":
    main()
