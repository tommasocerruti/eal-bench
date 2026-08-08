# Procurement v1 writer–executor transfer results

## Scope

The frozen run used `benchmark_v1`, `naturalistic_v1`, seed `20260719`, the primary
capacity, one writer run, two bounded logical attempts, and the complete free-text/typed ×
one-shot/incremental factorial. Every completed writer memory was reused unchanged with
`gptoss_baseten` and `deepseek_baseten`; pressure made no writer or baseline calls.

Five qualified writer targets were attempted once in the preregistered order. Three completed the
writer and exact-source pressure routes. Two produced preserved technical failures before any
executor trial, so the intended 5×2 behavioral matrix is incomplete and must not be reported as a
complete five-writer comparison.

## Route outcomes

| Writer | Writer route | Pressure route | Technical outcome |
|---|---:|---:|---|
| Mistral Medium 3 | Failed | Not run | Hit the frozen 3,600-second route limit after 230 transport attempts: 67 successes and 163 timeouts. |
| Nemotron 3 Ultra | Completed | Completed | 184 writer calls, 604 baseline trials, and 604 exact-source pressure trials; no provider errors. |
| Grok 4.3 | Completed | Completed | 157 writer calls, 600 baseline trials, and 600 exact-source pressure trials; no provider errors. |
| Kimi K2.6 | Failed | Not run | Memory calls completed, but frozen post-writer witness construction rejected a typed profile with more than 32 source IDs; no executor trial ran. |
| GLM 5.2 | Completed | Completed | 202 writer calls, 600 baseline trials, and 600 exact-source pressure trials; no provider errors. |

The Mistral and Kimi failures were retained without rerunning, replacing, or removing either
target. Pressure was not attempted without a complete writer source.

## Ordinary behavior by writer and executor

Rates use 144 authorized and 144 unauthorized ordinary requests for every completed
writer–executor pair.

| Writer | Executor | Baseline authorized use | Baseline unauthorized action | Pressure authorized use | Pressure unauthorized action |
|---|---|---:|---:|---:|---:|
| Nemotron 3 Ultra | DeepSeek V4 Pro | 138/144 (95.8%) | 11/144 (7.6%) | 128/144 (88.9%) | 12/144 (8.3%) |
| Nemotron 3 Ultra | GPT-OSS-120B | 133/144 (92.4%) | 12/144 (8.3%) | 73/144 (50.7%) | 11/144 (7.6%) |
| Grok 4.3 | DeepSeek V4 Pro | 137/144 (95.1%) | 23/144 (16.0%) | 115/144 (79.9%) | 22/144 (15.3%) |
| Grok 4.3 | GPT-OSS-120B | 138/144 (95.8%) | 22/144 (15.3%) | 79/144 (54.9%) | 22/144 (15.3%) |
| GLM 5.2 | DeepSeek V4 Pro | 140/144 (97.2%) | 20/144 (13.9%) | 120/144 (83.3%) | 21/144 (14.6%) |
| GLM 5.2 | GPT-OSS-120B | 136/144 (94.4%) | 19/144 (13.2%) | 78/144 (54.2%) | 19/144 (13.2%) |

The two executors transfer similarly on unsafe action rates for the same memories. Under pressure,
GPT-OSS becomes substantially more conservative than DeepSeek on authorized requests.

## Aggregate results and mechanism

| Writer | Baseline authorized use | Baseline unauthorized action | Pressure authorized use | Pressure unauthorized action |
|---|---:|---:|---:|---:|
| Nemotron 3 Ultra | 271/288 (94.1%) | 23/288 (8.0%) | 201/288 (69.8%) | 23/288 (8.0%) |
| Grok 4.3 | 275/288 (95.5%) | 45/288 (15.6%) | 194/288 (67.4%) | 44/288 (15.3%) |
| GLM 5.2 | 276/288 (95.8%) | 39/288 (13.5%) | 198/288 (68.8%) | 40/288 (13.9%) |

Across all three completed writers, ordinary baseline unauthorized actions occurred only in
incremental memory conditions. Both one-shot conditions were 0% unsafe for every completed writer.
The incremental unsafe rates, pooled across executors, were:

| Writer | Incremental free text | Incremental typed |
|---|---:|---:|
| Nemotron 3 Ultra | 0/72 (0.0%) | 23/72 (31.9%) |
| Grok 4.3 | 18/72 (25.0%) | 27/72 (37.5%) |
| GLM 5.2 | 19/72 (26.4%) | 20/72 (27.8%) |

Deterministically selected substantive typed-memory errors produced unauthorized action in 38/38
executor trials across the three writers, versus 0/38 after exact canonical repair. Pressure did
not change either witness result. This is the clearest mechanism evidence: changing only the
stored authorization state reverses the unsafe action while holding the request, executor route,
and presentation fixed.

Pressure chiefly reduced authorized use rather than increasing unauthorized action. Aggregate
unauthorized-action changes were 0.0 percentage points for Nemotron, −0.35 points for Grok, and
0.35 points for GLM; authorized use fell by 24.3, 28.1, and 27.1 points respectively.

## Manifest correction for pressure replay

The completed two-executor writer manifests stored `planned_ordinary_executor_jobs: 288`, the
per-target count, although each run contains 576 ordinary trials across two frozen targets. Raw
runs remain unchanged. Each pressure route uses a separate correction copy that changes only the
top-level counter to 576, records the original manifest SHA-256, and keeps every mapped artifact
file byte-identical to the original. All three corrected sources pass offline pressure validation.

## Cost

The eight attempted routes produced 4,548 call records. OpenRouter reported USD 1.10934481.
Baseten does not return `usage.cost`; applying the preregistered public rates to recorded prompt,
cached-input, and completion tokens gives USD 14.12830481. The combined non-authoritative total is
USD 15.23764962, below the approved USD 31 cap.
