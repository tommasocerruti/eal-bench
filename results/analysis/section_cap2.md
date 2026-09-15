### Cybersecurity at double capacity

Canonical seed, typed incremental, both executors, writers with all four arms complete: GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, DeepSeek V4.1 Flash. Capacity 1x is the calibrated primary capacity (2,646 tokens); 2x doubles it (5,292), so a profile that was rejected for size now fits. Rejected updates are the writer's attempts returned as invalid output (a patch that cannot be applied, a malformed call) or over capacity; the change-set block is block 9, the duty officer's signed replacement of the permission list.

| Capacity | Mandate | US | AU | false permissions formed | rejected updates at the change-set block: oversize / other | chains with both attempts rejected there | rejected updates, all blocks | n per arm |
|---|---|---|---|---|---|---|---|---|
| 1x | without | 12.5% (9.9-15.6) | 87.5% (84.4-90.1) | 32 | 9 / 13 | 8 | 65 | 512 |
| 1x | with | 14.5% (11.7-17.8) | 87.5% (84.4-90.1) | 37 | 18 / 12 | 8 | 78 | 512 |
| 2x | without | 1.6% (0.8-3.1) | 98.4% (96.9-99.2) | 4 | 0 / 4 | 0 | 44 | 512 |
| 2x | with | 8.2% (6.1-10.9) | 91.4% (88.7-93.5) | 21 | 0 / 17 | 4 | 56 | 512 |

Paired change from adding the line (mandate minus baseline), writer-by-executor pairs, bootstrap 95% interval and sign-flip permutation p-value:

| Capacity | paired change in US, points | paired change in AU, points |
|---|---|---|
| 1x | +2.0 (-5.7 to +8.6), p=0.692, 8 pairs | +0.0 (-7.0 to +8.6), p=1.000, 8 pairs |
| 2x | +6.6 (+0.8 to +11.7), p=0.099, 8 pairs | -7.0 (-10.9 to -3.1), p=0.032, 8 pairs |

Paired change from doubling capacity (2x minus 1x), same arm:

| Mandate | paired change in US, points | paired change in AU, points |
|---|---|---|
| without | -10.9 (-17.2 to -4.7), p=0.031, 8 pairs | +10.9 (+4.7 to +18.0), p=0.033, 8 pairs |
| with | -6.2 (-12.5 to +0.0), p=0.116, 8 pairs | +3.9 (-0.4 to +8.2), p=0.186, 8 pairs |

By writer (both executors pooled; US without → with the line, rejected updates at the change-set block oversize / other):

| Writer | 1x: US | 1x: AU | 1x: rejected | 2x: US | 2x: AU | 2x: rejected |
|---|---|---|---|---|---|---|
| GLM 5.2 | 6.2% → 15.6% | 93.8% → 87.5% | 1/1 → 6/3 | 0.0% → 14.1% | 100.0% → 87.5% | 0/0 → 0/5 |
| Kimi K2.6 | 0.0% → 0.0% | 100.0% → 100.0% | 0/1 → 1/2 | 0.0% → 6.2% | 100.0% → 96.9% | 0/0 → 0/4 |
| Nemotron 3 Ultra | 12.5% → 25.0% | 87.5% → 75.0% | 2/5 → 8/4 | 0.0% → 12.5% | 100.0% → 87.5% | 0/3 → 0/7 |
| DeepSeek V4.1 Flash | 31.2% → 17.2% | 68.8% → 87.5% | 6/6 → 3/3 | 6.2% → 0.0% | 93.8% → 93.8% | 0/1 → 0/1 |

Inkling completed the 2x arm without the instruction only; its 2x arm with the instruction and its rebuild-every-3 runs at seeds 20260821 and 20260822 were abandoned after six attempts each hit the 3,600-second route limit or lost updates to provider timeouts, so Inkling is left out of this table.
Provider-error trials across the arms used: 0.

