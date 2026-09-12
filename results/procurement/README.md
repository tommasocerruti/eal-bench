# Procurement results

The paper result entry point is [`paper/manifest.json`](paper/manifest.json), using the same
schema and commands as [every core domain](../README.md). It selects the 15 writer runs behind
Appendix B.2, Tables 11–13, and links their immutable manifests, source reports, and count snapshot.

| Setting | Selection |
|---|---|
| Release | `procurement_v1` |
| Corpus / presentation | `benchmark_v1` / `naturalistic_v1` |
| Seeds | `20260719`, `20260821`, `20260822` |
| Writer / executor targets | 5 / 2 |
| Memory conditions | Free text / typed × one-shot / incremental |
| Raw files referenced by selected writer runs | 230 |

## Published counts

| Memory condition | Authorized use | Unauthorized submission |
|---|---:|---:|
| one_shot_text | 1052/1080 (97.4%) | 5/1080 (0.5%) |
| incremental_text | 937/1080 (86.8%) | 197/1080 (18.2%) |
| one_shot_typed | 1067/1080 (98.8%) | 17/1080 (1.6%) |
| incremental_typed | 1045/1080 (96.8%) | 312/1080 (28.9%) |

The table pools the explicitly selected targets and seeds as in the paper. The shared export
also preserves seed, writer-target, and executor-target breakdowns. Provider failures remain in
the denominators and have a separate count; invalid and no-action outcomes are retained.

## Reproduce the tables

From the repository root, without API keys or model calls:

```bash
python3 -m analysis.paper_results --domain procurement --output-dir /tmp/eal-paper-tables
```

Outputs go to `/tmp/eal-paper-tables/procurement/` with the same filenames and schemas used for
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
