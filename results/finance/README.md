# Finance results

The paper result entry point is [`paper/manifest.json`](paper/manifest.json), using the same
schema and commands as [every core domain](../README.md). It selects the 15 writer runs behind
Appendix B.2, Tables 11–13, and links their immutable manifests, source reports, and count snapshot.

| Setting | Selection |
|---|---|
| Release | `finance_redesign_v1` |
| Corpus / presentation | `benchmark_v1` / `naturalistic_v1` |
| Seeds | `20260816`, `20260821`, `20260822` |
| Writer / executor targets | 5 / 2 |
| Memory conditions | Free text / typed × one-shot / incremental |
| Raw files referenced by selected writer runs | 255 |

## Published counts

| Memory condition | Authorized use | Unauthorized submission |
|---|---:|---:|
| one_shot_text | 954/960 (99.4%) | 26/960 (2.7%) |
| incremental_text | 908/960 (94.6%) | 296/960 (30.8%) |
| one_shot_typed | 880/960 (91.7%) | 4/960 (0.4%) |
| incremental_typed | 944/960 (98.3%) | 490/960 (51.0%) |

The table pools the explicitly selected targets and seeds as in the paper. The shared export
also preserves seed, writer-target, and executor-target breakdowns. Provider failures remain in
the denominators and have a separate count; invalid and no-action outcomes are retained.

## Reproduce the tables

From the repository root, without API keys or model calls:

```bash
python3 -m analysis.paper_results --domain finance --output-dir /tmp/eal-paper-tables
```

Outputs go to `/tmp/eal-paper-tables/finance/` with the same filenames and schemas used for
all domains. See the [shared result guide](../README.md) for column definitions, table mappings,
raw-file verification, and the limits of aggregate reproduction.

## Provenance and availability

[`paper/counts.json`](paper/counts.json) stores integer counts per seed and writer, with separate
condition and executor marginals. [`paper/manifest.json`](paper/manifest.json) pins its hash,
the exact source inputs, dataset files, and selected run manifests. No trial rows were reconstructed
from aggregates. Historical filenames and scientific release IDs are retained unchanged.

Raw `results/**/*.jsonl` files are excluded from Git for all domains. The shared command reports
which originals are present in the current checkout or a supplied `--raw-root` archive and checks
their hashes and row counts. It also recounts ordinary trial outcomes when `trials.jsonl` is present.
A saved completion audit describes availability at execution time, not what a clone contains.

Earlier qualification runs and supplemental studies remain in their original directories.
Use the selected manifests above when matching the paper's three-seed results.

The [frozen scientific report](../finance_redesign/final_held_out_evaluation.md) also records
controls, pressure, interventions, and development. Its [archive guide](../finance_redesign/README.md)
maps those additional analyses and the older release history.
