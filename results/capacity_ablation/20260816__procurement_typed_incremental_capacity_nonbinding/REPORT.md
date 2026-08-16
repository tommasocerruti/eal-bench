# Procurement typed-incremental capacity ablation

All intervals are 10,000-replicate writer–case trajectory cluster-bootstrap percentile intervals. Request and transition rows are not treated as independent memory samples.

| Metric | 2× capacity | Nonbinding | Difference (pp, 95% CI) |
|---|---:|---:|---:|
| exact_final_memory_rate | 3/60 (5.0%; 95% CI 0.0% to 11.7%) | 6/60 (10.0%; 95% CI 3.3% to 18.3%) | +5.0 [-1.7, +11.7] |
| final_semantic_error_rate | 38/60 (63.3%; 95% CI 51.7% to 75.0%) | 38/60 (63.3%; 95% CI 51.7% to 75.0%) | +0.0 [-13.3, +13.3] |
| final_authority_gaining_error_rate | 31/60 (51.7%; 95% CI 38.3% to 65.0%) | 31/60 (51.7%; 95% CI 40.0% to 65.0%) | +0.0 [-10.0, +10.0] |
| final_memory_apparent_authority_rate | 28/60 (46.7%; 95% CI 35.0% to 58.4%) | 27/60 (45.0%; 95% CI 33.3% to 58.3%) | -1.7 [-11.7, +8.3] |
| request_level_apparent_authority_formation_p_f | 55/180 (30.6%; 95% CI 21.7% to 39.4%) | 52/180 (28.9%; 95% CI 20.6% to 37.2%) | -1.7 [-10.0, +6.1] |
| transition_error_introduction_rate | 37/243 (15.2%; 95% CI 12.0% to 18.6%) | 36/241 (14.9%; 95% CI 11.7% to 18.2%) | -0.3 [-3.8, +3.0] |
| transition_error_persistence_rate | 27/27 (100.0%; 95% CI 100.0% to 100.0%) | 29/29 (100.0%; 95% CI 100.0% to 100.0%) | +0.0 [+0.0, +0.0] |
| introduced_episode_self_repair_rate | 0/37 (0.0%; 95% CI 0.0% to 0.0%) | 0/36 (0.0%; 95% CI 0.0% to 0.0%) | +0.0 [+0.0, +0.0] |

## Capacity and size audit

| Condition | Capacity failures | Final tokens, median [p25, p75] | Final maximum | Per-update tokens, median [p25, p75] |
|---|---:|---:|---:|---:|
| capacity_2x | 3 | 272.0 [171.2, 343.2] | 515 | 135.0 [125.0, 246.0] |
| capacity_nonbinding | 0 | 277.5 [197.5, 361.8] | 690 | 136.0 [125.0, 244.0] |

## Final-memory error taxonomy

| Category | 2× capacity | Nonbinding |
|---|---:|---:|
| scope_broadening | 26/60 (43.3%) | 27/60 (45.0%) |
| revoked_record_retention | 0/60 (0.0%) | 0/60 (0.0%) |
| boundary_loss | 25/60 (41.7%) | 24/60 (40.0%) |
| hallucinated_authority | 3/60 (5.0%) | 2/60 (3.3%) |
| scope_substitution | 5/60 (8.3%) | 3/60 (5.0%) |
| cross_record_stitching | 0/60 (0.0%) | 0/60 (0.0%) |
| stale_state_retention | 1/60 (1.7%) | 2/60 (3.3%) |
| inactive_record_retention | 0/60 (0.0%) | 1/60 (1.7%) |

## Primary-executor behavior

| Metric | 2× capacity | Nonbinding | Difference (pp, 95% CI) |
|---|---:|---:|---:|
| authorized_use_rate | 176/180 (97.8%; 95% CI 93.9% to 100.0%) | 168/180 (93.3%; 95% CI 87.2% to 98.3%) | -4.4 [-10.0, +0.0] |
| targeted_unauthorized_submission_rate | 56/180 (31.1%; 95% CI 22.2% to 40.6%) | 54/180 (30.0%; 95% CI 21.7% to 38.9%) | -1.1 [-9.4, +6.7] |
| propagation_given_apparent_authority_rate | 55/55 (100.0%; 95% CI 100.0% to 100.0%) | 52/52 (100.0%; 95% CI 100.0% to 100.0%) | +0.0 [+0.0, +0.0] |

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

## Replay integrity

All 360 trials completed with 0 terminal provider errors. The transport logged 85 transient errors across 74 logical calls; every retry recovered. All 360 executor contexts matched the frozen 2× policy, request, tool, route, and parameter surfaces after replacing only the treatment-dependent memory block.

## Interpretation

The result supports outcome A: capacity enforcement is not the primary cause of the observed authorization-state failures. Removing the validator changed neither the final semantic-error count nor the authority-gaining-error count, and the small P(F) and downstream differences have paired intervals spanning zero. The ablation isolates enforcement, not the model-visible 572-token instruction, which intentionally remained fixed.

A full Procurement capacity sweep is therefore a secondary mechanism study rather than a prerequisite for the present result. The higher-value next experiment is the same 2× versus nonbinding enforcement replication in Cybersecurity; a 1×/2×/4×/nonbinding sweep becomes more compelling if that replication shows a capacity effect.
