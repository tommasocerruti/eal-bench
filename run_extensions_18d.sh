#!/usr/bin/env bash
# Closed loop rerun with DeepSeek V4 Pro as the executor: action and neutral arms forked from the same base memories (one
# run each), all domains; procurement at two seeds like the GPT-OSS driver. The DeepSeek endpoint has its own rate
# limit, so this runs alongside the GPT-OSS drivers.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"  # uv, regardless of which shell launched the driver
# Writer order differs between drivers so the three writer endpoints are loaded at the same time.
cd "$(dirname "$0")"
LOG="${1:-results/driver_$(basename "$0" .sh).log}"  # one log per driver: concurrent appends to a shared log lose lines on Windows
run() {
  local tag; tag=$(printf '%s
' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%H:%M) PHASE 18d START" >> "$LOG"
for w in kimi_baseten nemotron_3_ultra_baseten glm_5_2_baseten; do
  run experiments.closed_loop --domain procurement --conditions incremental_typed --writer-targets "$w" --executor-targets deepseek_baseten --rounds 3 --loop-content both --batch-size 8 --writer-batch-size 8 --estimated-cost-usd 15 --tag "rounds3v2-both-procurement-deepseek-$w"
done
echo "=== $(date +%H:%M) PHASE 18d DONE" >> "$LOG"
