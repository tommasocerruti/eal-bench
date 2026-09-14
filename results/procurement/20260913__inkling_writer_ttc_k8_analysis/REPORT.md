# Procurement writer TTC — Inkling

Writer/reviewer target: `inkling_baseten`. Nested trajectory-level selected best-of-k with k=1, 2, 4, 8. The reviewer selected one complete trajectory without rewriting or merging and had no canonical oracle.

## Main results

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 41.7% | 33.3% | 20.8% | 12.5% | 83.3% | 11.8% | 6.6% |
| 2 | 41.7% | 25.0% | 20.8% | 4.2% | 84.0% | 11.8% | 7.3% |
| 4 | 41.7% | 25.0% | 20.8% | 4.2% | 86.1% | 11.1% | 6.6% |
| 8 | 41.7% | 25.0% | 20.8% | 4.2% | 84.7% | 11.8% | 6.9% |

Typed fidelity and authority metrics are deterministic and exclude free text. Behavioral rates pool all four conditions; condition-level rows are saved separately.

## Sampling versus selection

| k | Pool contains full-fidelity exact | Reviewer selects exact | Reviewer hits oracle-best | Mean selection regret | Reviewer failure |
|---:|---:|---:|---:|---:|---:|
| 1 | 25.0% | 25.0% | 100.0% | 0.000 fields | NA |
| 2 | 25.0% | 16.7% | 70.8% | 0.500 fields | 83.3% |
| 4 | 29.2% | 16.7% | 58.3% | 0.708 fields | 100.0% |
| 8 | 33.3% | 12.5% | 33.3% | 1.125 fields | 93.8% |

Generation uses the deterministic best typed memory available in each pool. Selection uses the actual reviewer choice, including the frozen fallback after review failure. Free-text oracle regret is undefined, and executor behavior is never used to define an oracle.

## Incremental typed mechanism

| k | Introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 21.6% | 94.1% | 5.9% | 83.3% |
| 2 | 21.6% | 94.1% | 5.9% | 83.3% |
| 4 | 21.6% | 94.1% | 5.9% | 83.3% |
| 8 | 21.6% | 94.1% | 5.9% | 83.3% |

Each mechanism row follows one reviewer-selected complete trajectory; states are never spliced across candidates.

## Diversity and lineage

| k | Candidate pairs | Distinct pairs | Newly added candidate selected |
|---:|---:|---:|---:|
| 1 | 0 | 0 | NA |
| 2 | 48 | 46 | 4/48 |
| 4 | 288 | 273 | 0/48 |
| 8 | 1344 | 1271 | 0/48 |

The nested-lineage audit verifies every inherited candidate exactly at each adjacent level.

## Cost

The non-reused TTC stages contain 2578 call records: 2558 successful and 20 failed. Provider-reported cost was $0.000000; saved-token reconstruction at frozen rates adds $20.161668, for $20.161668. 20 calls lacked usage metadata.
