# Procurement writer TTC — five-writer synthesis

Nested trajectory-level selected best-of-k across Qwen Plus, Nemotron 3 Ultra, Grok 4.3, Kimi K2.6, and GLM 5.2. GPT-OSS-120B is fixed as executor. Each writer reviews its own blinded candidates and selects one complete trajectory without rewriting or merging.

## Main outcomes

| k | Typed semantic fidelity | Typed authorization error | Typed apparent authority | Typed lost authority | Authorized use | Targeted unauthorized submission | Broader unsafe action |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 52.5% | 26.7% | 25.8% | 0.8% | 94.2% | 13.2% | 7.6% |
| 2 | 57.5% | 24.2% | 24.2% | 0.0% | 95.4% | 10.8% | 6.3% |
| 4 | 55.0% | 20.8% | 20.0% | 0.8% | 96.5% | 9.2% | 5.4% |
| 8 | 54.2% | 18.3% | 18.3% | 0.0% | 95.8% | 8.6% | 5.1% |

Typed metrics pool 120 deterministic final-memory observations per k. Behavioral metrics pool 1,440 GPT-OSS trials per k, equally split between authorized and unauthorized requests. All four memory conditions remain separate in the CSV tables before pooling.

## Memory format and writing mode

| Condition | Authorized use k=1 / 2 / 4 / 8 | Targeted unsafe k=1 / 2 / 4 / 8 | Broader unsafe k=1 / 2 / 4 / 8 |
|---|---:|---:|---:|
| One-shot free text | 94.4% / 96.1% / 96.1% / 96.7% | 0.0% / 1.1% / 2.2% / 0.6% | 0.0% / 1.1% / 1.7% / 0.6% |
| One-shot typed | 100.0% / 98.3% / 100.0% / 99.4% | 1.1% / 1.7% / 0.6% / 1.1% | 0.6% / 0.8% / 0.3% / 0.6% |
| Incremental free text | 84.4% / 87.8% / 91.1% / 87.8% | 20.6% / 12.2% / 10.0% / 10.6% | 13.9% / 8.9% / 6.9% / 7.8% |
| Incremental typed | 97.8% / 99.4% / 98.9% / 99.4% | 31.1% / 28.3% / 23.9% / 22.2% | 15.8% / 14.4% / 12.8% / 11.4% |

## Generation and selection

| k | Pool contains full-fidelity exact | Selected full-fidelity exact | Oracle-best field errors | Selected field errors | Selection regret | Review failure |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 31.7% | 31.7% | 1.775 | 1.775 | 0.000 | NA |
| 2 | 44.2% | 35.0% | 1.333 | 1.725 | 0.392 | 5.8% |
| 4 | 50.8% | 31.7% | 1.092 | 1.775 | 0.683 | 22.5% |
| 8 | 55.0% | 26.7% | 0.900 | 1.800 | 0.900 | 2.5% |

The oracle column measures whether more sampling makes a better typed memory available; the selected column measures whether practical self-review recovers it. Free-text oracle regret is undefined, and executor outcomes are never used as an oracle.

## Incremental typed mechanism

| k | Error introduction | Persistence | Self-repair | Final error |
|---:|---:|---:|---:|---:|
| 1 | 15.2% | 100.0% | 0.0% | 63.3% |
| 2 | 13.7% | 100.0% | 0.0% | 56.7% |
| 4 | 14.0% | 100.0% | 0.0% | 56.7% |
| 8 | 12.7% | 100.0% | 0.0% | 51.7% |

Each mechanism row follows the selected complete trajectory. Error persistence and self-repair are reported independently of final-state error.

## Safety–utility assessment at k=8

| Writer | Δ apparent authority vs k=1 | Δ authorized use | Δ targeted unsafe |
|---|---:|---:|---:|
| Qwen Plus | -8.3 pp | -2.1 pp | -3.5 pp |
| Nemotron 3 Ultra | -4.2 pp | +6.9 pp | +0.0 pp |
| Grok 4.3 | -8.3 pp | +1.4 pp | -6.9 pp |
| Kimi K2.6 | -12.5 pp | +4.9 pp | -7.6 pp |
| GLM 5.2 | -4.2 pp | -2.8 pp | -4.9 pp |

This is a descriptive paired scaling experiment over 12 fixed Procurement histories per condition and five writers. Writer, format, and writing-mode rows are preserved separately, and review fallbacks remain in denominators.

## Clean-stage cost

Across all five writer analyses, the non-reused TTC stages contain 11346 call records and cost $39.653796. Technical attempts excluded from scientific analysis are accounted separately in the experiment audit.
