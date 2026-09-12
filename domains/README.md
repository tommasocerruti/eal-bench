# Authorization-memory domains

Domains provide the model-visible setting and deterministic authorization semantics used by the
shared writer→memory→executor engine. The three core domains use the same experiment routes and
[paper result format](../results/README.md):

| Domain | Paper release | Behavioral corpus | Presentation | Pressure profile |
|---|---|---|---|---|
| [Procurement](procurement/README.md) | `procurement_v1` | `benchmark_v1` | `naturalistic_v1` | `pressure_v1` |
| [Cybersecurity](cybersecurity/README.md) | `cybersecurity_v1` | `benchmark_v1` | `naturalistic_v1` | `financial_urgency_v1` |
| [Finance](finance/README.md) | `finance_redesign_v1` | `benchmark_v1` | `naturalistic_v1` | `loss_containment_v1` |

All use `calibration_v1` for capacity and `langmem_profile` for memory. Each release pins its own
scientific sources and hashes; matching a corpus name alone does not identify an experiment.
Historical single-writer qualification reports are retained separately from the paper's selected
five-writer, two-executor, three-seed results. Their gate outcomes do not describe the full matrix.

`deployment_like_v1` is reserved for Procurement's evaluation-awareness control collection;
it is not a behavioral benchmark corpus.

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
