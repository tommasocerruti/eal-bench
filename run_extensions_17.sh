#!/usr/bin/env bash
# Phase 17: the authority rule on held-out settings. Cybersecurity three-round closed loop and the generated procurement
# corpus (typed incremental), three writers, same rule text as phase 15, compared with rounds3-cybersecurity-* and generated-*.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
INSTR=$(tr -d '\n' < "C:/Users/mikad/AppData/Local/Temp/claude/C--Users-mikad-Documents-GitHub-llm-compliance/767ffd3c-178a-438a-a3b3-b208e1bdbaa9/scratchpad/authority_instruction.txt")
run() { echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
echo "=== $(date +%H:%M) PHASE 17 START (authority rule, held-out: cyber rounds3 + generated corpus)" >> "$LOG"
for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten; do
  run experiments.closed_loop --domain cybersecurity --conditions incremental_typed --writer-targets "$w" --executor-targets gptoss_baseten --rounds 3       --writer-instruction "$INSTR" --batch-size 10 --estimated-cost-usd 20 --tag "rounds3-authority-cybersecurity-$w"
done
for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten; do
  run experiments.writer_variants_run --corpus-version generated_v1 --memory-types typed --writing-methods incremental --writer-targets "$w" --executor-targets gptoss_baseten       --writer-instruction "$INSTR" --instruction-tag authority --batch-size 10 --estimated-cost-usd 15 --tag "generated-authority-$w"
done
echo "=== $(date +%H:%M) PHASE 17 DONE" >> "$LOG"
bash run_diagnosis.sh results/diagnosis/judge_authority-cyber-loop.log results/diagnosis/authority-cyber-loop "results/cybersecurity/*closed_loop__rounds3-authority-cybersecurity-*"
bash run_diagnosis.sh results/diagnosis/judge_authority-generated.log results/diagnosis/authority-generated "results/procurement/*writer_variants__generated-authority-*"
echo "=== $(date +%H:%M) PHASE 17 JUDGED" >> "$LOG"
