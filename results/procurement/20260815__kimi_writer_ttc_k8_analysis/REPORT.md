# Procurement writer TTC — Kimi K2.6

Writer/reviewer target: `kimi_baseten`. Nested trajectory-level selected best-of-k with k=1, 2, 4, 8. The reviewer selected one complete trajectory without rewriting or merging and had no canonical oracle.

## Main results

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 45.8% | 33.3% | 29.2% | 4.2% | 93.1% | 13.9% | 7.6% |
| 2 | 66.7% | 29.2% | 29.2% | 0.0% | 98.6% | 11.1% | 5.6% |
| 4 | 58.3% | 20.8% | 20.8% | 0.0% | 98.6% | 7.6% | 3.8% |
| 8 | 58.3% | 16.7% | 16.7% | 0.0% | 97.9% | 6.2% | 3.5% |

Typed fidelity and authority metrics are deterministic and exclude free text. Behavioral rates pool all four conditions; condition-level rows are saved separately.

## Sampling versus selection

| k | Pool contains full-fidelity exact | Reviewer selects exact | Reviewer hits oracle-best | Mean selection regret | Reviewer failure |
|---:|---:|---:|---:|---:|---:|
| 1 | 29.2% | 29.2% | 100.0% | 0.000 fields | NA |
| 2 | 41.7% | 33.3% | 83.3% | 0.250 fields | 0.0% |
| 4 | 45.8% | 29.2% | 62.5% | 0.667 fields | 6.2% |
| 8 | 50.0% | 29.2% | 62.5% | 0.750 fields | 0.0% |

Generation uses the deterministic best typed memory available in each pool. Selection uses the actual reviewer choice, including the frozen fallback after review failure. Free-text oracle regret is undefined, and executor behavior is never used to define an oracle.

## Incremental typed mechanism

| k | Introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 21.7% | 100.0% | 0.0% | 83.3% |
| 2 | 14.3% | 100.0% | 0.0% | 58.3% |
| 4 | 12.5% | 100.0% | 0.0% | 50.0% |
| 8 | 12.5% | 100.0% | 0.0% | 50.0% |

Each mechanism row follows one reviewer-selected complete trajectory; states are never spliced across candidates.

## Diversity and lineage

| k | Candidate pairs | Distinct pairs | Newly added candidate selected |
|---:|---:|---:|---:|
| 1 | 0 | 0 | NA |
| 2 | 48 | 42 | 28/48 |
| 4 | 288 | 245 | 24/48 |
| 8 | 1344 | 1131 | 23/48 |

The nested-lineage audit verifies every inherited candidate exactly at each adjacent level.

## Cost

The non-reused TTC stages contain 2183 call records: 2167 successful and 16 failed. Provider-reported cost was $0.000000; saved-token reconstruction at frozen rates adds $7.121367, for $7.121367. 16 calls lacked usage metadata.
