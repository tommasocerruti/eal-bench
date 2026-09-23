"""Three follow-ups from the co-author's 2026-09-22 notes.
1. The 'update rejected' label now comes from the harness write-validation log, not the judge panel (Table 26, Table 27,
   Figure 6, the B.8 sentence, the C.3 counts). Source: deterministic_cause.py.
2. Error introduction, persistence and self-repair recomputed over all seven writers (transitions_added.py).
3. Every table and figure caption that lacked one now states how many seeds it rests on."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92); PC = B + "%"; NL = chr(10)


def sub(name, old, new, count=1):
    p = ICLR / name; t = p.read_text(encoding="utf-8")
    assert t.count(old) == count, (name, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n"); print("ok", name, "|", " ".join(old.split())[:58])


# ---------------------------------------------------------------- 1. deterministic rejected-update label
sub("extension_results_appendix.tex",
    "    Open loop, cybersecurity & 139 & 529 & 0 & 0 & 51 & 478 & 0 " + B + B,
    "    Open loop, cybersecurity & 139 & 529 & 0 & 0 & 26 & 503 & 0 " + B + B)
sub("extension_results_appendix.tex",
    "    Closed loop, shared history blocks & 156 & 444 & 367 & 0 & 16 & 61 & 0 " + B + B,
    "    Closed loop, shared history blocks & 156 & 444 & 367 & 0 & 8 & 69 & 0 " + B + B)
sub("extension_results_appendix.tex",
    "    Closed loop, the agent's own lines & 234 & 280 & 3 & 271 & 2 & 0 & 4 " + B + B,
    "    Closed loop, the agent's own lines & 234 & 280 & 2 & 271 & 2 & 0 & 5 " + B + B)
sub("extension_results_appendix.tex",
    "    With the instruction, cybersecurity & 176 & 637 & 0 & 6 & 60 & 571 & 0 " + B + B,
    "    With the instruction, cybersecurity & 176 & 637 & 0 & 6 & 48 & 581 & 2 " + B + B)
sub("extension_results_appendix.tex",
    "    All & 1360 & 3{,}569 & 1{,}999 & 285 & 164 & 1{,}114 & 7 " + B + B,
    "    All & 1360 & 3{,}569 & 1{,}998 & 285 & 119 & 1{,}157 & 10 " + B + B)
sub("extension_results_appendix.tex",
    "An update whose failures fall in more than one row is counted in each row, so the rows sum to 1,400 updates against 1,360 distinct.}",
    "A rejected update is read from the harness write-validation log rather than from the judges, who decide among the remaining labels. "
    "An update whose failures fall in more than one row is counted in each row, so the rows sum to 1,400 updates against 1,360 distinct.}")
sub("extension_results_appendix.tex",
    "Labels given by each judge over all 3{,}569 rows.}",
    "Labels given by each judge over all 3{,}569 rows; the write-validation log settles which of the two a row is.}")
sub("extension_results_appendix.tex",
    "The judges agree unanimously on 82" + PC + " of rows, and on a blind sample of fifty failures a fourth model given the judges' inputs agreed with the majority label on 46 (Cohen's $" + B + "kappa=0.88$).",
    "A rejected update is decided by the harness write-validation log, which agrees with the judges' majority on 3,506 of the 3,569 rows (Cohen's $" + B + "kappa=0.96$); "
    "on the 2,412 rows the judges still decide, all three agree on 95" + PC + ", and on a blind sample of fifty failures a fourth model given the judges' inputs agreed with the majority label on 46 (Cohen's $" + B + "kappa=0.88$).")
sub("extension_mitigations_appendix.tex",
    "of 574 failures in the instruction runs, 520 are a rejected update, against 313 of 348 in the same seeds' runs without it.",
    "of 574 failures in the instruction runs, 528 are a rejected update, against 335 of 348 in the same seeds' runs without it.")

# ---------------------------------------------------------------- 2. seven-writer transition rates
sub("main.tex",
    "errors are introduced at 587/5,550 (10.6" + PC + ") positions, persist at 2,869/5,550 (51.7" + PC + "), and self-repair at 207/5,550 (3.7" + PC + ").",
    "errors are introduced at 776/7,770 (10.0" + PC + ") positions, persist at 3,617/7,770 (46.6" + PC + "), and self-repair at 306/7,770 (3.9" + PC + ").")

# ---------------------------------------------------------------- 3. seed statements
sub("main.tex", "Per-executor values appear" + NL + "  in Appendix Table~" + B + "ref{tab:writer-executor-transfer-full}.}",
    "Both columns use the one seed per domain on which the pressure study was run, so they differ slightly from the three-seed baseline of Table~" + B + "ref{tab:memory-design-across-domains}. Per-executor values appear" + NL + "  in Appendix Table~" + B + "ref{tab:writer-executor-transfer-full}.}")
sub("main.tex", "Each domain cell pools all seeds, writers, and executors.", "Each domain cell pools three seeds, seven writers, and both executors.")
sub("main.tex", "hollow markers: a control with the same updates and neutral content. Pooled across writer and executor models.}",
    "hollow markers: a control with the same updates and neutral content. Pooled across writer and executor models at the canonical seed of each domain.}")
sub("main.tex", "Error bars show pointwise 95" + PC + " paired writer-cluster bootstrap intervals.}",
    "Error bars show pointwise 95" + PC + " paired writer-cluster bootstrap intervals. One seed, procurement only.}")
sub("extension_results_appendix.tex", "GPT-OSS-120B as executor; 756 unauthorized requests and 252 memories per point.}",
    "GPT-OSS-120B as executor, one seed; 756 unauthorized requests and 252 memories per point.}")
sub("extension_results_appendix.tex", "intervals are Wilson 95" + PC + ". 252 memories and 756 unauthorized requests per row.}",
    "intervals are Wilson 95" + PC + ". One seed; 252 memories and 756 unauthorized requests per row.}")
sub("extension_results_appendix.tex", "an action-log entry in the own-log arm or a content-free workspace notice in the control arm.}",
    "an action-log entry in the own-log arm or a content-free workspace notice in the control arm. Canonical seed of each domain.}")
sub("event_sourcing_appendix.tex", "Appendix~" + B + "ref{app:writer-ttc-details} excludes the citation field, so its final-state error is lower.}",
    "Appendix~" + B + "ref{app:writer-ttc-details} excludes the citation field, so its final-state error is lower. Three seeds, all writers.}")
sub("capacity_ablation_appendix.tex", "The final column counts" + NL + "  validation failures caused by the capacity bound over all writer updates.}",
    "The final column counts" + NL + "  validation failures caused by the capacity bound over all writer updates. One seed.}")
sub("capacity_ablation_appendix.tex", "requests derived from one" + NL + "  memory remain in the same resampled cluster.}",
    "requests derived from one" + NL + "  memory remain in the same resampled cluster. One seed.}")
sub("main.tex", "summarizing heterogeneity rather than population-level uncertainty.}",
    "summarizing heterogeneity across targets rather than sampling uncertainty. Writer cues use three seeds and executor cues one.}")
sub("main.tex", "values indicate fewer authorization errors or more exact memories.}",
    "values indicate fewer authorization errors or more exact memories. Three seeds.}")
sub("main.tex", "rate, fewer unauthorized actions, or higher paired" + NL + "  discrimination.}",
    "rate, fewer unauthorized actions, or higher paired" + NL + "  discrimination. Three seeds.}")
sub("main.tex", "95" + PC + " paired case-cluster bootstrap intervals, with positive values indicating improvement.}",
    "95" + PC + " paired case-cluster bootstrap intervals, with positive values indicating improvement. One seed.}")
print("done")
