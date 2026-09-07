# Finance results accompanying arXiv:2609.01836v1

Use this directory for the paper's **`finance_redesign_v1`** results. The older
`results/finance/finance_v1__*` and `phase2_finance_replacement*` summaries describe earlier
datasets, even though those releases also used the corpus name `benchmark_v1`.

The final release was completed at commit `010932e`; the scientific corpus revision is `7e9cd2d`.
The release's corpus provenance hash is
`e16f7342262b32188cff39e315c6041505195aceffea500d56a6a3e99a551966`.
The frozen [release declaration](../../domains/finance/release.json) links each final report and
all 33 run manifests by SHA-256.

## Where to find each result

| Paper result | Frozen JSON field | Scope |
|---|---|---|
| Appendix B.2, Table 11 | `ordinary_matrix`, grouped by seed and condition | All three seeds |
| Appendix B.2, Table 12 | `memory_design[*].behavior` | All three seeds |
| Appendix B.2, Table 13 | `ordinary_matrix` by executor; `executor_transfer` for agreement | All three seeds |
| Appendix B.3, Finance writer matrix | `ordinary_matrix`, seed `20260816` | One displayed seed |
| Appendix B.5, Finance pressure comparison | `pressure_matrix`, seed `20260816` | One displayed seed |
| Typed false-authority formation | `memory_design[*].formation` | Final typed memories, not free text |
| Natural-memory versus exact-repair intervention | `causal_analysis` | Outcome-blind selected witnesses |

The [JSON report](final_held_out_evaluation.json) and [scientific report](final_held_out_evaluation.md)
are immutable outputs. The pressure report also contains other seeds; use the seed selection
above when matching the published fixed-seed table. Do not substitute the three-seed pressure
aggregate for that table.

## Rebuild the aggregate tables

From the repository root, with Python 3.10 or later:

```bash
python3 -m analysis.finance_paper_results --output-dir /tmp/finance-paper-tables
```

No API keys, model calls, tokenizer download, or optional analysis packages are needed. Outputs:

- `ordinary_matrix.csv`: all 120 ordinary result cells with seeds and provider-specific targets.
- `seed_conditions.csv`: the 12 seed-by-condition cells behind Table 11.
- `memory_design.csv`: the four three-seed aggregate cells behind Table 12.
- `executor_transfer.csv` and `executor_agreement.csv`: counts behind Table 13.
- `tables.md` and `summary.json`: readable results, source hashes, and audit limits.
- `artifact_inventory.csv`: relative paths, expected hashes and row counts, and current status
  for every raw artifact referenced by the final manifests.

The script rejects altered frozen inputs, duplicate/missing matrix cells, and inconsistent
aggregates. A successful aggregate check means the saved result cells reproduce the tables;
it does not establish independent correctness of the original trial scoring.

## Raw artifact availability and recovery

As checked on 7 September 2026, the 33 final run manifests and the aggregate reports survive,
but all **378 referenced JSONL files** are absent from the available run directories. The
[historical artifact audit](final_artifact_audit.json) records the successful completion-time
verification of 130,381 rows and 1,766,734,205 bytes. That historical audit is retained unchanged.

The original execution root was `/private/tmp/eal-bench-finance-redesign`. A backup should contain
`results/finance/20260822-*__finance-redesign-final-*/` and its manifest-owned `trials.jsonl`,
`memories.jsonl`, `memory_states.jsonl`, `calls.jsonl`, `model_contexts.jsonl`, and other files.
The inventory generated above gives the exact expected paths and hashes. Restore recovered
files at those relative paths without overwriting a different file, then run:

```bash
python3 -m analysis.finance_paper_results --require-raw
```

This command exits with status 2 while raw files are missing and rejects any recovered file
whose hash or row count differs. It must pass before claiming full raw-artifact availability.
After restoration, the original domain finalizer can recompute trial-level analyses; direct its
outputs to a separate directory and preserve the frozen reports. Its legacy execution paths may
need an explicit local mapping.

Raw `results/**/*.jsonl` files are excluded from Git. A code push alone will not distribute
recovered originals; they require a separately approved archive with a complete checksum list.
Do not invent trial rows from aggregate counts or substitute newly sampled runs for lost outputs.

## Development record

The [design report](design_report.md), [iteration index](development_iteration_index.json),
iteration-specific reports, and [Procurement forensic comparison](procurement_reference_forensics.md)
document the 14 development iterations and the change from a GLM one-shot development gate to
an incremental gate. Iteration 14 was the first passing candidate; development stopped before
evaluation on held-out families and seeds. Development outcomes are not pooled into paper counts.
