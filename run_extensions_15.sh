#!/usr/bin/env bash
# Phase 15: the authority-rule writer instruction as a mitigation. Open loop (typed and hybrid, incremental) and the
# three-round closed loop, procurement, the paper's three writers, compared against the same conditions without it.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
INSTR=$(tr -d '\n' < "C:/Users/mikad/AppData/Local/Temp/claude/C--Users-mikad-Documents-GitHub-llm-compliance/767ffd3c-178a-438a-a3b3-b208e1bdbaa9/scratchpad/authority_instruction.txt")
until grep -q "PHASE 13 DONE" "$LOG"; do sleep 60; done
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
echo "=== $(date +%H:%M) PHASE 15 START (authority rule)" >> "$LOG"
for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten; do
  run experiments.writer_variants_run --memory-types typed,hybrid --writing-methods incremental --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten \
      --writer-instruction "$INSTR" --instruction-tag authority --batch-size 10 --estimated-cost-usd 12 --tag "authority-$w"
done
for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten; do
  run experiments.closed_loop --conditions incremental_typed --writer-targets "$w" --executor-targets gptoss_baseten --rounds 3 \
      --writer-instruction "$INSTR" --batch-size 10 --estimated-cost-usd 12 --tag "rounds3-authority-procurement-$w"
done
echo "=== $(date +%H:%M) PHASE 15 DONE" >> "$LOG"
