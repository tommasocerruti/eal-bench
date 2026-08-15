# Authorization-memory domains

Domains provide the model-visible setting and deterministic authorization semantics used by the
shared writer→memory→executor engine. Procurement is the reference core domain. Its active
release is `procurement_v1`, composed of:

- capacity corpus `calibration_v1`;
- behavioral corpus `benchmark_v1`;
- presentation `naturalistic_v1`;
- pressure profile `pressure_v1`;
- memory implementation `langmem_profile`.

`deployment_like_v1` is reserved for the procurement evaluation-awareness control collection;
it is not a behavioral benchmark corpus.

The registry also includes `cybersecurity`. Its historical frozen release is `cybersecurity_v1`,
composed of:

- capacity corpus `calibration_v1`;
- behavioral corpus `benchmark_v1`;
- presentation `naturalistic_v1`;
- pressure profile `financial_urgency_v1`;
- memory implementation `langmem_profile`.

The original gate accepted this release, but the corrected gate now requires every one-shot chain
and every incremental chain's initial update to create a usable profile. Cybersecurity fails that
new viability check, so its saved behavioral results remain diagnostic until a successor passes.
Procurement passes the corrected audit at 24/24 one-shot and 24/24 incremental initial profiles.

The registry also includes the core domain `finance`. Its frozen public release is
`finance_v1`, composed of:

- capacity corpus `calibration_v1`;
- behavioral corpus `benchmark_v1`;
- presentation `naturalistic_v1`;
- pressure profile `loss_containment_v1`;
- memory implementation `langmem_profile`.

Its eight-family final corpus passes offline validation and supplies 128 authorized plus 128
unauthorized ordinary trials per writer–executor pair. GPT-OSS and DeepSeek pass the faithful-
control isolation gate, and the five-writer × two-executor transfer matrix is complete. The
canonical GPT-OSS writer route remains pending, so the release is not yet merge-eligible.

## Domain contract

`AuthorizationMemoryDomain` in `domains/base.py` composes:

- a corpus adapter for versions, cases, replay, blocks, probes, sources, and capacity;
- a memory adapter for typed state, faithful evidence, parsing, and writer instructions;
- an executor adapter for requests, native tools, the oracle, and normalized actions;
- a fidelity adapter for canonical-versus-remembered comparisons;
- presentation, study, conformance, and optional awareness registrations.

Use `domains/toolkit.py` when the shared authorization envelope fits the domain. It carries
identity, effect, action, status, validity, supersession, provenance, and an opaque domain-owned
scope. Implement lower-level protocols only when the domain requires different semantics.

The shared experiment code owns LangMem execution, target matrices, batching, contexts, lineage,
hashing, persistence, source-run loading, pressure pairing, and generic validation. It must never
import a concrete domain. A domain owns its vocabulary, sources, replay, oracle, scope, choices,
tools, attractiveness semantics, pressure variants, and semantic validation.

## Behavioral routes

Core domains implement the same three routes:

| Route | Domain contribution |
|---|---|
| `controls` | Faithful evidence and valid one-field controlled broadenings. |
| `writer` | Fidelity, substantive-error screening, witnesses, and exact repairs. |
| `pressure` | Registered pressure rendering and domain-specific invariants. |

The writer route defaults to the complete free-text/typed × one-shot/incremental factorial.
Pressure reuses a completed writer run and changes only the registered pressure content. The
optional `evaluation_awareness` route is a separate validity analysis.

## Presentations and releases

Every model-visible renderer receives a registered `PresentationProfile`. A presentation ID and
hash define a treatment and cannot be pooled with another. Hidden case, probe, request, treatment,
oracle, and score identifiers must never appear in provider-visible messages or tools.

A core domain declares one machine-readable release tying together its benchmark and calibration
corpora, presentation, pressure profile, memory implementation and hash, canonical seed, review
status, freeze status, and source hashes. Domain defaults come from that release declaration, not
from procurement-specific branches in shared code.

Maturity values are:

- `fixture`: structural validation only;
- `development`: complete routes, but review or acceptance is incomplete;
- `core`: fully reviewed primary benchmark.

Maturity is distinct from `freeze_status`, which is either `not_frozen` or `frozen`.

## Adding a domain

Start from the scaffold:

```bash
uv run python -m domains.scaffold my_domain --dry-run
uv run python -m domains.scaffold my_domain
```

Then:

1. Define domain-native case, event, request, scope, and ledger types.
2. Implement deterministic replay and authorization.
3. Add source corpora, matched probes, choices, tools, and naturalistic rendering.
4. Register a versioned presentation and release defaults.
5. Implement the three route hooks and offline conformance samples.
6. Register one factory in `domains/__init__.py`.
7. Meet the contribution and empirical gates in `domains/CONTRIBUTING.md`.

Offline validation must not contact a provider:

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study controls \
  --validate-only

uv run python -m experiments.run --validate-only --all-domains
uv run ruff check .
git diff --check
```

Live qualification follows only after the exact call plan and cost estimate are reviewed and
approved.
