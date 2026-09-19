#!/usr/bin/env bash
# Phase 9: redo GLM 5.3 on the memory-type table at batch 10 (the batch-20 run hit executor rate limits).
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
until grep -q "PHASE 7 DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) PHASE 9 START" >> "$LOG"
run experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 \
    --writer-targets glm_5_3_baseten --executor-targets gptoss_baseten,deepseek_baseten --batch-size 10 --estimated-cost-usd 14 --tag "newwriter2-glm_5_3_baseten"
echo "=== $(date +%H:%M) PHASE 9 DONE" >> "$LOG"
