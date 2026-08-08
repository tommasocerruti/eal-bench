# Cybersecurity domain

The cybersecurity domain studies authorization-memory failures in incident response. A security
duty officer may permit an incident-response team to execute named actions only for a specific
tenant, incident, asset set, environment set, vulnerability set, and half-open time window:
`valid_from <= requested_at < valid_until`.

The active release is `cybersecurity_v1`.

| Component | ID |
|---|---|
| Behavioral corpus | `benchmark_v1` |
| Capacity corpus | `calibration_v1` |
| Presentation | `naturalistic_v1` |
| Pressure profile | `financial_urgency_v1` |
| Memory implementation | `langmem_profile` |
| Canonical seed | `20260812` |

The release declaration and immutable component hashes are in [`release.json`](release.json).
The frozen release contains 16 held-out families and 128 matched authorization
decisions. Each history presents a signed pre-final permission snapshot followed by an atomic
state replacement. Missing that replacement retains obsolete grants and loses current grants,
creating deterministic stale-memory overgrant and undergrant without changing the oracle or
making the request ambiguous.

## Routes

- `controls`: faithful free-text and typed evidence, full history, controlled broadening, exact
  repair, and semantic sham conditions with GPT-OSS and DeepSeek V4 Pro executors.
- `writer`: the complete free-text/typed × one-shot/incremental LangMem factorial using GPT-OSS as
  writer and executor, plus frozen natural-error witnesses and exact repairs.
- `pressure`: exact replay of the writer jobs under `financial_urgency_v1`, with zero writer calls
  and zero baseline reruns.

## Final results

Both executors achieved 128/128 authorized uses and 0/128 unauthorized actions across faithful
text and typed controls. Controlled broadening caused 64/64 unauthorized actions.

Generated memory caused 43/256 unauthorized actions at baseline (16.8%), while authorized use was
144/256 (56.3%). The primary rate is defined over out-of-scope submitted requests. A supplemental
all-trial diagnostic also counts unauthorized operational alternatives selected when the submitted
request was authorized: 69/512 ordinary trials contained an unauthorized terminal action.

All 20 selected substantive-memory witnesses caused the predicted unauthorized action, versus
0/20 after exact canonical repair. Eight repair calls selected the authorized operational
alternative already visible in the request. Their original synthetic probes omitted the internal
course linkage, so an offline hash-linked rescore corrected those rows from invalid to compliant
without changing raw calls, model-visible contexts, or the 0/20 repair safety result. Among unsafe
ordinary typed actions, 42/42 were formally authorized by stored memory and denied by canonical
state.

The one-shot typed writer failed to create a profile in all 16 cases. Thirty of 32 attempts emitted
no valid patch after reaching the 4,096-token output limit; the other two emitted invalid typed
profiles. The frozen atomic-retention policy therefore preserved an empty initial profile, yielding
0/64 authorized use and 0/64 unauthorized actions. This condition remains in the primary
intention-to-treat denominator as a pipeline-generation failure and is not interpreted as faithful
or safe memory.

Under financial and deadline pressure, unauthorized actions rose to 55/256 (21.5%) and authorized
use fell to 95/256 (37.1%). The supplemental all-trial diagnostic found 87/512 unauthorized
terminal actions under pressure. Unsafe outcomes spanned 14/16 families. The release passes every
scientific-domain merge threshold in `domains/CONTRIBUTING.md`. The separately recorded aggressive
25% baseline and 30% pressure stress targets were not reached.

The three final routes produced 2,660 provider responses with no provider errors. Baseten did not
return `usage.cost`; the documented-rate estimate from recorded token usage is USD 11.537112425,
within the approved USD 12 cap.

## Reproduce validation

```bash
uv run python -m experiments.run \
  --domain cybersecurity \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study controls \
  --validate-only

uv run python -m experiments.run \
  --domain cybersecurity \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study writer \
  --validate-only

uv run python -m experiments.run --validate-only --all-domains
uv run ruff check .
```

The frozen release is `release.json`. The route summaries, threshold reports, fidelity and witness
reports, typed-attribution report, mechanism report, cost aggregate, and final results bundle are
under `results/cybersecurity/`. That directory also contains the immutable-source offline-rescore
record and writer-failure diagnostics.
