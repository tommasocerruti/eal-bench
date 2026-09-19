#!/usr/bin/env bash
# Phase 8: the paper's own writer route on finance (GLM, Kimi) at the paper's seed, to compare with our finance results.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
until grep -q "PHASE 6 DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) PHASE 8 START" >> "$LOG"
for w in glm_5_2_baseten kimi_baseten; do
  run experiments.run --domain finance --study writer --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten \
      --seed 20260816 --batch-size 10 --estimated-cost-usd 8 --tag "finance-official-check-$w"
done
echo "=== $(date +%H:%M) PHASE 8 DONE" >> "$LOG"
