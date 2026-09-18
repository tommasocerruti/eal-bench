#!/usr/bin/env bash
# Phase 11: the paper's own writer route (four memory conditions, both executors) for the new writers at the
# paper's seeds, then the pressure route on each fixed-seed writer run.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
until grep -q "PHASE 10 DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) PHASE 11 START" >> "$LOG"
for w in glm_5_3_baseten inkling_baseten; do
  short=${w%_baseten}
  for spec in "procurement 20260719 20260821 20260822" "cybersecurity 20260812 20260821 20260822"; do
    set -- $spec; d=$1; shift
    for seed in "$@"; do
      run experiments.run --domain "$d" --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study writer \
          --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --writer-runs 1 --executor-runs 1 \
          --writer-max-attempts 2 --capacity-tier primary --seed "$seed" --batch-size 10 --estimated-cost-usd 25 \
          --tag "paper-writer-s$seed-$d-$short"
    done
    fixed=$1
    src=$(ls -d results/$d/*__authorization-memory-writer__paper-writer-s$fixed-$d-$short 2>/dev/null | tail -1)
    if [ -n "$src" ]; then
      run experiments.run --domain "$d" --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study pressure \
          --source-run "$src" --batch-size 10 --estimated-cost-usd 10 --tag "paper-pressure-$d-$short"
    else
      echo "FAILED: no writer run found for pressure on $d $short" >> "$LOG"
    fi
  done
done
echo "=== $(date +%H:%M) PHASE 11 DONE" >> "$LOG"
