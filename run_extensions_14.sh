#!/usr/bin/env bash
# Phase 14 (Windows): the two reasoning writers, redone with the 16k output budget, on procurement:
# the paper's writer and pressure routes at the paper's seeds, the memory-type table at three seeds, the three-round loop.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
echo "=== $(date +%H:%M) PHASE 14 START" >> "$LOG"
for w in glm_5_3_baseten inkling_baseten; do
  short=${w%_baseten}
  for seed in 20260719 20260821 20260822; do
    run experiments.run --domain procurement --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study writer \
        --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --writer-runs 1 --executor-runs 1 \
        --writer-max-attempts 2 --capacity-tier primary --seed "$seed" --batch-size 10 --estimated-cost-usd 30 \
        --tag "paper-writer-s$seed-procurement-$short"
  done
  src=$(ls -d results/procurement/*__authorization-memory-writer__paper-writer-s20260719-procurement-$short 2>/dev/null | tail -1)
  [ -n "$src" ] && run experiments.run --domain procurement --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study pressure \
      --source-run "$src" --batch-size 10 --estimated-cost-usd 12 --tag "paper-pressure-procurement-$short"
  for seed in 20260719 20260821 20260822; do
    run experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 \
        --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --seed "$seed" --batch-size 10 --estimated-cost-usd 20 --tag "newwriter-s$seed-$w"
  done
  run experiments.closed_loop --domain procurement --conditions incremental_typed --writer-targets "$w" --executor-targets gptoss_baseten \
      --rounds 3 --batch-size 10 --estimated-cost-usd 15 --tag "rounds3-procurement-$w"
done
echo "=== $(date +%H:%M) PHASE 14 DONE" >> "$LOG"
