#!/usr/bin/env bash
# Phase 2: rebuild-k sweep and the three-seed, two-executor set for the key conditions.
# Waits for run_extensions.sh to finish (its ALL DONE line), then runs one process at a time.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
WRITERS="glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten"
until grep -q "ALL DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) PHASE 2 START" >> "$LOG"
for w in $WRITERS; do
  run experiments.writer_variants_run --memory-types typed --writing-methods rebuild:2,rebuild:4,rebuild:6 \
      --writer-targets "$w" --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 8 --tag "rebuildk-$w"
done
for seed in 20260719 20260821 20260822; do
  for w in $WRITERS; do
    run experiments.writer_variants_run --memory-types typed,hybrid --writing-methods incremental,rebuild:3 \
        --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --seed "$seed" --batch-size 10 \
        --estimated-cost-usd 10 --tag "seeds-$seed-$w"
  done
done
echo "=== $(date +%H:%M) PHASE 2 DONE" >> "$LOG"
