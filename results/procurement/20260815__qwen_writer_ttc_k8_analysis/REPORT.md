# Procurement writer TTC — Qwen Plus

Writer/reviewer target: `qwen_plus_0728_openrouter`. Nested trajectory-level selected best-of-k with k=1, 2, 4, 8. The reviewer selected one complete trajectory without rewriting or merging and had no canonical oracle.

## Main results

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 50.0% | 29.2% | 29.2% | 0.0% | 95.1% | 15.3% | 9.7% |
| 2 | 58.3% | 25.0% | 25.0% | 0.0% | 90.3% | 13.2% | 9.4% |
| 4 | 50.0% | 25.0% | 20.8% | 4.2% | 91.0% | 10.4% | 8.3% |
| 8 | 54.2% | 20.8% | 20.8% | 0.0% | 93.1% | 11.8% | 8.3% |

Typed fidelity and authority metrics are deterministic and exclude free text. Behavioral rates pool all four conditions; condition-level rows are saved separately.

## Sampling versus selection

| k | Pool contains full-fidelity exact | Reviewer selects exact | Reviewer hits oracle-best | Mean selection regret | Reviewer failure |
|---:|---:|---:|---:|---:|---:|
| 1 | 25.0% | 25.0% | 100.0% | 0.000 fields | NA |
| 2 | 41.7% | 33.3% | 79.2% | 0.292 fields | 0.0% |
| 4 | 58.3% | 25.0% | 45.8% | 0.792 fields | 0.0% |
| 8 | 58.3% | 12.5% | 29.2% | 0.958 fields | 4.2% |

Generation uses the deterministic best typed memory available in each pool. Selection uses the actual reviewer choice, including the frozen fallback after review failure. Free-text oracle regret is undefined, and executor behavior is never used to define an oracle.

## Incremental typed mechanism

| k | Introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 10.6% | 100.0% | 0.0% | 50.0% |
| 2 | 9.6% | 100.0% | 0.0% | 41.7% |
| 4 | 13.3% | 100.0% | 0.0% | 58.3% |
| 8 | 11.1% | 100.0% | 0.0% | 50.0% |

Each mechanism row follows one reviewer-selected complete trajectory; states are never spliced across candidates.

## Diversity and lineage

| k | Candidate pairs | Distinct pairs | Newly added candidate selected |
|---:|---:|---:|---:|
| 1 | 0 | 0 | NA |
| 2 | 48 | 42 | 21/48 |
| 4 | 288 | 257 | 20/48 |
| 8 | 1344 | 1163 | 27/48 |

The nested-lineage audit verifies every inherited candidate exactly at each adjacent level.

## Cost

The non-reused TTC stages contain 2331 call records: 2331 successful and 0 failed. Provider-reported cost was $2.852974; saved-token reconstruction at frozen rates adds $0.254174, for $3.107148. 0 calls lacked usage metadata.
