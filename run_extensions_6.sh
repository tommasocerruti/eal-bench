#!/usr/bin/env bash
# Phase 6: closed loop with three rounds on every domain, then Nemotron on the generated corpus.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
WRITERS="glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten"
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) PHASE 6 START" >> "$LOG"
for d in procurement cybersecurity finance; do
  for w in $WRITERS; do
    run experiments.closed_loop --domain "$d" --conditions incremental_typed --writer-targets "$w" --executor-targets gptoss_baseten \
        --rounds 3 --batch-size 10 --estimated-cost-usd 12 --tag "rounds3-$d-$w"
  done
done
run experiments.writer_variants_run --corpus-version generated_v1 --memory-types typed --writing-methods incremental \
    --writer-targets nemotron_3_ultra_baseten --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15 --tag generated-nemotron
echo "=== $(date +%H:%M) PHASE 6 DONE" >> "$LOG"
