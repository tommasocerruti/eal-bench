# Procurement v1 writer–executor transfer results

## Scope

The frozen run used `benchmark_v1`, `naturalistic_v1`, seed `20260719`, the primary
capacity, one writer run, two bounded logical attempts, and the complete free-text/typed ×
one-shot/incremental factorial. Every completed writer memory was reused unchanged with
`gptoss_baseten` and `deepseek_baseten`; pressure made no writer or baseline calls.

Five qualified writer targets were attempted once in the preregistered order. Three completed the
original writer and exact-source pressure routes. Mistral and Kimi stopped before executor trials
for different technical reasons, and those outcomes remain preserved. A separately documented and
approved technical-completion pass then populated their missing writer–executor cells without
changing the frozen prompts, memory treatment, capacity, seed, attempts, or executor design.

## Route outcomes

| Writer | First attempt | Technical completion | Interpretation |
|---|---|---|---|
| Mistral Medium 3 | Hit the 3,600-second route limit before executor trials. | Writer and pressure completed. | Full-load writer reliability remained poor: 208/267 writer transports timed out. Its downstream behavior is reported but excluded from pooled memory-mechanism claims. |
| Nemotron 3 Ultra | Writer and pressure completed. | Not needed. | Complete, error-free behavioral route. |
| Grok 4.3 | Writer and pressure completed. | Not needed. | Complete, error-free behavioral route. |
| Kimi K2.6 | Memory generation completed, then incompatible post-processing rejected a valid profile before executor trials. | Writer and pressure completed with no provider errors. | Clean behavioral route after aligning deterministic validation with the active typed schema. |
| GLM 5.2 | Writer and pressure completed. | Not needed. | Complete, error-free behavioral route. |

The technical-completion pass did not remove, overwrite, or relabel either first outcome. Mistral's
route-level deadline was raised to 10,800 seconds while its 180-second per-call timeout and bounded
two-attempt policy remained fixed. The Kimi fix changed only deterministic post-writer validation.

## Ordinary behavior by writer and executor

Rates use 144 authorized and 144 unauthorized ordinary requests for every writer–executor pair.

| Writer | Executor | Baseline authorized use | Baseline unauthorized action | Pressure authorized use | Pressure unauthorized action |
|---|---|---:|---:|---:|---:|
| Mistral Medium 3 | DeepSeek V4 Pro | 37/144 (25.7%) | 42/144 (29.2%) | 20/144 (13.9%) | 69/144 (47.9%) |
| Mistral Medium 3 | GPT-OSS-120B | 27/144 (18.8%) | 24/144 (16.7%) | 12/144 (8.3%) | 20/144 (13.9%) |
| Nemotron 3 Ultra | DeepSeek V4 Pro | 138/144 (95.8%) | 11/144 (7.6%) | 128/144 (88.9%) | 12/144 (8.3%) |
| Nemotron 3 Ultra | GPT-OSS-120B | 133/144 (92.4%) | 12/144 (8.3%) | 73/144 (50.7%) | 11/144 (7.6%) |
| Grok 4.3 | DeepSeek V4 Pro | 137/144 (95.1%) | 23/144 (16.0%) | 115/144 (79.9%) | 22/144 (15.3%) |
| Grok 4.3 | GPT-OSS-120B | 138/144 (95.8%) | 22/144 (15.3%) | 79/144 (54.9%) | 22/144 (15.3%) |
| Kimi K2.6 | DeepSeek V4 Pro | 134/144 (93.1%) | 19/144 (13.2%) | 118/144 (81.9%) | 20/144 (13.9%) |
| Kimi K2.6 | GPT-OSS-120B | 134/144 (93.1%) | 20/144 (13.9%) | 79/144 (54.9%) | 20/144 (13.9%) |
| GLM 5.2 | DeepSeek V4 Pro | 140/144 (97.2%) | 20/144 (13.9%) | 120/144 (83.3%) | 21/144 (14.6%) |
| GLM 5.2 | GPT-OSS-120B | 136/144 (94.4%) | 19/144 (13.2%) | 78/144 (54.2%) | 19/144 (13.2%) |

For the four operationally reliable writers, the two executors transfer similarly on unsafe-action
rates for the same memories. Under pressure, GPT-OSS becomes substantially more conservative than
DeepSeek on authorized requests.

## Aggregate results and mechanism

| Writer | Baseline authorized use | Baseline unauthorized action | Pressure authorized use | Pressure unauthorized action |
|---|---:|---:|---:|---:|
| Mistral Medium 3 | 64/288 (22.2%) | 66/288 (22.9%) | 32/288 (11.1%) | 89/288 (30.9%) |
| Nemotron 3 Ultra | 271/288 (94.1%) | 23/288 (8.0%) | 201/288 (69.8%) | 23/288 (8.0%) |
| Grok 4.3 | 275/288 (95.5%) | 45/288 (15.6%) | 194/288 (67.4%) | 44/288 (15.3%) |
| Kimi K2.6 | 268/288 (93.1%) | 39/288 (13.5%) | 197/288 (68.4%) | 40/288 (13.9%) |
| GLM 5.2 | 276/288 (95.8%) | 39/288 (13.5%) | 198/288 (68.8%) | 40/288 (13.9%) |

Across Nemotron, Grok, Kimi, and GLM, baseline authorized use was 1,090/1,152 (94.6%) and
unauthorized action was 146/1,152 (12.7%). Under pressure, authorized use fell to 790/1,152
(68.6%), while unauthorized action was nearly unchanged at 147/1,152 (12.8%). Mistral is excluded
from this pooled comparison because its writer transport failures caused widespread missing or
retained profiles rather than a clean generated-memory treatment.

For the four reliable writers, every ordinary baseline unauthorized action occurred in an
incremental memory condition. Both one-shot conditions were 0% unsafe. The incremental unsafe
rates, pooled across executors, were:

| Writer | Incremental free text | Incremental typed |
|---|---:|---:|
| Nemotron 3 Ultra | 0/72 (0.0%) | 23/72 (31.9%) |
| Grok 4.3 | 18/72 (25.0%) | 27/72 (37.5%) |
| Kimi K2.6 | 12/72 (16.7%) | 27/72 (37.5%) |
| GLM 5.2 | 19/72 (26.4%) | 20/72 (27.8%) |

Deterministically selected substantive typed-memory errors produced unauthorized action in 54/54
executor trials across the four reliable writers, versus 0/54 after exact canonical repair.
Pressure preserved the same 54/54 versus 0/54 contrast. This is the clearest mechanism evidence:
changing only the stored authorization state reverses the unsafe action while holding the request,
executor route, and presentation fixed.

Pressure chiefly reduced authorized use rather than increasing unauthorized action. For the four
reliable writers, the pooled unauthorized-action rate changed by only 0.1 percentage points, while
authorized use fell by 26.0 points. Mistral differs: pressure increased unauthorized action from
22.9% to 30.9%, but that result is entangled with severe writer transport failure and should not be
used as clean evidence about memory-error susceptibility.

## Manifest correction for pressure replay

The original completed two-executor writer manifests stored `planned_ordinary_executor_jobs: 288`,
the per-target count, although each run contains 576 ordinary trials across two frozen targets.
Raw runs remain unchanged. Each affected pressure route uses a separate correction copy that
changes only the top-level counter to 576, records the original manifest SHA-256, and keeps every
mapped artifact file byte-identical to the original. The completion routes use the corrected
multi-executor accounting directly. Every pressure source passes offline validation.

## Cost

The original routes produced 4,548 call records and an estimated USD 15.23764962. The separately
approved technical-completion pass produced 2,803 records and cost an estimated USD 7.42484339:
OpenRouter reported USD 0.05443672 for successful Mistral calls, and recorded Baseten token usage
gives USD 7.37040667 at the frozen rates. The combined 7,351 records are estimated at USD
22.66249301. The completion pass stayed below its USD 12 cap, and the original pass stayed below
its USD 31 cap.
