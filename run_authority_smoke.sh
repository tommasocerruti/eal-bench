#!/usr/bin/env bash
# Smoke: the authority rule on two procurement cases, typed incremental, GLM 5.2.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
INSTR=$(tr -d '\n' < "C:/Users/mikad/AppData/Local/Temp/claude/C--Users-mikad-Documents-GitHub-llm-compliance/767ffd3c-178a-438a-a3b3-b208e1bdbaa9/scratchpad/authority_instruction.txt")
echo "=== $(date +%H:%M) [authority-smoke] start" >> "$LOG"
uv run python -m experiments.writer_variants_run --memory-types typed --writing-methods incremental --case-ids procurement_v1_cloud_spend_narrowing,procurement_v1_freight_vendor_change \
    --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --writer-instruction "$INSTR" --instruction-tag authority \
    --batch-size 10 --estimated-cost-usd 3 --tag authority-smoke >> "$LOG" 2>&1 || echo "FAILED: authority smoke" >> "$LOG"
echo "=== $(date +%H:%M) [authority-smoke] done" >> "$LOG"
