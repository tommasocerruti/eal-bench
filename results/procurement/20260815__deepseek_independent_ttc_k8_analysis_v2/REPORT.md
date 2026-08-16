# Procurement TTC — independent DeepSeek selection

DeepSeek V4 Pro reviewed the exact frozen k=2, 4, 8 candidate pools used by each writer's self-review. It saw the same blinded candidates, visible history, tool schema, and candidate order, and selected one existing trajectory without rewriting or oracle information. GPT-OSS-120B remained fixed as executor.

## Selection on typed memory

| k | Method | Exact memory | Oracle hit | Regret (fields) | Authorization error | Apparent authority | Review failure |
|---:|---|---:|---:|---:|---:|---:|---:|
| 2 | Writer self-review | 35.0% | 79.2% | 0.392 | 24.2% | 24.2% | 3.3% |
| 2 | DeepSeek review | 35.8% | 80.8% | 0.367 | 24.2% | 24.2% | 2.5% |
| 2 | Deterministic oracle | 44.2% | 100.0% | 0.000 | 22.5% | 22.5% | NA |
| 4 | Writer self-review | 31.7% | 60.0% | 0.683 | 20.8% | 20.0% | 21.7% |
| 4 | DeepSeek review | 33.3% | 60.8% | 0.633 | 19.2% | 18.3% | 34.2% |
| 4 | Deterministic oracle | 50.8% | 100.0% | 0.000 | 17.5% | 17.5% | NA |
| 8 | Writer self-review | 26.7% | 47.5% | 0.900 | 18.3% | 18.3% | 2.5% |
| 8 | DeepSeek review | 30.0% | 52.5% | 0.900 | 19.2% | 16.7% | 5.8% |
| 8 | Deterministic oracle | 55.0% | 100.0% | 0.000 | 14.2% | 14.2% | NA |

## Downstream behavior on typed memory

| k | Method | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---|---:|---:|---:|
| 2 | Writer self-review | 98.9% | 15.0% | 7.6% |
| 2 | DeepSeek review | 100.0% | 15.0% | 7.5% |
| 2 | Deterministic oracle | 99.7% | 13.9% | 7.1% |
| 4 | Writer self-review | 99.4% | 12.2% | 6.5% |
| 4 | DeepSeek review | 98.6% | 11.9% | 6.1% |
| 4 | Deterministic oracle | 99.2% | 10.6% | 5.7% |
| 8 | Writer self-review | 99.4% | 11.7% | 6.0% |
| 8 | DeepSeek review | 98.9% | 10.6% | 5.4% |
| 8 | Deterministic oracle | 99.4% | 8.1% | 4.3% |

The oracle arm is defined only for typed memory. Its executor table combines newly replayed oracle-selected candidates with the frozen self-review trial whenever both selectors chose the same candidate; all requests, seeds, and executor settings are unchanged.

## All-condition self versus independent review

| k | Method | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---|---:|---:|---:|
| 2 | Writer self-review | 95.4% | 10.8% | 6.3% |
| 2 | DeepSeek review | 98.2% | 11.4% | 6.5% |
| 4 | Writer self-review | 96.5% | 9.2% | 5.4% |
| 4 | DeepSeek review | 96.4% | 8.8% | 5.3% |
| 8 | Writer self-review | 95.8% | 8.6% | 5.1% |
| 8 | DeepSeek review | 97.2% | 7.6% | 4.5% |

## Review agreement and successful-review sensitivity

| k | Same candidate | DeepSeek lower error | Self-review lower error |
|---:|---:|---:|---:|
| 2 | 62.5% | 3.3% | 1.7% |
| 4 | 60.8% | 5.8% | 5.0% |
| 8 | 58.3% | 12.5% | 11.7% |

| k | Method | Successful typed reviews | Exact memory | Oracle hit | Regret (fields) |
|---:|---|---:|---:|---:|---:|
| 2 | Writer self-review | 116 | 36.2% | 80.2% | 0.362 |
| 2 | DeepSeek review | 117 | 36.8% | 80.3% | 0.376 |
| 4 | Writer self-review | 94 | 39.4% | 63.8% | 0.543 |
| 4 | DeepSeek review | 79 | 45.6% | 64.6% | 0.570 |
| 8 | Writer self-review | 117 | 26.5% | 47.0% | 0.915 |
| 8 | DeepSeek review | 113 | 31.9% | 53.1% | 0.885 |

## Interpretation

The deterministic oracle isolates candidate generation from selection. Comparing the two practical reviewers against that ceiling shows whether the bottleneck is specific to writer self-review or remains under independent review. Failed reviews use the preregistered frozen self-selection fallback and remain in every denominator.

Across all conditions, review failures were:

| k | Method | Failures | Reviewed pools | Failure rate |
|---:|---|---:|---:|---:|
| 2 | Writer self-review | 14 | 240 | 5.8% |
| 2 | DeepSeek review | 4 | 240 | 1.7% |
| 4 | Writer self-review | 54 | 240 | 22.5% |
| 4 | DeepSeek review | 63 | 240 | 26.2% |
| 8 | Writer self-review | 6 | 240 | 2.5% |
| 8 | DeepSeek review | 8 | 240 | 3.3% |

Free-text oracle regret and oracle behavior are undefined because no deterministic semantic oracle exists for free text. Executor outcomes were never used to choose a candidate.

## Cost and audit

The independent-review and typed-oracle runs contain 6524 call records and cost $11.609292. They include 77 error records, retained under the frozen failure policy.
