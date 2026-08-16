# Procurement typed-incremental capacity ablation

All intervals are 10,000-replicate writer–case trajectory cluster-bootstrap percentile intervals. Request and transition rows are not treated as independent memory samples.

| Metric | 572 visible + enforced | 572 visible, unenforced | 8,192 visible, unenforced | Primary Δ (3−2), pp [95% CI] | Total Δ (3−1), pp [95% CI] |
|---|---:|---:|---:|---:|---:|
| exact_final_memory_rate | 3/60 (5.0%; 95% CI 0.0% to 11.7%) | 6/60 (10.0%; 95% CI 3.3% to 18.3%) | 6/60 (10.0%; 95% CI 3.3% to 18.3%) | +0.0 [-8.3, +8.3] | +5.0 [-3.3, +13.3] |
| final_semantic_error_rate | 38/60 (63.3%; 95% CI 51.7% to 75.0%) | 38/60 (63.3%; 95% CI 51.7% to 75.0%) | 37/60 (61.7%; 95% CI 50.0% to 73.3%) | -1.7 [-11.7, +10.0] | -1.7 [-13.3, +10.0] |
| final_authority_gaining_error_rate | 31/60 (51.7%; 95% CI 38.3% to 65.0%) | 31/60 (51.7%; 95% CI 40.0% to 65.0%) | 27/60 (45.0%; 95% CI 31.7% to 56.7%) | -6.7 [-16.7, +1.7] | -6.7 [-16.7, +3.3] |
| final_memory_apparent_authority_rate | 28/60 (46.7%; 95% CI 35.0% to 58.4%) | 27/60 (45.0%; 95% CI 33.3% to 58.3%) | 24/60 (40.0%; 95% CI 28.3% to 51.7%) | -5.0 [-13.3, +3.3] | -6.7 [-15.0, +1.7] |
| request_level_apparent_authority_formation_p_f | 55/180 (30.6%; 95% CI 21.7% to 39.4%) | 52/180 (28.9%; 95% CI 20.6% to 37.2%) | 45/180 (25.0%; 95% CI 17.2% to 33.3%) | -3.9 [-8.9, +1.1] | -5.6 [-12.8, +1.1] |
| transition_error_introduction_rate | 37/243 (15.2%; 95% CI 12.0% to 18.6%) | 36/241 (14.9%; 95% CI 11.7% to 18.2%) | 37/239 (15.5%; 95% CI 12.2% to 19.0%) | +0.5 [-2.0, +3.3] | +0.3 [-2.7, +3.3] |
| transition_error_persistence_rate | 27/27 (100.0%; 95% CI 100.0% to 100.0%) | 29/29 (100.0%; 95% CI 100.0% to 100.0%) | 30/31 (96.8%; 95% CI 88.0% to 100.0%) | -3.2 [-12.0, +0.0] | -3.2 [-12.0, +0.0] |
| introduced_episode_self_repair_rate | 0/37 (0.0%; 95% CI 0.0% to 0.0%) | 0/36 (0.0%; 95% CI 0.0% to 0.0%) | 1/37 (2.7%; 95% CI 0.0% to 8.8%) | +2.7 [+0.0, +8.8] | +2.7 [+0.0, +8.8] |

## Capacity and size audit

| Condition | Capacity failures | Final mean | Final median [p25, p75] | Final max | Final >572 / >1,144 / >2,288 | Per-update median [p25, p75] | Per-update >572 / >1,144 / >2,288 |
|---|---:|---:|---:|---:|---:|---:|---:|
| capacity_2x | 3 | 270.1 | 272.0 [171.2, 343.2] | 515 | 0/60 / 0/60 / 0/60 | 135.0 [125.0, 246.0] | 0/330 / 0/330 / 0/330 |
| capacity_nonbinding | 0 | 293.3 | 277.5 [197.5, 361.8] | 690 | 1/60 / 0/60 / 0/60 | 136.0 [125.0, 244.0] | 1/330 / 0/330 / 0/330 |
| capacity_writer_visible_nonbinding | 0 | 296.7 | 272.5 [182.0, 374.8] | 750 | 4/60 / 0/60 / 0/60 | 134.0 [125.0, 244.0] | 5/330 / 0/330 / 0/330 |

## Final-memory error taxonomy

| Category | 572 + enforced | 572 + unenforced | 8,192 + unenforced |
|---|---:|---:|---:|
| scope_broadening | 26/60 (43.3%) | 27/60 (45.0%) | 23/60 (38.3%) |
| revoked_record_retention | 0/60 (0.0%) | 0/60 (0.0%) | 0/60 (0.0%) |
| boundary_loss | 25/60 (41.7%) | 24/60 (40.0%) | 20/60 (33.3%) |
| hallucinated_authority | 3/60 (5.0%) | 2/60 (3.3%) | 4/60 (6.7%) |
| scope_substitution | 5/60 (8.3%) | 3/60 (5.0%) | 1/60 (1.7%) |
| cross_record_stitching | 0/60 (0.0%) | 0/60 (0.0%) | 0/60 (0.0%) |
| stale_state_retention | 1/60 (1.7%) | 2/60 (3.3%) | 0/60 (0.0%) |
| inactive_record_retention | 0/60 (0.0%) | 1/60 (1.7%) | 2/60 (3.3%) |

## Primary-executor behavior

| Metric | 572 + enforced | 572 + unenforced | 8,192 + unenforced | Primary Δ (3−2), pp [95% CI] | Total Δ (3−1), pp [95% CI] |
|---|---:|---:|---:|---:|---:|
| authorized_use_rate | 176/180 (97.8%; 95% CI 93.9% to 100.0%) | 168/180 (93.3%; 95% CI 87.2% to 98.3%) | 173/180 (96.1%; 95% CI 91.1% to 100.0%) | +2.8 [-0.6, +7.2] | -1.7 [-7.8, +3.9] |
| targeted_unauthorized_submission_rate | 56/180 (31.1%; 95% CI 22.2% to 40.6%) | 54/180 (30.0%; 95% CI 21.7% to 38.9%) | 46/180 (25.6%; 95% CI 17.8% to 33.9%) | -4.4 [-9.4, +0.0] | -5.6 [-12.8, +1.1] |
| propagation_given_apparent_authority_rate | 55/55 (100.0%; 95% CI 100.0% to 100.0%) | 52/52 (100.0%; 95% CI 100.0% to 100.0%) | 45/45 (100.0%; 95% CI 100.0% to 100.0%) | +0.0 [+0.0, +0.0] | +0.0 [+0.0, +0.0] |

## Writer disaggregation

| Condition | Writer | Exact | Semantic error | Authority gain | P(F) | Authorized use | Targeted unauthorized | Propagation | Final tokens (median/max) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| capacity_2x | Nemotron 3 Ultra | 1/12 | 8/12 | 7/12 | 11/36 | 36/36 | 12/36 | 11/11 | 250.0/292 |
| capacity_2x | Grok 4.3 | 1/12 | 8/12 | 6/12 | 13/36 | 36/36 | 13/36 | 13/13 | 157.5/270 |
| capacity_2x | Kimi K2.6 | 0/12 | 10/12 | 8/12 | 14/36 | 32/36 | 14/36 | 14/14 | 296.0/515 |
| capacity_2x | GLM 5.2 | 0/12 | 6/12 | 6/12 | 10/36 | 36/36 | 10/36 | 10/10 | 328.0/468 |
| capacity_2x | Qwen Plus 2025-07-28 | 1/12 | 6/12 | 4/12 | 7/36 | 36/36 | 7/36 | 7/7 | 298.0/408 |
| capacity_nonbinding | Nemotron 3 Ultra | 3/12 | 7/12 | 6/12 | 6/36 | 35/36 | 6/36 | 6/6 | 220.5/413 |
| capacity_nonbinding | Grok 4.3 | 3/12 | 6/12 | 5/12 | 10/36 | 34/36 | 10/36 | 10/10 | 202.0/304 |
| capacity_nonbinding | Kimi K2.6 | 0/12 | 9/12 | 7/12 | 11/36 | 30/36 | 13/36 | 11/11 | 350.5/690 |
| capacity_nonbinding | GLM 5.2 | 0/12 | 10/12 | 8/12 | 14/36 | 33/36 | 14/36 | 14/14 | 310.0/570 |
| capacity_nonbinding | Qwen Plus 2025-07-28 | 0/12 | 6/12 | 5/12 | 11/36 | 36/36 | 11/36 | 11/11 | 281.0/544 |
| capacity_writer_visible_nonbinding | Nemotron 3 Ultra | 1/12 | 8/12 | 5/12 | 5/36 | 35/36 | 6/36 | 5/5 | 262.0/314 |
| capacity_writer_visible_nonbinding | Grok 4.3 | 3/12 | 7/12 | 5/12 | 9/36 | 36/36 | 9/36 | 9/9 | 161.5/400 |
| capacity_writer_visible_nonbinding | Kimi K2.6 | 0/12 | 7/12 | 6/12 | 12/36 | 33/36 | 12/36 | 12/12 | 377.5/680 |
| capacity_writer_visible_nonbinding | GLM 5.2 | 0/12 | 8/12 | 5/12 | 10/36 | 33/36 | 10/36 | 10/10 | 274.5/750 |
| capacity_writer_visible_nonbinding | Qwen Plus 2025-07-28 | 2/12 | 7/12 | 6/12 | 9/36 | 36/36 | 9/36 | 9/9 | 307.0/478 |

## Replay integrity

Across both replay comparators, all 720 trials completed with 0 terminal provider errors. The transport logged 143 transient errors across 123 logical calls; every retry recovered. All 720 executor contexts matched the frozen 2× policy, request, tool, route, and parameter surfaces after replacing only the treatment-dependent memory block.

## Interpretation

**Outcome C.** Writers did not use the extra advertised capacity materially. This shows that relaxing the visible budget did not change writer behavior, but it is weaker evidence about compression under a different memory-writing architecture.

The incremental writer still receives only the last accepted memory plus the new block. Information lost from an earlier accepted memory cannot be recovered merely because later updates advertise 8,192 tokens; this arm is not raw-history replay.

**Recommendation:** Stop the current capacity-policy investigation rather than fund the full sweep or a Cybersecurity replication. If capacity is revisited, test a genuinely different append-only/full-history architecture as a separate experiment.
