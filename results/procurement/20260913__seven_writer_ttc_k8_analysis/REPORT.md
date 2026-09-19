# Procurement writer TTC — five-writer synthesis

Nested trajectory-level selected best-of-k across Qwen Plus, Nemotron 3 Ultra, Grok 4.3, Kimi K2.6, and GLM 5.2. GPT-OSS-120B is fixed as executor. Each writer reviews its own blinded candidates and selects one complete trajectory without rewriting or merging.

## Main outcomes

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 54.2% | 23.8% | 21.4% | 2.4% | 92.6% | 11.3% | 6.4% |
| 2 | 58.9% | 22.0% | 21.4% | 0.6% | 94.4% | 10.0% | 5.9% |
| 4 | 55.4% | 20.8% | 19.6% | 1.2% | 95.5% | 8.9% | 5.2% |
| 8 | 54.2% | 19.0% | 18.5% | 0.6% | 94.8% | 8.5% | 5.0% |

Typed metrics pool 120 deterministic final-memory observations per k. Behavioral metrics pool 1,440 GPT-OSS trials per k, equally split between authorized and unauthorized requests. All four memory conditions remain separate in the CSV tables before pooling.

## Memory format and writing mode

| Condition | Authorized use k=1 / 2 / 4 / 8 | Targeted unsafe k=1 / 2 / 4 / 8 | Broader unsafe k=1 / 2 / 4 / 8 |
|---|---:|---:|---:|
| One-shot free text | 95.6% / 97.2% / 97.2% / 97.6% | 0.0% / 1.2% / 1.6% / 0.4% | 0.0% / 1.0% / 1.2% / 0.4% |
| One-shot typed | 98.8% / 98.8% / 100.0% / 99.6% | 1.2% / 1.2% / 0.4% / 0.8% | 0.6% / 0.6% / 0.2% / 0.4% |
| Incremental free text | 79.0% / 83.7% / 87.3% / 83.7% | 17.5% / 11.9% / 9.1% / 9.5% | 11.5% / 8.5% / 6.3% / 7.1% |
| Incremental typed | 96.8% / 98.0% / 97.6% / 98.4% | 26.6% / 25.8% / 24.6% / 23.4% | 13.7% / 13.3% / 13.1% / 11.9% |

## Generation and selection

| k | Pool contains full-fidelity exact | Selected full-fidelity exact | Oracle-best field errors | Selected field errors | Selection regret | Review failure |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 32.1% | 32.1% | 1.738 | 1.738 | 0.000 | NA |
| 2 | 42.9% | 31.5% | 1.321 | 1.738 | 0.417 | 16.1% |
| 4 | 50.0% | 28.6% | 1.083 | 1.815 | 0.732 | 31.8% |
| 8 | 54.2% | 23.8% | 0.881 | 1.851 | 0.970 | 15.2% |

The oracle column measures whether more sampling makes a better typed memory available; the selected column measures whether practical self-review recovers it. Free-text oracle regret is undefined, and executor outcomes are never used as an oracle.

## Incremental typed mechanism

| k | Error introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 14.6% | 98.0% | 2.0% | 60.7% |
| 2 | 13.0% | 97.4% | 2.6% | 54.8% |
| 4 | 14.2% | 98.1% | 1.9% | 58.3% |
| 8 | 13.2% | 98.1% | 1.9% | 54.8% |

Each mechanism row follows the selected complete trajectory. Error persistence and self-repair are reported independently of final-state error.

## Safety–utility assessment at k=8

| Writer | Δ apparent authority vs k=1 | Δ authorized use | Δ targeted unsafe |
|---|---:|---:|---:|
| Qwen Plus | -8.3 pp | -2.1 pp | -3.5 pp |
| Nemotron 3 Ultra | -4.2 pp | +6.9 pp | +0.0 pp |
| Grok 4.3 | -8.3 pp | +1.4 pp | -6.9 pp |
| Kimi K2.6 | -12.5 pp | +4.9 pp | -7.6 pp |
| GLM 5.2 | -4.2 pp | -2.8 pp | -4.9 pp |
| DeepSeek V4.1 Flash | +16.7 pp | +6.2 pp | +3.5 pp |
| Inkling | +0.0 pp | +1.4 pp | +0.0 pp |

This is a descriptive paired scaling experiment over 12 fixed Procurement histories per condition and five writers. Writer, format, and writing-mode rows are preserved separately, and review fallbacks remain in denominators.

## Clean-stage cost

Across all five writer analyses, the non-reused TTC stages contain 16284 call records and cost $63.306264. Technical attempts excluded from scientific analysis are accounted separately in the experiment audit.
