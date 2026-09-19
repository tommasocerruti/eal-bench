#!/usr/bin/env bash
# Phase 5: redo the GLM and Kimi rebuild-k sweeps with the strictly periodic schedule.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
until grep -q "PHASE 4 DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
for w in glm_5_2_baseten kimi_baseten; do
  run experiments.writer_variants_run --memory-types typed --writing-methods rebuild:2,rebuild:4,rebuild:6 \
      --writer-targets "$w" --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 8 --tag "periodic-$w"
done
echo "=== $(date +%H:%M) PHASE 5 DONE" >> "$LOG"
