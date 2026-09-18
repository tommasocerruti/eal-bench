#!/usr/bin/env bash
# Judge the failures of the Grok 4.3 and Qwen-Plus parity runs into the existing diagnosis groups (same judges, same labels).
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
cd "$(dirname "$0")"
LOG=results/driver_parity_judge.log
judge() {  # judge GROUP GLOB...
  local group="$1"; shift
  echo "=== $(date +%F_%H:%M) diagnosis start -> results/diagnosis/v2/$group : $*" >> "$LOG"
  uv run python -m experiments.diagnose_formation "$@" --out "results/diagnosis/v2/$group" >> "$LOG" 2>&1 || echo "FAILED: diagnosis $group $*" >> "$LOG"
}
for W in grok_4_3_openrouter qwen_plus_0728_openrouter; do
  judge open-seeds "results/procurement/*__newwriter-s*-$W"
  judge memtable-cyber "results/cybersecurity/*__memtable-cybersecurity-$W"
  judge memtable-finance "results/finance/*__memtable-finance-$W"
  judge memtable-seeds "results/cybersecurity/*__memtable-s*-cybersecurity-$W" "results/finance/*__memtable-s*-finance-$W"
  judge mandate-open "results/*/*__mandate-*$W"
  judge open-generated-v2 "results/procurement/*__generated-v2-$W" "results/procurement/*__mandate-generated-v2-$W"
  judge loop-both "results/*/*__rounds3v2-both-*-$W"
done
echo "=== $(date +%F_%H:%M) PARITY JUDGE DONE" >> "$LOG"
