# Procurement writer TTC — Grok 4.3

Writer/reviewer target: `grok_4_3_openrouter`. Nested trajectory-level selected best-of-k with k=1, 2, 4, 8. The reviewer selected one complete trajectory without rewriting or merging and had no canonical oracle.

## Main results

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 54.2% | 25.0% | 25.0% | 0.0% | 95.8% | 15.3% | 8.3% |
| 2 | 58.3% | 20.8% | 20.8% | 0.0% | 95.1% | 10.4% | 6.2% |
| 4 | 62.5% | 16.7% | 16.7% | 0.0% | 97.9% | 8.3% | 4.9% |
| 8 | 62.5% | 16.7% | 16.7% | 0.0% | 97.2% | 8.3% | 4.9% |

Typed fidelity and authority metrics are deterministic and exclude free text. Behavioral rates pool all four conditions; condition-level rows are saved separately.

## Sampling versus selection

| k | Pool contains full-fidelity exact | Reviewer selects exact | Reviewer hits oracle-best | Mean selection regret | Reviewer failure |
|---:|---:|---:|---:|---:|---:|
| 1 | 41.7% | 41.7% | 100.0% | 0.000 fields | NA |
| 2 | 54.2% | 50.0% | 83.3% | 0.167 fields | 12.5% |
| 4 | 58.3% | 50.0% | 66.7% | 0.333 fields | 8.3% |
| 8 | 58.3% | 50.0% | 66.7% | 0.333 fields | 6.2% |

Generation uses the deterministic best typed memory available in each pool. Selection uses the actual reviewer choice, including the frozen fallback after review failure. Free-text oracle regret is undefined, and executor behavior is never used to define an oracle.

## Incremental typed mechanism

| k | Introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 16.3% | 100.0% | 0.0% | 66.7% |
| 2 | 14.0% | 100.0% | 0.0% | 58.3% |
| 4 | 12.5% | 100.0% | 0.0% | 50.0% |
| 8 | 12.5% | 100.0% | 0.0% | 50.0% |

Each mechanism row follows one reviewer-selected complete trajectory; states are never spliced across candidates.

## Diversity and lineage

| k | Candidate pairs | Distinct pairs | Newly added candidate selected |
|---:|---:|---:|---:|
| 1 | 0 | 0 | NA |
| 2 | 48 | 37 | 22/48 |
| 4 | 288 | 218 | 23/48 |
| 8 | 1344 | 998 | 23/48 |

The nested-lineage audit verifies every inherited candidate exactly at each adjacent level.

## Cost

The non-reused TTC stages contain 2112 call records: 2112 successful and 0 failed. Provider-reported cost was $8.897622; saved-token reconstruction at frozen rates adds $0.234219, for $9.131841. 0 calls lacked usage metadata.
