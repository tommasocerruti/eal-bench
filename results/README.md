# Paper results

All core domains use the same result layout and offline export command.

| Domain | Published result guide | Selected manifest |
|---|---|---|
| Procurement | [Results](procurement/README.md) | [Manifest](procurement/paper/manifest.json) |
| Cybersecurity | [Results](cybersecurity/README.md) | [Manifest](cybersecurity/paper/manifest.json) |
| Finance | [Results](finance/README.md) | [Manifest](finance/paper/manifest.json) |

## Reproduce published counts

Run from the repository root with Python 3.10 or later. Only the standard library is needed:

```bash
python3 -m analysis.paper_results --domain all --output-dir /tmp/eal-paper-tables
```

Select one domain with `--domain procurement`, `--domain cybersecurity`, or `--domain finance`.
Every selection uses this source layout:

```text
results/<domain>/paper/manifest.json   # release, design, sources, and run hashes
results/<domain>/paper/counts.json     # integer counts per seed and writer
results/<domain>/<run-id>/manifest.json
```

The output directory contains one subdirectory per domain, each with these files:

| File | Contents / paper mapping |
|---|---|
| `seed_conditions.csv` | Seed × condition counts; Appendix B.2, Table 11 |
| `memory_design.csv` | Three-seed condition totals; Table 12 |
| `executor_transfer.csv` | Counts per executor target; Table 13 |
| `executor_agreement.csv` | Fixed-memory requested-action agreement per seed and writer; sum for Table 13 |
| `writer_conditions.csv` | Counts per seed, writer target, and condition |
| `writer_executors.csv` | Counts per seed, writer target, and executor target |
| `artifact_inventory.csv` | Expected paths, hashes, row counts, and current availability |
| `summary.json`, `tables.md` | Counts, treatment identity, availability, and verification limits |

The paper is [arXiv:2609.01836v1](https://arxiv.org/html/2609.01836v1#A2.SS2).
These packages select the 15 ordinary writer routes per domain used in its three-seed analysis.
Supplemental pressure, controls, interventions, and development reports retain their original
locations; they are outside this selected writer-run inventory.

## Counts and source verification

Authorized use counts the exact requested action when the canonical request is authorized.
Unauthorized submission counts that action when the canonical request is unauthorized.
Each has its own authorization denominator. All ordinary `generated_final` trials remain in the
denominators, including invalid, no-action, and provider-error outcomes; provider errors also have
a separate column. Executor agreement compares the requested-action outcome on both replays of
the same memory and request.

Pooling in the displayed condition tables follows the paper's explicitly selected five writers,
two executors, and three seeds. The exports retain target and seed breakdowns. The verifier rejects
a change of presentation hash or memory implementation within a domain. Domains are never pooled.
Condition and executor marginals do not specify their joint distribution; use the original trial
files or a frozen report's full matrix for analyses requiring joint cells.

The common count snapshots were derived from hash-verified original trial files for the initial
Procurement and Cybersecurity seeds, and the frozen replication/evaluation report cells for the
remaining routes. The manifest records each route's precise source and report row where needed.
`analysis.paper_results.from_trials` uses the shared hash-aware loader in `analysis/common.py`;
`from_report` adapts historical report formats to the same count schema. Every invocation checks
the saved snapshot against available source report cells and recounts any available raw trials.
The saved snapshot remains usable when original trials are absent.

## Raw artifacts

Raw `results/**/*.jsonl` files are excluded from Git for all domains. A clone includes count
snapshots, reports, and manifests, but does not include raw trials, memories, or provider contexts.
Historical completion audits describe files at execution time. The generated inventory reports
availability now; a successful table export does not imply that the raw archive is complete.

To check an archive with the original repository-relative paths:

```bash
python3 -m analysis.paper_results --domain all \
  --raw-root /path/to/archive --require-raw --output-dir /tmp/eal-paper-audit
```

The archive must contain `results/<domain>/<run-id>/manifest.json` alongside the original files.
Available files must match their declared hashes and JSONL row counts. Available trial files are
recounted against the saved counts; this does not independently rerun the oracle. `--require-raw`
exits with status 2 if any inventoried raw file is missing, after exporting the inventory.
Missing raw files prevent independent scoring and reconstruction of bootstrap inputs. New model
runs are stochastic replications and cannot replace original records.

## Run a new experiment

All domains use the same runner. Replace the domain, seed, and tag as appropriate:

```bash
uv run python -m experiments.run \
  --domain procurement --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 --study writer \
  --writer-targets nemotron_3_ultra_baseten,kimi_baseten,glm_5_2_baseten,grok_4_3_openrouter,qwen_plus_0728_openrouter \
  --executor-targets gptoss_baseten,deepseek_baseten \
  --writer-architecture all --writer-strategy all \
  --seed 20260719 --validate-only
```

The selected seeds are in each domain's paper manifest. Validation makes no provider calls.
Removing `--validate-only` starts paid model calls and writes a new run; it does not regenerate the
original published sample. Preserve historical artifacts and direct derived exports outside
`domains/` and `results/`.
