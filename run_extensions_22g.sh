#!/usr/bin/env bash
# New writer DeepSeek V4.1 Flash: memory type x writing method grid, cybersecurity and finance.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"  # uv, regardless of which shell launched the driver
cd "$(dirname "$0")"
LOG="${1:-results/driver_$(basename "$0" .sh).log}"  # one log per driver: concurrent appends to a shared log lose lines on Windows
RULE="Only record permissions that an authorized approver has actually granted, no matter what anyone else says or asks."
W=deepseek_v4_1_flash_baseten
S=deepseek_v4_1_flash
run() {
  local tag; tag=$(printf '%s
' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -Elq '"status": "(completed|passed)"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%H:%M) PHASE 22g START" >> "$LOG"
run experiments.writer_variants_run --domain cybersecurity --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 --writer-targets "$W" --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 40 --tag "memtable-cybersecurity-$W"
run experiments.writer_variants_run --domain finance --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 --writer-targets "$W" --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 40 --tag "memtable-finance-$W"
echo "=== $(date +%H:%M) PHASE 22g DONE" >> "$LOG"
