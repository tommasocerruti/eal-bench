# Procurement writer TTC — GLM 5.2

Writer/reviewer target: `glm_5_2_baseten`. Nested trajectory-level selected best-of-k with k=1, 2, 4, 8. The reviewer selected one complete trajectory without rewriting or merging and had no canonical oracle.

## Main results

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 58.3% | 20.8% | 20.8% | 0.0% | 94.4% | 13.2% | 8.0% |
| 2 | 50.0% | 20.8% | 20.8% | 0.0% | 95.1% | 11.1% | 6.2% |
| 4 | 50.0% | 20.8% | 20.8% | 0.0% | 95.8% | 11.1% | 5.9% |
| 8 | 50.0% | 16.7% | 16.7% | 0.0% | 91.7% | 8.3% | 4.5% |

Typed fidelity and authority metrics are deterministic and exclude free text. Behavioral rates pool all four conditions; condition-level rows are saved separately.

## Sampling versus selection

| k | Pool contains full-fidelity exact | Reviewer selects exact | Reviewer hits oracle-best | Mean selection regret | Reviewer failure |
|---:|---:|---:|---:|---:|---:|
| 1 | 25.0% | 25.0% | 100.0% | 0.000 fields | NA |
| 2 | 37.5% | 25.0% | 66.7% | 0.750 fields | 12.5% |
| 4 | 37.5% | 25.0% | 62.5% | 0.875 fields | 64.6% |
| 8 | 41.7% | 16.7% | 41.7% | 1.208 fields | 2.1% |

Generation uses the deterministic best typed memory available in each pool. Selection uses the actual reviewer choice, including the frozen fallback after review failure. Free-text oracle regret is undefined, and executor behavior is never used to define an oracle.

## Incremental typed mechanism

| k | Introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 11.5% | 100.0% | 0.0% | 50.0% |
| 2 | 14.6% | 100.0% | 0.0% | 58.3% |
| 4 | 14.6% | 100.0% | 0.0% | 58.3% |
| 8 | 12.5% | 100.0% | 0.0% | 50.0% |

Each mechanism row follows one reviewer-selected complete trajectory; states are never spliced across candidates.

## Diversity and lineage

| k | Candidate pairs | Distinct pairs | Newly added candidate selected |
|---:|---:|---:|---:|
| 1 | 0 | 0 | NA |
| 2 | 48 | 44 | 22/48 |
| 4 | 288 | 263 | 5/48 |
| 8 | 1344 | 1221 | 21/48 |

The nested-lineage audit verifies every inherited candidate exactly at each adjacent level.

## Cost

The non-reused TTC stages contain 2430 call records: 2394 successful and 36 failed. Provider-reported cost was $0.000000; saved-token reconstruction at frozen rates adds $12.907603, for $12.907603. 36 calls lacked usage metadata.
