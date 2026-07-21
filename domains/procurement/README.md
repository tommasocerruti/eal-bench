# Procurement

Procurement is the reference EAL-Bench domain. The active release is `procurement_v1`.

| Component | ID |
|---|---|
| Behavioral corpus | `benchmark_v1` |
| Capacity corpus | `calibration_v1` |
| Presentation | `naturalistic_v1` |
| Pressure profile | `pressure_v1` |
| Memory implementation | `langmem_profile` |
| Canonical seed | `20260719` |

The release declaration and immutable component hashes are in [`release.json`](release.json).
The accepted benchmark histories and challenges are unchanged at the provider-visible surface;
the release migration changed only internal identities and metadata.

## Scope and oracle

The domain models scoped purchase exceptions across grantee, action, vendor, category, amount,
currency, validity, status, and supersession. Twelve case families cover issue, patch,
revocation, replacement, narrowing, and time changes. Each matched probe changes exactly one of
amount, category, or time. Replay and tool authorization are deterministic.

Every challenge includes an operationally preferred unauthorized order and a feasible but worse
compliant course. `pressure_v1` adds case-specific business objectives and immediate stakes while
leaving evidence, requests, choices, tools, and authorization unchanged.

## Capacity

`calibration_v1` fixes the largest faithful memory at 286 reference tokens. The primary budget is
572 tokens (2×), the tight research budget is 358 tokens (1.25×), and every benchmark history is
at least eight times the primary budget. [`capacity_calibration.json`](capacity_calibration.json)
pins sources, representations, tokenizer, counts, policy, and hashes.

Compile and lint sources with:

```bash
uv run python -m domains.procurement.compile_corpus \
  --version calibration_v1 --write
uv run python -m domains.procurement.compile_corpus \
  --version benchmark_v1 --write
uv run python -m domains.procurement.corpus_lint \
  --versions calibration_v1 benchmark_v1
```

Edit YAML sources, never compiled JSONL directly.

## Offline validation

```bash
uv run python -m experiments.run \
  --domain procurement \
  --study controls \
  --validate-only

uv run python -m experiments.run \
  --domain procurement \
  --study writer \
  --validate-only

uv run python -m experiments.run --validate-only --all-domains
```

The release supplies `benchmark_v1` and `naturalistic_v1` when they are omitted. A pressure
validation additionally requires a completed compatible writer source or the shared offline
source fixture.

## Review and freeze

The repository owner approved the authorization clarity, operational attractiveness,
compliant-course feasibility, and release freeze recorded in [`reviews/`](reviews/). The blinded
packets remain available for optional independent review; any later disagreement must be recorded
and resolved rather than hidden.

The frozen acceptance sequence is GPT-OSS controls, the GPT-OSS full writer route,
its linked GPT-OSS pressure route, and DeepSeek V4 Pro controls. The merge criteria are defined in
[`../CONTRIBUTING.md`](../CONTRIBUTING.md). Any failure requires a successor benchmark version;
the frozen corpus is never altered or resampled.

`deployment_like_v1` is reserved for the separately authored evaluation-awareness control
package described in [`awareness_controls/README.md`](awareness_controls/README.md).
