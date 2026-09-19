#!/usr/bin/env bash
# Closed loop with the neutral control (Section 3) for Grok 4.3, the paper's OpenRouter writer, to the same design as the five
# Baseten writers: three rounds, action and neutral arms, incremental typed memory, canonical seed, one run per domain and
# executor (GPT-OSS-120B, DeepSeek V4 Pro on Baseten). Writer calls go to OpenRouter; executor calls to Baseten.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
cd "$(dirname "$0")"
LOG="${1:-results/driver_$(basename "$0" .sh).log}"
W=grok_4_3_openrouter
run() {
  local tag; tag=$(printf '%s
' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%H:%M) PHASE 29j START" >> "$LOG"
for d in procurement cybersecurity finance; do
  run experiments.closed_loop --domain "$d" --conditions incremental_typed --writer-targets "$W" --executor-targets gptoss_baseten --rounds 3 --loop-content both --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 40 --tag "rounds3v2-both-$d-gptoss-$W"
  run experiments.closed_loop --domain "$d" --conditions incremental_typed --writer-targets "$W" --executor-targets deepseek_baseten --rounds 3 --loop-content both --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 40 --tag "rounds3v2-both-$d-deepseek-$W"
done
echo "=== $(date +%H:%M) PHASE 29j DONE" >> "$LOG"
