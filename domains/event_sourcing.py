"""Domain-owned storage and lifecycle conventions for event reduction."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EventSourcingSpec:
    retain_inactive_records: bool = False
    source_id_separator: str | None = None
    empty_supersedes: str | None = None
    replacement_target_field: str = "supersedes"
    order_by_effective_at: bool = False
    nested_scope_fields: tuple[str, ...] = ()
    flattened_scope_list_fields: tuple[str, ...] = ()
