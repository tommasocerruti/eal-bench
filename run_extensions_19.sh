#!/usr/bin/env bash
# Generated_v2 baseline (stale restatements isolated) and the finance memory-type grid, then the judges on every new run once phases 18a-d and 20a-b are done.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"  # uv, regardless of which shell launched the driver
# Writer order differs between drivers so the three writer endpoints are loaded at the same time; completed runs are skipped by tag.
cd "$(dirname "$0")"
LOG="${1:-results/driver_$(basename "$0" .sh).log}"  # one log per driver: concurrent appends to a shared log lose lines on Windows
RULE="Only record permissions that an authorized approver has actually granted, no matter what anyone else says or asks."
run() {
  local tag; tag=$(printf '%s
' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%H:%M) PHASE 19 START" >> "$LOG"
for w in nemotron_3_ultra_baseten glm_5_2_baseten kimi_baseten; do
  run experiments.writer_variants_run --corpus-version generated_v2 --memory-types typed --writing-methods incremental --writer-targets "$w" --executor-targets gptoss_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 15 --tag "generated-v2-$w"
done
for w in nemotron_3_ultra_baseten glm_5_2_baseten kimi_baseten; do
  run experiments.writer_variants_run --domain finance --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "memtable-finance-$w"
done
echo "=== $(date +%H:%M) PHASE 19 RUNS DONE" >> "$LOG"
for p in 18a 18b 18c 18d 18e 20a 20b 20c; do until grep -q "PHASE $p DONE" "results/driver_run_extensions_$p.log" 2>/dev/null; do sleep 60; done; done
# Judge with the simplified label set (4 causes + other) under results/diagnosis/v2: every new run, and the earlier
# open-loop groups again so Section 6 uses one label set throughout.
J=results/diagnosis/v2
bash run_diagnosis.sh $J/judge_loop-both.log $J/loop-both "results/*/*closed_loop__rounds3v2-both-*"
bash run_diagnosis.sh $J/judge_loop-mandate.log $J/loop-mandate "results/*/*closed_loop__rounds3v2-mandate-*"
bash run_diagnosis.sh $J/judge_onepass.log $J/onepass "results/procurement/*closed_loop__onepassv2-*"
bash run_diagnosis.sh $J/judge_open-generated-v2.log $J/open-generated-v2 "results/procurement/*writer_variants__generated-v2-*"
bash run_diagnosis.sh $J/judge_memtable-finance.log $J/memtable-finance "results/finance/*writer_variants__memtable-finance-*"
bash run_diagnosis.sh $J/judge_mandate-open.log $J/mandate-open "results/*/*writer_variants__mandate-*"
bash run_diagnosis.sh $J/judge_open-seeds.log $J/open-seeds "results/procurement/*writer_variants__seeds-2026*"
bash run_diagnosis.sh $J/judge_open-variants.log $J/open-variants "results/procurement/*writer_variants__variants-*"
bash run_diagnosis.sh $J/judge_memtable-cyber.log $J/memtable-cyber "results/cybersecurity/*writer_variants__memtable-cybersecurity-*"
echo "=== $(date +%H:%M) PHASE 19 DONE (all judged)" >> "$LOG"
