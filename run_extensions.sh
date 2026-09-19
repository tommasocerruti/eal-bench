#!/usr/bin/env bash
# Sequential driver for the extension studies (procurement, Baseten, GPT-OSS executor).
# Runs one process at a time; each piece writes its own run directory under results/.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
WRITERS="glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten"
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

for w in $WRITERS; do
  run experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3,retrieve:6 \
      --writer-targets "$w" --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15 --tag "variants-$w"
done
for w in $WRITERS; do
  run experiments.closed_loop --writer-targets "$w" --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 8 --tag "loop-$w"
done
for w in $WRITERS; do
  run experiments.closed_loop --conditions incremental_typed --writer-targets "$w" --executor-targets gptoss_baseten \
      --loop-writer executor --action-log --batch-size 10 --estimated-cost-usd 5 --tag "loop-executor-$w"
done
run experiments.writer_variants_run --corpus-version generated_v1 --memory-types typed --writing-methods incremental \
    --writer-targets kimi_baseten --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15 --tag generated-kimi
echo "=== $(date +%H:%M) ALL DONE" >> "$LOG"
