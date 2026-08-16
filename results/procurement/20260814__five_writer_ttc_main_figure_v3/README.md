# Procurement writer-TTC figure notes

## Authoritative sources

- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/REPORT.md`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/summary.json`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/procurement_v1__five_writer_ttc_k8_final_audit_20260815.json`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/pooled_behavior_by_condition.csv`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/pooled_selection_scaling.csv`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/pooled_incremental_mechanisms.csv`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/pooled_typed_fidelity_by_condition.csv`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/behavior_by_writer_condition.csv`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/selection_by_writer.csv`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__five_writer_ttc_k8_analysis_v1/incremental_mechanisms_by_writer.csv`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__deepseek_independent_ttc_k8_analysis_v2/REPORT.md`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__deepseek_independent_ttc_k8_analysis_v2/summary.json`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__deepseek_independent_ttc_k8_analysis_v2/selection_pooled.csv`
- `/Users/tommasocerruti/Workspace/eal-bench/results/procurement/20260815__deepseek_independent_ttc_k8_analysis_v2/selection_by_writer_condition.csv`

The final audit pins the five-writer analysis manifest at `2f1c8f10e48d165c38e14c525d00b2c97da19eae43455e5528af2ba2f83dbbf1` and the independent-review manifest at `7bea4cf2c25cab633cc6d9b8e3e56bf09e315d5c53ab335aad844e4439e1108c`. Every file hash in both manifests was rechecked before plotting. `verification.json` confirms that all requested k=8 values match the authoritative files after the stated rounding; no discrepancies were found.

## Pooling and denominators

Panel A uses the already-pooled analysis rows, not a new recomputation: 1,440 executor trials per k, including 720 authorized and 720 unauthorized requests. Authorized use is conditioned on authorized requests; targeted unauthorized submission is conditioned on unauthorized requests.

Panel B uses 120 typed candidate pools per k for full-fidelity exact-memory availability and selected exactness. DeepSeek's k=1 point is the same single available candidate by identity; k=2,4,8 use the independent-review analysis. Failed reviews retain the preregistered prior selection and remain in selected-outcome denominators.

Panel C pools 60 selected incremental typed trajectories per k. Error introduction uses correct-origin transitions as its denominator; final-state error uses selected trajectories. Persistence and self-repair use incorrect-origin transitions.

## Uncertainty and design choices

Pointwise 95% percentile intervals use a paired writer-cluster bootstrap with 10,000 resamples and seed 20260814. Each resample draws five writers with replacement, uses the same resampled writers at every k, and recomputes each pooled rate as the ratio of resampled numerator and denominator sums. This preserves pairing across the nested k pools. With only five writer clusters and 12 fixed histories per condition, the intervals are best read as a descriptive across-writer robustness check, not population-level inference.

Panel A uses vertically stacked mini-axes because authorized use is near 95% while targeted unauthorized submission is below 14%; a single 0–100% scale would suppress the safety change, while a dual axis would make slopes hard to compare. Distinct markers and line styles preserve interpretation in grayscale. Panel B leaves the three selection curves unshaded so neither practical selector is visually privileged. Panel C plots only introduction and final-state error; persistence and self-repair are reported in the caption and machine-readable data. Every x-axis is base-2 logarithmic with labeled ticks only at k=1,2,4,8.
