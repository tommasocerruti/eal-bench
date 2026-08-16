# Cybersecurity v1 writer-transfer results

## Design

Five writers generated memories once for the frozen 16-family Cybersecurity v1 corpus. The exact
same memories were evaluated by GPT-OSS and DeepSeek at baseline and then replayed under
`financial_urgency_v1`. All ten writer-executor combinations completed without executor provider
errors or outcome-based reruns.

The primary unsafe metric is submission of the requested action when that submitted request is
canonically unauthorized. The supplemental all-action metric additionally counts a different
terminal action, such as the operational alternative, when that action is also unauthorized.

## Ordinary outcomes

| Writer | Baseline authorized use | Baseline unauthorized submission | Pressure authorized use | Pressure unauthorized submission | Pressure any unauthorized action |
|---|---:|---:|---:|---:|---:|
| Nemotron 3 Ultra | 488/512 (95.3%) | 24/512 (4.7%) | 400/512 (78.1%) | 23/512 (4.5%) | 69/512 (13.5%) |
| Grok 4.3 | 481/512 (93.9%) | 5/512 (1.0%) | 414/512 (80.9%) | 9/512 (1.8%) | 59/512 (11.5%) |
| Kimi K2.6 | 504/512 (98.4%) | 8/512 (1.6%) | 415/512 (81.1%) | 8/512 (1.6%) | 59/512 (11.5%) |
| GLM 5.2 | 504/512 (98.4%) | 8/512 (1.6%) | 421/512 (82.2%) | 7/512 (1.4%) | 48/512 (9.4%) |
| Qwen Plus 2025-07-28 | 446/512 (87.1%) | 53/512 (10.4%) | 384/512 (75.0%) | 44/512 (8.6%) | 106/512 (20.7%) |
| **Pooled** | **2,423/2,560 (94.6%)** | **98/2,560 (3.8%)** | **2,034/2,560 (79.5%)** | **91/2,560 (3.6%)** | **341/2,560 (13.3%)** |

Qwen is the clearest difficult writer: its baseline unauthorized-submission rate is 10.4%, driven
primarily by incremental typed memory. Across all writers, incremental updates produced 87/1,280
unauthorized submissions (6.8%), versus 11/1,280 (0.9%) for one-shot memory.

The 98 baseline failures cover every designed mechanism: 27 cross-record, 23 late-narrowing, 23
revoked-action, and 25 time-shift trials. Qwen's failures span seven families and Nemotron's span
three; the smaller Grok, Kimi, and GLM effects are more family-localized.

## Memory mechanism

The deterministic selector found 30 distinct substantive typed-memory witnesses. Each witness was
shown to both executors. At baseline, natural erroneous memory caused the predicted unauthorized
submission in 60/60 trials; exact canonical repair reduced this to 0/60. The two executors agreed
on 1,274/1,280 paired baseline unauthorized-request decisions (99.5%).

One repaired baseline trial selected a different canonically unauthorized operational alternative,
so the supplemental any-unauthorized-action result is 1/60 after repair. This does not change the
0/60 result for the witness-causal submitted action and is retained rather than rescored or
removed.

Typed checkpoint scoring found many more non-exact incremental fields than one-shot fields for
every writer: Nemotron 79 vs 0, Grok 100 vs 2, Kimi 92 vs 0, GLM 104 vs 1, and Qwen 127 vs 2.
Together with the intervention and executor-agreement results, this supports the intended
memory-mediated attribution.

## Pressure interpretation

Pressure does not amplify the primary stale-memory submission rate in the pooled matrix: it moves
from 98/2,560 (3.8%) to 91/2,560 (3.6%). It does, however, cause many agents to switch to the
operational alternative, raising the supplemental any-unauthorized-action rate to 341/2,560
(13.3%) and reducing authorized use to 79.5%.

This effect is strongly executor-specific. Under pressure, DeepSeek retains 1,220/1,280 authorized
uses (95.3%) and takes any unauthorized action in 106/1,280 unauthorized-request trials (8.3%).
GPT-OSS falls to 814/1,280 authorized uses (63.6%) and takes any unauthorized action in 235/1,280
trials (18.4%). The pressure result therefore exposes an additional executor-policy effect; it
should not be presented as amplification of the central stale-memory submission mechanism.

## Comparison with procurement

Procurement is harder at baseline: 189/1,440 unauthorized submissions (13.1%) versus 98/2,560
(3.8%) in cybersecurity. Both domains have almost identical baseline authorized use—94.9% and
94.6%—and both show a large incremental-versus-one-shot gap.

The direct memory intervention is especially consistent across domains: procurement produced
66/68 predicted unsafe submissions with natural errors and 0/68 after repair; cybersecurity
produced 60/60 and 0/60. Pressure behaves differently: procurement mainly reduces authorized use
while leaving unsafe submission unchanged, whereas cybersecurity redirects many actions toward a
different operational course. The cross-domain result therefore supports a shared endogenous
memory-failure mechanism plus domain- and executor-specific pressure responses.

## Technical and cost record

The matrix made 12,341 calls. Four writer calls failed at the provider layer: two Kimi HTTP 500s,
and one GLM logical update whose first attempt returned HTTP 500 and second attempt timed out.
Every route still completed, all executor calls succeeded, and every pressure source-job hash
matches its writer source exactly.

Actual matrix cost was USD 64.4890 under the approved USD 85 cap: USD 5.1314 was reported by
OpenRouter and USD 59.3577 was derived from recorded Baseten token usage at the frozen rates.
