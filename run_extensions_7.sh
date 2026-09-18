#!/usr/bin/env bash
# Phase 7: two additional Baseten writers on the memory-type table (procurement, canonical seed).
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) PHASE 7 START" >> "$LOG"
for w in glm_5_3_baseten inkling_baseten; do
  run experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 \
      --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --batch-size 20 --estimated-cost-usd 14 --tag "newwriter-$w"
done
echo "=== $(date +%H:%M) PHASE 7 DONE" >> "$LOG"
