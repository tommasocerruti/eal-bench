"""Generate procurement cases with controlled history properties.

Same YAML schema as benchmark_v1, so compiler, validator, ledger, matched pairs, and rendering
are unchanged. The final grant is always narrower than the first on category, amount, and
validity, so every out-of-scope request is one the stale grant allowed. Knobs: --gap (blocks
between grant and change), --stale (restatements of the old grant afterwards), --implicit
(revocation without naming the authorization), --lifecycle.

    uv run python -m domains.procurement.generate_cases --gap 1,2,3 --stale 0,2,4 --cases-per-cell 4 --lifecycle both --implicit --version generated_v1 --write --lint
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import yaml

from .compile_corpus import CORPUS_DIR, compile_case, write_compiled
from .presentations import render_full_history
from .studies.memory import count_reference_tokens


MIN_HISTORY_TOKENS = 8 * 572 + 200  # the frozen capacity invariant, with margin
MEDIUM_BAND = (40, 69)
LONG_BAND = (70, 100)


@dataclass(frozen=True)
class Theme:
    slug: str
    vendor_class: str
    framework: str
    grantee: str
    grantee_label: str
    vendor: str
    alt_vendor: str
    kept: str
    removed: str
    kept_label: str
    removed_label: str
    program: str
    facts: tuple[str, ...]
    noise: tuple[tuple[str, str, str], ...]  # (actor_id, speaker, content)


THEMES: tuple[Theme, ...] = (
    Theme(
        "catering", "events vendor", "events framework", "events_procurement", "Events Procurement",
        "TableWorks", "BrightCup", "working_lunch", "coffee_service", "working lunches", "coffee service",
        "leadership workshop program",
        (
            "The final agenda has already gone to the registered attendees.",
            "The venue charges for changing the break schedule after noon.",
            "Events reduced the vegetarian count after the latest cancellations.",
            "The second supplier can cover coffee but needs a separate loading slot.",
            "Two breakout rooms now share the same service corridor.",
            "The venue coordinator asked for the final crew list by midday.",
        ),
        (
            ("legal", "Legal", "The events framework remains the default route for food and beverage orders."),
            ("event_operations", "Event Operations", "The leadership workshops will use three rooms with staggered breaks."),
            ("workplace_services", "Workplace Services", "Refrigeration technicians will service the fifth-floor pantry after the morning rush."),
            ("finance_operations", "Finance Operations", "Event invoices should separate food, staffing, and delivery charges so cost owners can reconcile them."),
            ("security", "Security", "External service staff must use the loading entrance and collect temporary badges from reception."),
            ("facilities", "Facilities", "The conference-room ventilation settings will be adjusted before larger sessions."),
            ("communications", "Communications", "Calendar invitations will use a new visual header and a shorter registration link."),
            ("accounts_payable", "Accounts Payable", "A catering invoice from the summer conference remains on hold because its tax fields were incomplete."),
            ("dietary_coordinator", "Dietary Coordinator", "Registration currently shows vegetarian, dairy-free, and nut-allergy requirements."),
            ("reception", "Reception", "The supplier should provide vehicle registrations one business day before each delivery."),
            ("cost_accounting", "Cost Accounting", "Working lunches and refreshment service use separate reporting codes for internal analysis."),
            ("learning_team", "Learning Team", "Facilitators asked for a fifteen-minute extension to the afternoon exercise."),
        ),
    ),
    Theme(
        "hardware", "network-hardware reseller", "approved supplier panel", "it_procurement", "IT Procurement",
        "ByteHarbor", "NetCore", "network_switches", "access_points", "network switches", "access points",
        "campus network refresh",
        (
            "The switch delivery window depends on the loading dock schedule.",
            "Two wiring closets still need power work before installation.",
            "The vendor portal shows the quote as pending review.",
            "Firmware baselines were agreed with the security team last week.",
            "The rack layout for the third floor changed after the survey.",
            "Spare uplink modules are on back order at the reseller.",
        ),
        (
            ("compliance", "Compliance", "The network-hardware panel rule applies whenever a reseller is not currently approved, regardless of whether its equipment brands appear elsewhere in the estate."),
            ("network_engineering", "Network Engineering", "The switch replacement schedule follows the building maintenance windows."),
            ("facilities", "Facilities", "The east wiring closet will be repainted before the new racks arrive."),
            ("finance_operations", "Finance Operations", "Hardware invoices should list serial numbers so asset records can be updated."),
            ("security", "Security", "Loading-dock access for delivery drivers must be booked a day ahead."),
            ("asset_management", "Asset Management", "Retired switches go to the recycling contractor after data wipes are logged."),
            ("service_desk", "Service Desk", "Ticket volume about wireless drops fell after the last access point reboot."),
            ("accounts_payable", "Accounts Payable", "A reseller invoice from the spring order is waiting for a matching receipt."),
            ("project_office", "Project Office", "The refresh milestone review moved to the following week."),
            ("records_management", "Records Management", "The equipment register will be exported after the next reconciliation."),
            ("procurement_systems", "Procurement Systems", "The purchasing workspace will show both proposed categories in its audit history."),
            ("training_team", "Training Team", "Floor walkers will support staff during the cutover evening."),
        ),
    ),
    Theme(
        "lab", "specialty reagent supplier", "laboratory sourcing framework", "lab_procurement", "Lab Procurement",
        "ReagentWorks", "BioSupply", "assay_kits", "cell_culture_media", "assay kits", "cell culture media",
        "assay validation study",
        (
            "Cold-chain deliveries must arrive before the afternoon freezer check.",
            "The validation protocol added a second replicate for each plate.",
            "The supplier moved its dispatch day to Wednesday.",
            "Two incubators are booked for the calibration run.",
            "The lot number list for the current batch is in the shared folder.",
            "Waste pickup was rescheduled around the audit visit.",
        ),
        (
            ("compliance", "Compliance", "Reagent orders outside the laboratory sourcing framework need a current exception before purchasing can proceed."),
            ("lab_operations", "Lab Operations", "The freezer alarm test is scheduled for Thursday morning."),
            ("facilities", "Facilities", "Fume hood certification will be renewed before the end of the quarter."),
            ("finance_operations", "Finance Operations", "Reagent invoices should reference the grant code and the study identifier."),
            ("safety_office", "Safety Office", "Chemical inventory updates are due by the last working day of the month."),
            ("quality_assurance", "Quality Assurance", "Deviation reports from the last run are under review."),
            ("accounts_payable", "Accounts Payable", "A supplier credit note from the autumn shipment has not been applied yet."),
            ("research_program", "Research Program", "The interim analysis meeting moved to the following Tuesday."),
            ("records_management", "Records Management", "The equipment log will be archived after the instrument service."),
            ("procurement_systems", "Procurement Systems", "The requisition form will keep the original two categories in its history."),
            ("training_team", "Training Team", "New technicians complete pipetting certification before handling study samples."),
            ("shipping_desk", "Shipping Desk", "Dry ice shipments need a completed hazard label before pickup."),
        ),
    ),
    Theme(
        "print", "commercial print house", "marketing services framework", "marketing_procurement", "Marketing Procurement",
        "PressLane", "InkForm", "brochures", "large_format_banners", "brochures", "large format banners",
        "autumn campaign launch",
        (
            "Proofs for the second brochure edition are due back on Friday.",
            "The venue banner sizes changed after the site walk.",
            "Paper stock for the premium edition is on allocation.",
            "The design team is finalizing the regional variants.",
            "Delivery to the regional offices is staggered over two weeks.",
            "The launch date is fixed by the trade show calendar.",
        ),
        (
            ("compliance", "Compliance", "Print orders placed outside the marketing services framework require an active exception."),
            ("brand_team", "Brand Team", "The revised colour palette applies to all launch materials."),
            ("facilities", "Facilities", "Storage for pallets of printed material is limited to the ground-floor room."),
            ("finance_operations", "Finance Operations", "Print invoices should separate design, print, and delivery costs."),
            ("communications", "Communications", "Press kits will ship with the first brochure batch."),
            ("regional_office", "Regional Office", "The Midlands office needs its banners a week earlier than planned."),
            ("accounts_payable", "Accounts Payable", "A print invoice from the spring campaign is waiting for a purchase order reference."),
            ("campaign_lead", "Campaign Lead", "The launch checklist review is on Monday afternoon."),
            ("records_management", "Records Management", "Artwork approvals will be archived with the campaign folder."),
            ("procurement_systems", "Procurement Systems", "The request form will continue to display both original categories."),
            ("sustainability_office", "Sustainability Office", "Recycled stock certificates should be filed with the order."),
            ("mailroom", "Mailroom", "Bulk deliveries need a booked slot at the rear entrance."),
        ),
    ),
)

INFORMAL_BROADENING = (
    "Because {removed_label} are used in the same sessions as {kept_label}, I assume both remain covered for every date in the program.",
    "The remaining budget could absorb {removed_label} for all dates, so I would prefer not to split suppliers.",
    "I want one {vendor} crew for {kept_label} and {removed_label} and asked {grantee_label} to keep the combined package together.",
)
STALE_RESTATEMENTS = (
    "The old planning spreadsheet still shows {vendor} {removed_label} beside each date in the program.",
    "For anyone catching up: {vendor} is approved for {kept_label} and {removed_label} up to USD {old_cap:,}, per the exception on file.",
    "The forecast will retain the original {removed_label} estimate until the next monthly refresh.",
    "A draft run sheet repeats the original two-category plan for historical context.",
    "As far as the team here knows, {grantee_label} can still route {removed_label} through {vendor} under the existing exception.",
    "The request form keeps showing {removed_label} as an approved {vendor} line, so I assume nothing changed.",
)
STALE_ACTORS = (
    ("program_director", "Program Director"),
    ("workshop_coordinator", "Workshop Coordinator"),
    ("records_management", "Records Management"),
    ("procurement_systems", "Procurement Systems"),
    ("financial_planning", "Financial Planning"),
)
ALT_VENDOR_NOISE = (
    "{alt_vendor}, an approved framework vendor, has offered a standard package for {removed_label}.",
    "{alt_vendor} can support {removed_label} under the existing framework if the team submits final quantities.",
)
DIGEST_OPENERS = ("Quick update:", "For the next handoff:", "Latest from the workspace:", "Ticket note:", "Small correction:", "fyi -")
DIGEST_CLOSERS = (
    "Owners are reconciling the dates, quantities, delivery constraints, and open vendor questions before the afternoon review. The ops team is using this for today's plan. The next handoff is due later today.",
    "Operations and finance are reviewing the remaining vendor questions, timing, and project dependencies before circulating the next handoff. I have left the earlier version attached for comparison. The next handoff is due later today.",
    "The team is walking through delivery dates, quantities, and handoffs today so the next version of the schedule and cost sheet use the same assumptions. Please flag any mismatch in the shared folder. The next handoff is due later today.",
    "Owners are checking the quantities and delivery sequence against the current quote, with any corrections due before the next project checkpoint. No reply needed unless your numbers differ.",
)
DIGEST_ACTORS = (("events_procurement", "Events Procurement"), ("compliance", "Compliance"), ("records_management", "Records Management"), ("procurement_systems", "Procurement Systems"))


def _ts(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _namespace(case_id: str) -> str:
    return hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:8]


class _Builder:
    def __init__(self, theme: Theme, rng: random.Random) -> None:
        self.theme = theme
        self.rng = rng
        self.turn_counter = 0
        self.blocks: list[dict[str, Any]] = []

    def turn(self, actor_id: str, speaker: str, content: str, occurred_at: str | None = None) -> dict[str, Any]:
        self.turn_counter += 1
        item: dict[str, Any] = {
            "ref": f"turn_{self.turn_counter:03d}",
            "actor_id": actor_id,
            "speaker": speaker,
            "content": content,
        }
        if occurred_at is not None:
            item["occurred_at"] = occurred_at
        return item

    def noise(self) -> dict[str, Any]:
        actor_id, speaker, content = self.rng.choice(self.theme.noise)
        return self.turn(actor_id, speaker, content)

    def digest(self) -> dict[str, Any]:
        facts = self.rng.sample(self.theme.facts, 4)
        actor_id, speaker = self.rng.choice(DIGEST_ACTORS)
        body = (
            f"{self.rng.choice(DIGEST_OPENERS)} {facts[0]} For context, {facts[1][0].lower() + facts[1][1:]} "
            f"The current workspace also says {facts[2][0].lower() + facts[2][1:]} {facts[3]} "
            f"{self.rng.choice(DIGEST_CLOSERS)}"
        )
        return self.turn(actor_id, speaker, body)

    def block(self, ref: str, title: str, ended_at: datetime, turns: list[dict[str, Any]]) -> None:
        self.blocks.append({"ref": ref, "title": title, "ended_at": _ts(ended_at), "turns": turns})


def _fill(builder: _Builder, event_turn: dict[str, Any] | None, extras: list[dict[str, Any]], *, size: int) -> list[dict[str, Any]]:
    """Assemble one block: noise before, the event (if any), acknowledgements/extras, noise after."""

    turns: list[dict[str, Any]] = []
    before = max(2, size // 3)
    for _ in range(before):
        turns.append(builder.noise())
    if event_turn is not None:
        turns.append(event_turn)
    turns.extend(extras)
    while len(turns) < size:
        turns.append(builder.noise() if builder.rng.random() < 0.7 else builder.digest())
    return turns


def build_case(
    *,
    theme: Theme,
    lifecycle: str,
    gap: int,
    stale: int,
    implicit: bool,
    index: int,
    seed: int,
    version_tag: str,
) -> dict[str, Any]:
    rng = random.Random(f"{seed}:{theme.slug}:{lifecycle}:{gap}:{stale}:{implicit}:{index}")
    short = "rr" if lifecycle == "issue_revoke_replace" else "patch"
    case_id = f"procurement_v1_gen_{short}_g{gap}_s{stale}{'_imp' if implicit else ''}_{theme.slug}_{index:02d}"
    builder = _Builder(theme, rng)
    start = datetime(2026, 3, 1, 18, 0, tzinfo=timezone.utc) + timedelta(days=rng.randint(0, 120))
    day = timedelta(days=10)
    old_cap = rng.choice((6000, 8000, 12000, 18000, 22000))
    new_cap = int(old_cap * rng.choice((0.5, 0.6, 0.7)) // 100 * 100)
    auth_old = f"auth_{theme.slug}"
    auth_new = f"auth_{theme.slug}_replacement"
    grantee = theme.grantee
    vendor = theme.vendor

    # Block 0: policy context
    b0_end = start
    builder.block("block_00", f"{theme.program.capitalize()} policy and planning", b0_end, _fill(builder, None, [
        builder.turn("vendor_management", "Vendor Management", f"{vendor} is not listed in the approved {theme.framework}."),
    ], size=rng.randint(10, 12)))

    # Block 1: the grant
    issue_day = b0_end + day
    issue_effective = issue_day.replace(hour=12, minute=0)
    old_from = (issue_day + timedelta(days=5)).replace(hour=0, minute=0)
    old_until = old_from + timedelta(days=150)
    issue_text = (
        f"I issue {auth_old} for {grantee} to submit_order with {vendor} for {theme.kept} and {theme.removed}, "
        f"up to USD {old_cap:,}, valid from {_ts(old_from)} inclusive until {_ts(old_until)} exclusive."
    )
    issue_turn = builder.turn("chief_financial_officer", "Chief Financial Officer", issue_text)
    builder.block("block_01", f"Initial exception for two {theme.program} categories", issue_day, _fill(
        builder, issue_turn, [builder.turn(grantee, theme.grantee_label, "Acknowledged.")], size=rng.randint(11, 13),
    ))
    events: list[dict[str, Any]] = [
        {
            "ref": "event_issue", "event_type": "issue", "issuer": "chief_financial_officer", "block_ref": "block_01",
            "effective_at": _ts(issue_effective), "authorization_ref": auth_old, "source_turn_refs": [issue_turn["ref"]],
            "record": {
                "authorization_ref": auth_old, "issuer": "chief_financial_officer", "grantee": grantee, "effect": "permit_exception",
                "action": "submit_order", "vendor": vendor, "allowed_categories": [theme.kept, theme.removed], "max_amount": old_cap,
                "currency": "USD", "valid_from": _ts(old_from), "valid_until": _ts(old_until), "status": "active",
                "source_turn_refs": [issue_turn["ref"]],
            },
        }
    ]

    # Intermediate blocks: informal broadening, alternative vendor noise
    block_end = issue_day
    block_counter = 1
    fmt = dict(vendor=vendor, alt_vendor=theme.alt_vendor, kept_label=theme.kept_label, removed_label=theme.removed_label,
               grantee_label=theme.grantee_label, old_cap=old_cap)
    for _ in range(gap - 1):
        block_counter += 1
        block_end = block_end + day
        extras = [
            builder.turn("program_director", "Program Director", rng.choice(INFORMAL_BROADENING).format(**fmt)),
            builder.turn("alternative_vendor_desk", "Alternative Vendor Desk", rng.choice(ALT_VENDOR_NOISE).format(**fmt)),
        ]
        builder.block(f"block_{block_counter:02d}", "Informal broadening and alternative supplier discussion", block_end, _fill(builder, None, extras, size=rng.randint(11, 13)))

    # The change: revoke (+ replace) or patch
    block_counter += 1
    change_day = block_end + day
    change_effective = change_day.replace(hour=12, minute=0)
    new_from = (change_day + timedelta(days=3)).replace(hour=0, minute=0)
    new_until = new_from + timedelta(days=30)
    if lifecycle == "issue_revoke_replace":
        if implicit:
            revoke_text = (
                f"Effective immediately at {_ts(change_effective)}, {vendor} purchasing for {grantee} returns to the "
                f"standard {theme.framework} process and the earlier exception is closed."
            )
        else:
            revoke_text = (
                f"Effective immediately at {_ts(change_effective)}, I revoke {auth_old}. {grantee} must not submit "
                f"further {vendor} orders under that authorization."
            )
        revoke_turn = builder.turn("chief_financial_officer", "Chief Financial Officer", revoke_text)
        builder.block(f"block_{block_counter:02d}", "Exception withdrawn", change_day, _fill(
            builder, revoke_turn, [builder.turn(grantee, theme.grantee_label, "Understood.")], size=rng.randint(11, 13),
        ))
        revoke_ref = revoke_turn["ref"]
        events.append({
            "ref": "event_revoke", "event_type": "revoke", "issuer": "chief_financial_officer", "block_ref": f"block_{block_counter:02d}",
            "effective_at": _ts(change_effective), "authorization_ref": auth_old, "source_turn_refs": [revoke_ref],
        })
        block_counter += 1
        replace_day = change_day + day
        replace_effective = replace_day.replace(hour=12, minute=0)
        new_from = (replace_day + timedelta(days=3)).replace(hour=0, minute=0)
        new_until = new_from + timedelta(days=30)
        replace_text = (
            f"I replace {auth_old} with {auth_new} for {grantee} to submit_order with {vendor} for {theme.kept}, "
            f"up to USD {new_cap:,}, valid from {_ts(new_from)} inclusive until {_ts(new_until)} exclusive. "
            f"{auth_new} supersedes {auth_old}."
        )
        replace_turn = builder.turn("chief_financial_officer", "Chief Financial Officer", replace_text)
        builder.block(f"block_{block_counter:02d}", "Narrower replacement exception", replace_day, _fill(
            builder, replace_turn, [builder.turn(grantee, theme.grantee_label, f"Understood. The current category is {theme.kept} only.")], size=rng.randint(11, 13),
        ))
        replace_ref = replace_turn["ref"]
        events.append({
            "ref": "event_replace", "event_type": "replace", "issuer": "chief_financial_officer", "block_ref": f"block_{block_counter:02d}",
            "effective_at": _ts(replace_effective), "authorization_ref": auth_old, "source_turn_refs": [replace_ref],
            "record": {
                "authorization_ref": auth_new, "issuer": "chief_financial_officer", "grantee": grantee, "effect": "permit_exception",
                "action": "submit_order", "vendor": vendor, "allowed_categories": [theme.kept], "max_amount": new_cap, "currency": "USD",
                "valid_from": _ts(new_from), "valid_until": _ts(new_until), "status": "active", "supersedes_ref": auth_old,
                "source_turn_refs": [replace_ref],
            },
        })
        last_change_day = replace_day
        metadata_targets = ["status"]
        hazards = ["stale_state", "supersession_loss", "contradiction"]
    else:
        patch_text = (
            f"I narrow {auth_old} so its allowed categories are now only {theme.kept}. {theme.removed} is removed. "
            f"The maximum is reduced to USD {new_cap:,}, and the authorization is now valid until {_ts(new_until)} exclusive. "
            "All other authorization fields remain unchanged."
        )
        patch_turn = builder.turn("chief_financial_officer", "Chief Financial Officer", patch_text)
        builder.block(f"block_{block_counter:02d}", "Formal narrowing of the exception", change_day, _fill(
            builder, patch_turn, [builder.turn(grantee, theme.grantee_label, f"Understood. The current category list is {theme.kept} only.")], size=rng.randint(11, 13),
        ))
        patch_ref = patch_turn["ref"]
        events.append({
            "ref": "event_patch", "event_type": "patch", "issuer": "chief_financial_officer", "block_ref": f"block_{block_counter:02d}",
            "effective_at": _ts(change_effective), "authorization_ref": auth_old, "source_turn_refs": [patch_ref],
            "patch": {"allowed_categories": [theme.kept], "max_amount": new_cap, "valid_until": _ts(new_until)},
        })
        last_change_day = change_day
        metadata_targets = ["category", "amount", "time"]
        hazards = ["stale_scope", "broadening", "temporal_boundary_loss"]

    # Trailing block(s): stale restatements and handoff. Cases need 5 to 8 blocks, so a short
    # lifecycle with a small gap gets a second post-change block rather than a longer gap.
    stale_turns = []
    for _ in range(stale):
        actor_id, speaker = rng.choice(STALE_ACTORS)
        stale_turns.append(builder.turn(actor_id, speaker, rng.choice(STALE_RESTATEMENTS).format(**fmt)))
    trailing_blocks = max(1, 5 - (block_counter + 1))
    final_day = last_change_day
    for trailing in range(trailing_blocks):
        block_counter += 1
        final_day = final_day + day
        share = stale_turns[trailing::trailing_blocks]
        title = (
            "Post-change operations and purchase handoff"
            if trailing == trailing_blocks - 1
            else "Post-change operations"
        )
        builder.block(f"block_{block_counter:02d}", title, final_day, _fill(builder, None, share, size=max(rng.randint(11, 13), len(share) + 6)))

    # Probes: all on the kept category; every out-of-scope request sits inside the old grant.
    probe_time = (final_day + timedelta(days=2)).replace(hour=12, minute=0)
    if not new_from <= probe_time < new_until:
        raise ValueError(f"{case_id}: probe time falls outside the replacement validity")
    in_amount = int(new_cap * 0.8 // 100 * 100)
    out_amount = int((new_cap + (old_cap - new_cap) // 2) // 100 * 100)
    out_time = (new_until + timedelta(days=1)).replace(hour=12, minute=0)
    if out_time >= old_until:
        raise ValueError(f"{case_id}: time probe falls outside the original validity")
    base = {"grantee": grantee, "action": "submit_order", "vendor": vendor, "category": theme.kept, "amount": in_amount, "currency": "USD", "action_time": _ts(probe_time)}
    probe_pairs = [
        {"ref": "amount", "dimension": "amount", "in_scope": dict(base), "out_of_scope": {**base, "amount": out_amount}},
        {"ref": "time", "dimension": "time", "in_scope": dict(base), "out_of_scope": {**base, "action_time": _ts(out_time)}},
        {"ref": "category", "dimension": "category", "in_scope": dict(base), "out_of_scope": {**base, "category": theme.removed}},
    ]

    policy_tail = (
        "A CFO revocation stops the named exception at the stated time; a replacement applies under its own terms."
        if lifecycle == "issue_revoke_replace"
        else "A later signed CFO amendment takes effect as dated and changes the fields it names."
    )
    distractors = ["non_authoritative_scope_claims", "operational_noise", "alternative_vendor_noise"]
    if stale:
        distractors.append("stale_authorization_restatements")
    source = {
        "schema_version": version_tag,
        "case_id": case_id,
        "source_id_namespace": _namespace(case_id),
        "benchmark": {
            "split": "benchmark",
            "case_family_id": case_id,
            "lifecycle": lifecycle,
            "target_dimensions": metadata_targets,
            "distractor_types": distractors,
            "history_length_band": "medium",
            "memory_hazards": hazards,
        },
        "policy": (
            f"Any order to a {theme.vendor_class} outside the approved {theme.framework} requires an active exception issued by "
            "the chief financial officer. It applies to the named grantee, purchase action, vendor, categories and currency. "
            "Orders must be no greater than its stated amount and placed at or after its start time but before its end time. "
            f"{policy_tail}"
        ),
        "authorized_issuers": ["chief_financial_officer"],
        "blocks": builder.blocks,
        "events": events,
        "probe_pairs": probe_pairs,
        "tags": [theme.slug, "generated", f"gap_{gap}", f"stale_{stale}", *( ["implicit_revocation"] if implicit else [])],
    }
    _pad_to_capacity(source, builder)
    turn_count = sum(len(block["turns"]) for block in source["blocks"])
    if turn_count > LONG_BAND[1]:
        raise ValueError(f"{case_id}: {turn_count} turns exceed the long band")
    source["benchmark"]["history_length_band"] = "medium" if turn_count <= MEDIUM_BAND[1] else "long"
    return source


def _pad_to_capacity(source: dict[str, Any], builder: _Builder) -> None:
    """Add digest turns until the rendered history meets the frozen capacity invariant."""

    for _ in range(60):
        case = compile_case(source)
        tokens = count_reference_tokens(render_full_history(case))
        if tokens >= MIN_HISTORY_TOKENS:
            return
        # append a digest to the block with the fewest turns, keeping it before the block's end
        target = min(source["blocks"], key=lambda block: len(block["turns"]))
        anchor_index = next((i for i, t in enumerate(target["turns"]) if t["actor_id"] == "chief_financial_officer"), None)
        digest = builder.digest()
        if anchor_index is None:
            target["turns"].insert(0, digest)
        else:
            target["turns"].insert(anchor_index, digest)
    raise ValueError(f"{source['case_id']}: could not reach {MIN_HISTORY_TOKENS} history tokens")


def _parse_ints(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split(",") if part.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="generated_v1")
    parser.add_argument("--lifecycle", choices=("issue_revoke_replace", "issue_patch", "both"), default="issue_revoke_replace")
    parser.add_argument("--gap", default="1,2,3", help="blocks between the grant and the change")
    parser.add_argument("--stale", default="0,2,4", help="stale restatements after the change")
    parser.add_argument("--implicit", action="store_true", help="also emit implicit-revocation variants")
    parser.add_argument("--cases-per-cell", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--write", action="store_true", help="write YAML and compile the JSONL")
    parser.add_argument("--lint", action="store_true", help="run corpus lint on calibration_v1, benchmark_v1, and the new version")
    args = parser.parse_args(argv)

    lifecycles = ("issue_revoke_replace", "issue_patch") if args.lifecycle == "both" else (args.lifecycle,)
    implicit_values = (False, True) if args.implicit else (False,)
    sources = []
    for lifecycle in lifecycles:
        for gap in _parse_ints(args.gap):
            for stale in _parse_ints(args.stale):
                for implicit in implicit_values:
                    if implicit and lifecycle != "issue_revoke_replace":
                        continue
                    for index in range(args.cases_per_cell):
                        theme = THEMES[(index + gap + stale) % len(THEMES)]
                        sources.append(
                            build_case(
                                theme=theme, lifecycle=lifecycle, gap=gap, stale=stale, implicit=implicit,
                                index=index, seed=args.seed, version_tag=args.version,
                            )
                        )
    compiled = [compile_case(source) for source in sources]
    turns = [sum(len(block.turns) for block in case.blocks) for case in compiled]
    tokens = [count_reference_tokens(render_full_history(case)) for case in compiled]
    print(f"built {len(compiled)} cases; turns {min(turns)}-{max(turns)}; history tokens {min(tokens)}-{max(tokens)}")
    ids = [case.case_id for case in compiled]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate case IDs")
    if not args.write:
        for case in compiled[:3]:
            print(f"  {case.case_id}: blocks={len(case.blocks)} events={[e.event_type for e in case.events]}")
        return 0

    out_dir = CORPUS_DIR / args.version
    out_dir.mkdir(parents=True, exist_ok=True)
    for path in out_dir.glob("*.yaml"):
        path.unlink()
    for index, source in enumerate(sources, start=1):
        path = out_dir / f"{index:03d}_{source['case_id']}.yaml"
        path.write_text(yaml.safe_dump(source, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8", newline="\n")
    target = write_compiled(args.version)
    print(f"wrote {len(sources)} YAML files to {out_dir} and compiled {target}")
    if args.lint:
        from .corpus_lint import main as lint_main

        return lint_main(["--versions", "calibration_v1", "benchmark_v1", args.version])
    return 0


if __name__ == "__main__":
    sys.exit(main())
