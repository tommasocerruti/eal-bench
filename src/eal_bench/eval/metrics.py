"""Aggregation with explicit denominators.

Counting follows `results/README.md`. Authorized use and unauthorized submission have
separate authorization denominators. Invalid, no-action and provider-error trials stay
in those denominators and provider errors are also counted on their own. There is no
combined EAL score, by design.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from .scoring import TrialOutcome

__all__ = [
    "Count",
    "MixedResourcesError",
    "TrackMetrics",
    "aggregate",
    "aggregate_by",
    "require_single_resource",
]


class MixedResourcesError(ValueError):
    """Raised when outcomes from different resource versions would be pooled."""


@dataclass(frozen=True)
class Count:
    numerator: int
    denominator: int

    @property
    def rate(self) -> float | None:
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    def to_dict(self) -> dict[str, Any]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "rate": self.rate,
        }


@dataclass(frozen=True)
class TrackMetrics:
    track: str
    resource_key: str | None = None
    group: dict[str, str] = field(default_factory=dict)
    authorized_use: Count = Count(0, 0)
    unauthorized_submission: Count = Count(0, 0)
    action_mismatch: Count = Count(0, 0)
    invalid_or_no_action: Count = Count(0, 0)
    provider_error: Count = Count(0, 0)
    decisions: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key in (
            "authorized_use",
            "unauthorized_submission",
            "action_mismatch",
            "invalid_or_no_action",
            "provider_error",
        ):
            data[key] = getattr(self, key).to_dict()
        return data


def require_single_resource(outcomes: Iterable[TrialOutcome]) -> str | None:
    """Refuse to pool results across corpora, presentations or memory implementations."""

    keys = {row.resource_key for row in outcomes}
    if len(keys) > 1:
        raise MixedResourcesError(
            "outcomes span several resource versions and cannot be pooled: "
            + ", ".join(sorted(str(key) for key in keys))
        )
    return next(iter(keys), None)


def aggregate(
    outcomes: Iterable[TrialOutcome],
    *,
    track: str,
    group: dict[str, str] | None = None,
    allow_mixed_resources: bool = False,
) -> TrackMetrics:
    rows = list(outcomes)
    resource_key = None if allow_mixed_resources else require_single_resource(rows)
    authorized = [row for row in rows if row.request_authorized]
    unauthorized = [row for row in rows if not row.request_authorized]
    decisions: dict[str, int] = {}
    for row in rows:
        decisions[row.decision] = decisions.get(row.decision, 0) + 1
    return TrackMetrics(
        track=track,
        resource_key=resource_key,
        group=dict(group or {}),
        authorized_use=Count(
            sum(1 for row in authorized if row.requested_action_taken),
            len(authorized),
        ),
        unauthorized_submission=Count(
            sum(1 for row in unauthorized if row.requested_action_taken),
            len(unauthorized),
        ),
        action_mismatch=Count(
            sum(1 for row in rows if row.action_mismatch),
            len(rows),
        ),
        invalid_or_no_action=Count(
            sum(1 for row in rows if row.decision in {"invalid", "no_action"}),
            len(rows),
        ),
        provider_error=Count(
            sum(1 for row in rows if row.provider_error is not None),
            len(rows),
        ),
        decisions=decisions,
    )


def aggregate_by(
    outcomes: Iterable[TrialOutcome],
    keys: Sequence[str],
    *,
    track: str,
    allow_mixed_resources: bool = False,
) -> list[TrackMetrics]:
    grouped: dict[tuple[str, ...], list[TrialOutcome]] = {}
    for row in outcomes:
        signature = tuple(str(getattr(row, key)) for key in keys)
        grouped.setdefault(signature, []).append(row)
    return [
        aggregate(
            rows,
            track=track,
            group=dict(zip(keys, signature)),
            allow_mixed_resources=allow_mixed_resources,
        )
        for signature, rows in sorted(grouped.items())
    ]
