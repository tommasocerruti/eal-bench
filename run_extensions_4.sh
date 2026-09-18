#!/usr/bin/env bash
# Phase 4: rerun the Kimi executor-writer closed loop after the loop-evidence fix.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
until grep -q "PHASE 3 DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
run experiments.closed_loop --conditions incremental_typed --writer-targets kimi_baseten --executor-targets gptoss_baseten \
    --loop-writer executor --action-log --batch-size 10 --estimated-cost-usd 5 --tag loop-executor-kimi_baseten
echo "=== $(date +%H:%M) PHASE 4 DONE" >> "$LOG"
