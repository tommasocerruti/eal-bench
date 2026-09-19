#!/usr/bin/env bash
# Rebuild-from-history every three blocks at the paper's other two seeds in finance (Section 1 / the mitigation
# frontier): the canonical seed exists in the memtable-finance-<writer> runs; these add 20260821 and 20260822 so every
# frontier point is at three seeds. Typed memory, rebuild:3, both executors, five writers.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
cd "$(dirname "$0")"
LOG="${1:-results/driver_$(basename "$0" .sh).log}"
run() {
  local tag; tag=$(printf '%s\n' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%H:%M) PHASE 29b START" >> "$LOG"
for seed in 20260821 20260822; do
  for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten inkling_baseten deepseek_v4_1_flash_baseten; do
    run experiments.writer_variants_run --domain finance --memory-types typed --writing-methods rebuild:3 --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 15 --writer-targets "$w" --seed "$seed" --tag "rebuild3-s${seed}-finance-${w}"
  done
done
echo "=== $(date +%H:%M) PHASE 29b DONE" >> "$LOG"
