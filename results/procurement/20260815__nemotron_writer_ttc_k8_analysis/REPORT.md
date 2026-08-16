# Procurement writer TTC — Nemotron 3 Ultra

Writer/reviewer target: `nemotron_3_ultra_baseten`. Nested trajectory-level selected best-of-k with k=1, 2, 4, 8. The reviewer selected one complete trajectory without rewriting or merging and had no canonical oracle.

## Main results

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 54.2% | 25.0% | 25.0% | 0.0% | 92.4% | 8.3% | 4.2% |
| 2 | 54.2% | 25.0% | 25.0% | 0.0% | 97.9% | 8.3% | 4.2% |
| 4 | 54.2% | 20.8% | 20.8% | 0.0% | 99.3% | 8.3% | 4.2% |
| 8 | 45.8% | 20.8% | 20.8% | 0.0% | 99.3% | 8.3% | 4.2% |

Typed fidelity and authority metrics are deterministic and exclude free text. Behavioral rates pool all four conditions; condition-level rows are saved separately.

## Sampling versus selection

| k | Pool contains full-fidelity exact | Reviewer selects exact | Reviewer hits oracle-best | Mean selection regret | Reviewer failure |
|---:|---:|---:|---:|---:|---:|
| 1 | 37.5% | 37.5% | 100.0% | 0.000 fields | NA |
| 2 | 45.8% | 33.3% | 83.3% | 0.500 fields | 4.2% |
| 4 | 54.2% | 29.2% | 62.5% | 0.750 fields | 33.3% |
| 8 | 66.7% | 25.0% | 37.5% | 1.250 fields | 0.0% |

Generation uses the deterministic best typed memory available in each pool. Selection uses the actual reviewer choice, including the frozen fallback after review failure. Free-text oracle regret is undefined, and executor behavior is never used to define an oracle.

## Incremental typed mechanism

| k | Introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 16.3% | 100.0% | 0.0% | 66.7% |
| 2 | 16.3% | 100.0% | 0.0% | 66.7% |
| 4 | 17.0% | 100.0% | 0.0% | 66.7% |
| 8 | 14.9% | 100.0% | 0.0% | 58.3% |

Each mechanism row follows one reviewer-selected complete trajectory; states are never spliced across candidates.

## Diversity and lineage

| k | Candidate pairs | Distinct pairs | Newly added candidate selected |
|---:|---:|---:|---:|
| 1 | 0 | 0 | NA |
| 2 | 48 | 38 | 17/48 |
| 4 | 288 | 232 | 14/48 |
| 8 | 1344 | 1102 | 23/48 |

The nested-lineage audit verifies every inherited candidate exactly at each adjacent level.

## Cost

The non-reused TTC stages contain 2290 call records: 2290 successful and 0 failed. Provider-reported cost was $0.000000; saved-token reconstruction at frozen rates adds $7.385837, for $7.385837. 0 calls lacked usage metadata.
