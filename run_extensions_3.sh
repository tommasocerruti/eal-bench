#!/usr/bin/env bash
# Phase 3: rerun the free-text closed loop with one-condition-per-call writer updates.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
until grep -q "PHASE 2 DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
echo "=== $(date +%H:%M) PHASE 3 START" >> "$LOG"
for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten; do
  run experiments.closed_loop --conditions incremental_text --writer-targets "$w" --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 5 --tag "loop-text-$w"
done
echo "=== $(date +%H:%M) PHASE 3 DONE" >> "$LOG"
