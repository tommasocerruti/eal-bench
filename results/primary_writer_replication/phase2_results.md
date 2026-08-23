# Phase 2 seeded replication and Finance replacement

All 42 precommitted routes completed without outcome-based reruns. Finance values use exact-request unauthorized submission throughout.

## Three-seed ordinary writer robustness

| Domain | Seed | Source | Authorized use | Unauthorized submission |
|---|---:|---|---:|---:|
| procurement | 20260821 | new_seed | 1361/1440 (94.5%) | 167/1440 (11.6%) |
| procurement | 20260822 | new_seed | 1373/1440 (95.3%) | 175/1440 (12.2%) |
| procurement | 20260719 | published aggregate; original raw route files are not re-audited here | 1367/1440 (94.9%) | 189/1440 (13.1%) |
| cybersecurity | 20260821 | new_seed | 2424/2560 (94.7%) | 101/2560 (3.9%) |
| cybersecurity | 20260822 | new_seed | 2333/2560 (91.1%) | 151/2560 (5.9%) |
| cybersecurity | 20260812 | published request-scoped aggregate | 2423/2560 (94.6%) | 98/2560 (3.8%) |
| finance | 20260816 | fresh_original_seed_replacement | 1193/1280 (93.2%) | 19/1280 (1.5%) |
| finance | 20260821 | new_seed | 1151/1280 (89.9%) | 28/1280 (2.2%) |
| finance | 20260822 | new_seed | 1128/1280 (88.1%) | 36/1280 (2.8%) |

The seed ranges are descriptive. No seed is pooled into or substituted for the primary result.

## Fresh original-seed Finance replacement

| Result | Historical current-paper value | Fresh replacement |
|---|---:|---:|
| Pooled pressure unauthorized submission | 127/1280 (9.9%) | 72/1280 (5.6%) |
| DeepSeek baseline unauthorized submission | 39/640 (6.1%) | 10/640 (1.6%) |
| DeepSeek pressure unauthorized submission | 91/640 (14.2%) | 65/640 (10.2%) |
| Natural-error → exact-repair intervention | 24/24 → 0/24 | 0/0 → 0/0 (not estimable) |

Fresh controls: **failed** overall. GPT-OSS passed; DeepSeek failed because terminal provider errors prevented perfect faithful-use and controlled-broadening gates. No successful outcomes were rerun.

## Cost and execution

| Provider | Calls | Network attempts | Provider-reported | Rate-derived | Total |
|---|---:|---:|---:|---:|---:|
| baseten | 34042 | 41887 | $0.00 | $169.84 | $169.84 |
| openrouter | 3221 | 3221 | $24.08 | $0.00 | $24.08 |

Total: **$193.92 / $292.00**; 37263 final call records and 45108 recorded network attempts.
The global total uses the frozen Phase 1 cache-aware rates. The standalone Finance finalizer conservatively prices writer cache reads at ordinary input rates, so its cost subtotal is higher; behavioral results are unaffected.
Sequential execution span: **14.59 hours**, from 2026-08-21T03:12:19.599196+02:00 to 2026-08-21T17:47:44.727010+02:00.

## Artifact completeness

**Passed:** 42/42 selected routes, 642 authoritative JSONL artifacts, 216045 rows, and 490 checkpoint files all match their manifest hashes and row counts. Raw model contexts are present for every route.

The zero-cost GLM pressure attempt blocked by local sandbox DNS is preserved and excluded; it made zero provider calls and cost $0.

## Paper limitation

The missing-Finance-artifacts limitation can be removed after the paper replaces every historical Finance value with these fresh artifact-backed outcomes. That edit must replace 24/24 → 0/24 with a not-estimable witness result and transparently report the failed fresh DeepSeek control gate.

No paper files were edited.
