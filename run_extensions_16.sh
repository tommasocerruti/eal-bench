#!/usr/bin/env bash
# Phase 16: diagnose whatever false permissions remain under the authority rule (open loop and closed loop).
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"
until grep -q "PHASE 15 DONE" "$LOG"; do sleep 60; done
echo "=== $(date +%H:%M) PHASE 16 START (diagnose authority-rule runs)" >> "$LOG"
bash run_diagnosis.sh results/diagnosis/judge_authority-open.log results/diagnosis/authority-open "results/procurement/*writer_variants__authority-*"
bash run_diagnosis.sh results/diagnosis/judge_authority-loop.log results/diagnosis/authority-loop "results/procurement/*closed_loop__rounds3-authority-*"
echo "=== $(date +%H:%M) PHASE 16 DONE" >> "$LOG"
