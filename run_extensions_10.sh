#!/usr/bin/env bash
# Phase 10: rerun Inkling on the memory-type table at batch 10 (the first attempt died without a traceback).
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
until grep -q "PHASE 9 DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) PHASE 10 START" >> "$LOG"
run experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 \
    --writer-targets inkling_baseten --executor-targets gptoss_baseten,deepseek_baseten --batch-size 10 --estimated-cost-usd 14 --tag "newwriter2-inkling_baseten"
echo "=== $(date +%H:%M) PHASE 10 DONE" >> "$LOG"
