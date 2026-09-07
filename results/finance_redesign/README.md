# Finance scientific report archive

This directory preserves the frozen source reports for **`finance_redesign_v1`**. The older
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

## Standard result package

The public entry point is the same as every domain: [`results/finance/`](../finance/README.md).
Use the [shared command and artifact policy](../README.md):

```bash
python3 -m analysis.paper_results --domain finance --output-dir /tmp/eal-paper-tables
```

This historical directory retains the original report filenames and hashes. The shared paper
package selects its 15 writer routes for Tables 11–13. The full release also contains controls
and pressure: all 33 final manifests survive, while their 378 raw JSONL files were unavailable
in the inspected local archives on 7 September 2026. The historical completion audit records
130,381 rows and 1,766,734,205 bytes verified at execution time. It remains unchanged.

A backup would contain the original `results/finance/20260822-*__finance-redesign-final-*/`
run directories from `/private/tmp/eal-bench-finance-redesign`. The selected writer inventory and
all other final manifests specify the exact original paths and hashes. Restore originals only;
aggregate counts cannot recover individual trials, memories, or provider-visible contexts.

## Development record

The [design report](design_report.md), [iteration index](development_iteration_index.json),
iteration-specific reports, and [Procurement forensic comparison](procurement_reference_forensics.md)
document the 14 development iterations and the change from a GLM one-shot development gate to
an incremental gate. Iteration 14 was the first passing candidate; development stopped before
evaluation on held-out families and seeds. Development outcomes are not pooled into paper counts.
