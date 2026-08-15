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

Across five writers and both executors, baseline authorized use was 86.6% and unauthorized
submission was 5.9%. Under pressure these changed to 77.3% and 10.1%. Natural substantive memory
errors caused 24/24 unsafe actions, while exact canonical repair caused 0/24. Fixed-memory action
outcomes agreed across executors on 98.4% of matched requests.

Qwen's incremental free-text initialization succeeded for 7/8 families, so its failed initial
profile remains in the intention-to-treat results. The complete transfer matrix cost USD 37.29
under its USD 50 cap; isolation controls cost USD 4.30 separately. Full tables are in
[`results/finance/finance_v1__matrix_results.md`](../../results/finance/finance_v1__matrix_results.md).

The transfer matrix is complete, but it does not replace the repository's canonical scientific
merge gate. Finance remains ineligible to merge as a claim-complete scientific domain until a
GPT-OSS writer → GPT-OSS executor writer route and its linked pressure route pass on this release.

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
