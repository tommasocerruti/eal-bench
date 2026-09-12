"""Reusable EAL evaluation interface.

Load versioned trials, score them with the official scorer, and aggregate with
explicit denominators, without the experiment runner and without provider
credentials. Tracks are reported separately and are never combined into one score.
"""

from __future__ import annotations

from .metrics import Count, TrackMetrics, aggregate, aggregate_by
from .resources import (
    PROTOCOL_ID,
    SCORER_ID,
    ResourceVersions,
    describe,
    list_domains,
    load_domain,
)
from .scoring import TrialOutcome, score_many, score_response
from .trials import ModelResponse, ToolCall, Trial, TrialTruth

__all__ = [
    "PROTOCOL_ID",
    "SCORER_ID",
    "Count",
    "ModelResponse",
    "ResourceVersions",
    "ToolCall",
    "TrackMetrics",
    "Trial",
    "TrialOutcome",
    "TrialTruth",
    "aggregate",
    "aggregate_by",
    "describe",
    "list_domains",
    "load_domain",
    "score_many",
    "score_response",
]
