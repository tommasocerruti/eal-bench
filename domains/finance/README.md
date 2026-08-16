# Finance domain

Finance studies authorization-memory failures in portfolio-order execution. A portfolio mandate
officer may permit trades only for a named account, strategy, instrument set, side, order type,
quantity ceiling, price interval, settlement currency, and half-open time window.

The active release is `finance_v1`.

| Component | ID |
|---|---|
| Behavioral corpus | `benchmark_v1` |
| Capacity corpus | `calibration_v1` |
| Presentation | `naturalistic_v1` |
| Pressure profile | `loss_containment_v1` |
| Memory implementation | `langmem_profile` |
| Canonical seed | `20260816` |

The release declaration and immutable hashes are in [`release.json`](release.json). The corpus has
eight held-out families and four matched request pairs per family. Each final signed transaction
replaces six obsolete mandates with six current mandates. Every outside request is covered by one
complete pre-final mandate and denied by the final state; its inside match differs in exactly one
serialized request field and has the opposite authorization result.

## Routes

- `controls`: faithful free-text and typed evidence, full history, controlled broadening, exact
  repair, and semantic sham conditions with GPT-OSS and DeepSeek executors.
- `writer`: the full free-text/typed × one-shot/incremental LangMem factorial.
- `pressure`: exact replay of every frozen writer baseline under `loss_containment_v1`, with no
  writer calls or baseline reruns.

## Results

Both executors passed isolation: faithful text and typed memory each produced 32/32 authorized
uses and 0/32 unauthorized submissions, while controlled broadening produced 32/32 unauthorized
submissions.

Across five writers and both executors, baseline authorized use was 86.6% and unsafe action was
5.9%. Under pressure these changed to 77.3% and 10.1%. Natural substantive memory
errors caused 24/24 unsafe actions, while exact canonical repair caused 0/24. Fixed-memory action
outcomes agreed across executors on 98.4% of matched requests.

The shared typed-state mechanism analysis yields an 80 → 19 → 6 → 6 → 6
final-memory funnel: final typed memories, semantic errors, authority-gaining errors,
apparent-authority memories, and propagated unsafe actions. The frozen derivation is in
[`finance_v1__mechanism_extension.json`](../../results/finance/finance_v1__mechanism_extension.json).

Qwen's incremental free-text initialization succeeded for 7/8 families, so its failed initial
profile remains in the intention-to-treat results. The complete transfer matrix cost USD 37.29
under its USD 50 cap; isolation controls cost USD 4.30 separately. Full tables are in
[`results/finance/finance_v1__matrix_results.md`](../../results/finance/finance_v1__matrix_results.md).

Finance is a claim-valid, merge-eligible core domain. The repository owner's final acceptance
treats the completed five-writer by two-executor matrix, passed isolation controls, exact-repair
reversal, and byte-identical public release mapping as sufficient evidence. This acceptance
supersedes the earlier plan for a separate GPT-OSS writer → GPT-OSS executor merge route without
altering or resampling any completed result. The decision and its retained limitations are frozen
in [`finance_v1__acceptance.json`](../../results/finance/finance_v1__acceptance.json).

## Offline validation

```bash
uv run python -m experiments.run \
  --domain finance \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study controls \
  --validate-only

uv run python -m experiments.run \
  --domain finance \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study writer \
  --validate-only

uv run python -m experiments.run --validate-only --all-domains
uv run ruff check .
```

The public package exposes only the two v1 corpus identities. Immutable paid-run manifests retain
their original technical execution identifiers; the byte-identical model-surface mapping is
recorded in `results/finance/finance_v1__release_equivalence.json`.
