#!/usr/bin/env bash
# One-off: my writer_variants pipeline on finance typed incremental at the paper's phase-2 seed, GLM, both executors.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
run experiments.writer_variants_run --domain finance --memory-types typed --writing-methods incremental --writer-targets glm_5_2_baseten \
    --executor-targets gptoss_baseten,deepseek_baseten --seed 20260821 --batch-size 10 --estimated-cost-usd 4 --tag finance-check-s20260821-glm
echo "=== $(date +%H:%M) FINANCE CHECK DONE" >> "$LOG"
