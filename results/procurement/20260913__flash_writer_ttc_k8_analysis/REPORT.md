# Procurement writer TTC — DeepSeek V4.1 Flash

Writer/reviewer target: `deepseek_v4_1_flash_baseten`. Nested trajectory-level selected best-of-k with k=1, 2, 4, 8. The reviewer selected one complete trajectory without rewriting or merging and had no canonical oracle.

## Main results

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 75.0% | 0.0% | 0.0% | 0.0% | 93.8% | 1.4% | 0.7% |
| 2 | 83.3% | 8.3% | 8.3% | 0.0% | 100.0% | 4.2% | 2.1% |
| 4 | 70.8% | 16.7% | 16.7% | 0.0% | 100.0% | 5.6% | 2.8% |
| 8 | 66.7% | 16.7% | 16.7% | 0.0% | 100.0% | 4.9% | 2.4% |

Typed fidelity and authority metrics are deterministic and exclude free text. Behavioral rates pool all four conditions; condition-level rows are saved separately.

## Sampling versus selection

| k | Pool contains full-fidelity exact | Reviewer selects exact | Reviewer hits oracle-best | Mean selection regret | Reviewer failure |
|---:|---:|---:|---:|---:|---:|
| 1 | 41.7% | 41.7% | 100.0% | 0.000 fields | NA |
| 2 | 54.2% | 29.2% | 66.7% | 0.458 fields | 0.0% |
| 4 | 66.7% | 25.0% | 45.8% | 1.000 fields | 10.4% |
| 8 | 70.8% | 20.8% | 33.3% | 1.167 fields | 0.0% |

Generation uses the deterministic best typed memory available in each pool. Selection uses the actual reviewer choice, including the frozen fallback after review failure. Free-text oracle regret is undefined, and executor behavior is never used to define an oracle.

## Incremental typed mechanism

| k | Introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 6.2% | 100.0% | 0.0% | 25.0% |
| 2 | 3.7% | NA | NA | 16.7% |
| 4 | 9.6% | 100.0% | 0.0% | 41.7% |
| 8 | 9.4% | 100.0% | 0.0% | 41.7% |

Each mechanism row follows one reviewer-selected complete trajectory; states are never spliced across candidates.

## Diversity and lineage

| k | Candidate pairs | Distinct pairs | Newly added candidate selected |
|---:|---:|---:|---:|
| 1 | 0 | 0 | NA |
| 2 | 48 | 43 | 22/48 |
| 4 | 288 | 250 | 19/48 |
| 8 | 1344 | 1158 | 23/48 |

The nested-lineage audit verifies every inherited candidate exactly at each adjacent level.

## Cost

The non-reused TTC stages contain 2360 call records: 2337 successful and 23 failed. Provider-reported cost was $0.000000; saved-token reconstruction at frozen rates adds $3.490800, for $3.490800. 23 calls lacked usage metadata.
