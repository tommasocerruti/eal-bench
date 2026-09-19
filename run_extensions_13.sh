#!/usr/bin/env bash
# Phase 13 (Windows): the memory-type table on cybersecurity and finance for the paper's writers.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
echo "=== $(date +%H:%M) PHASE 13 START" >> "$LOG"
for d in cybersecurity finance; do
  for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten; do
    run experiments.writer_variants_run --domain "$d" --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 \
        --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --batch-size 10 --estimated-cost-usd 30 --tag "memtable-$d-$w"
  done
done
echo "=== $(date +%H:%M) PHASE 13 DONE" >> "$LOG"
