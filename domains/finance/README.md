# Finance domain

The Finance domain studies authorization-memory failures in portfolio-order execution. A
portfolio mandate officer may delegate trading authority only for a named trader, account,
strategy, instrument set, side, order type, quantity ceiling, price interval, settlement
currency, and half-open time window.

The public release is `finance_v1`, composed of:

- capacity corpus `calibration_v1`;
- behavioral corpus `benchmark_v1`;
- presentation `naturalistic_v1`;
- pressure profile `loss_containment_v1`;
- memory implementation `langmem_profile`.

## Design

Each case builds a sixteen-record active mandate book and then applies one signed atomic
transaction that revokes all sixteen records and issues two current grants. Six later desk
blocks reproduce the obsolete book as explicitly archived, superseded, non-authoritative
exports. The authorization rule remains complete and unambiguous; difficulty comes from updating
memory after a large state contraction and rejecting highly salient stale records.

Four matched request pairs test a removed instrument, a side retained only by a revoked mandate,
a cross-record order-type combination, and an exact time shift. Each pair differs in one
serialized request field. The final state authorizes every inside request and denies every
outside request, while the stale pre-contraction state reverses those decisions.

Capacity is twice the largest faithful text or typed payload at any authorization-changing
checkpoint. The pressure treatment adds concrete loss, deadline, and execution urgency without
changing authority. Every executor choice uses a distinct native terminal tool, so scoring never
depends on free-text interpretation.

## Routes

- `controls`: faithful text and typed evidence, full history, controlled broadening, exact
  repair, and semantic shams.
- `writer`: the complete free-text/typed × one-shot/incremental LangMem factorial, typed
  checkpoint screening, natural witnesses, and exact repairs.
- `pressure`: exact replay of a frozen writer source, with no writer calls or baseline reruns.

## Development evidence

The final eight-family surface passed faithful controls with both required executors. GPT-OSS
and DeepSeek each achieved 64/64 authorized uses and 0/64 unauthorized actions across faithful
text and typed memory; controlled broadening produced 32/32 unauthorized actions for each. The
DeepSeek run encountered 30 exhausted rate-limited calls; a hash-linked continuation retained all
258 successful outcomes and retried only those failures, with no successful outcome rerun.

In the completed Nemotron-to-GPT-OSS route, all 16 initial profiles were created. Generated
memory produced 14/64 unauthorized submissions (21.9%) and 56/64 authorized uses. Eight selected
natural errors across four families caused 8/8 unsafe actions, versus 0/8 after exact repair.
Exact-source pressure retained 14/64 unauthorized submissions, reduced authorized use to 45/64,
and increased unsafe action across all ordinary trials from 19/128 to 28/128.

These are development results, not a completed merge-gate result. The final `benchmark_v1`
combines those four development-derived families with four reserved families, providing 128
ordinary authorized and 128 ordinary unauthorized trials per writer–executor pair. The added
families satisfy the trial-count requirement and both executors now pass isolation. The canonical
GPT-OSS writer → GPT-OSS executor and pressure routes still need to pass before Finance can be
marked merge-eligible.

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
  --writer-targets nemotron_3_ultra_baseten \
  --executor-targets gptoss_baseten,deepseek_baseten \
  --validate-only

uv run python -m experiments.run --validate-only --all-domains
uv run ruff check .
```
