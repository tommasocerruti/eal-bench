"""Reusable EAL evaluation interface.

Load versioned trials, score them with the official scorer, and aggregate with
explicit denominators, without the experiment runner and without provider
credentials. Tracks are reported separately and are never combined into one score.
"""

from __future__ import annotations

from .export import read_outcomes, write_outcomes, write_trials
from .metrics import (
    Count,
    MixedConditionsError,
    MixedExecutorsError,
    MixedResourcesError,
    MixedSurfacesError,
    TrackMetrics,
    aggregate,
    aggregate_by,
    require_single_condition,
    require_single_executor,
    require_single_resource,
    require_single_surface,
)
from .resources import (
    CALIBRATION_TOKENIZER,
    PROTOCOL_ID,
    SCORER_ID,
    ResourceVersions,
    UncalibratedTokenizerError,
    describe,
    list_domains,
    load_domain,
    require_calibration_tokenizer,
)
from .scoring import TrialOutcome, score_many, score_response
from .trials import ModelResponse, ToolCall, Trial, TrialTruth

__all__ = [
    "CALIBRATION_TOKENIZER",
    "PROTOCOL_ID",
    "SCORER_ID",
    "Count",
    "MixedConditionsError",
    "MixedExecutorsError",
    "MixedResourcesError",
    "MixedSurfacesError",
    "ModelResponse",
    "ResourceVersions",
    "ToolCall",
    "TrackMetrics",
    "Trial",
    "TrialOutcome",
    "TrialTruth",
    "UncalibratedTokenizerError",
    "aggregate",
    "aggregate_by",
    "describe",
    "list_domains",
    "load_domain",
    "read_outcomes",
    "require_calibration_tokenizer",
    "require_single_condition",
    "require_single_executor",
    "require_single_resource",
    "require_single_surface",
    "score_many",
    "score_response",
    "write_outcomes",
    "write_trials",
]
