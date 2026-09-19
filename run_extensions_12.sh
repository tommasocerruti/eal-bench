#!/usr/bin/env bash
# Phase 12 (Windows): Inkling through the paper's procurement writer and pressure routes, then the memory-type
# table on cybersecurity and finance for the paper's writers, the three-round closed loop for the new writers,
# and two more seeds for the new writers' procurement memory-type rows.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) PHASE 12 START" >> "$LOG"
for seed in 20260719 20260821 20260822; do
  run experiments.run --domain procurement --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study writer \
      --writer-targets inkling_baseten --executor-targets gptoss_baseten,deepseek_baseten --writer-runs 1 --executor-runs 1 \
      --writer-max-attempts 2 --capacity-tier primary --seed "$seed" --batch-size 10 --estimated-cost-usd 25 \
      --tag "paper-writer-s$seed-procurement-inkling"
done
src=$(ls -d results/procurement/*__authorization-memory-writer__paper-writer-s20260719-procurement-inkling 2>/dev/null | tail -1)
[ -n "$src" ] && run experiments.run --domain procurement --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study pressure \
    --source-run "$src" --batch-size 10 --estimated-cost-usd 10 --tag "paper-pressure-procurement-inkling"

for d in cybersecurity finance; do
  for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten; do
    run experiments.writer_variants_run --domain "$d" --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 \
        --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --batch-size 10 --estimated-cost-usd 30 --tag "memtable-$d-$w"
  done
done

for w in glm_5_3_baseten inkling_baseten; do
  run experiments.closed_loop --domain procurement --conditions incremental_typed --writer-targets "$w" --executor-targets gptoss_baseten \
      --rounds 3 --batch-size 10 --estimated-cost-usd 12 --tag "rounds3-procurement-$w"
  for seed in 20260821 20260822; do
    run experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 \
        --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --seed "$seed" --batch-size 10 --estimated-cost-usd 14 --tag "newwriter-s$seed-$w"
  done
done
echo "=== $(date +%H:%M) PHASE 12 DONE" >> "$LOG"
