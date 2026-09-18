#!/usr/bin/env bash
# Closed loop with the neutral control (Section 3) for Qwen Plus in cybersecurity: same design as the five Baseten writers (three
# rounds, action and neutral arms, incremental typed memory, canonical seed), one run per executor. Split per domain so the
# twelve OpenRouter-writer runs proceed in parallel; the procurement GPT-OSS run of each writer was started by the earlier
# sequential driver and is left out here.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
cd "$(dirname "$0")"
LOG="results/driver_$(basename "$0" .sh).log"
W=qwen_plus_0728_openrouter
run() {
  local tag; tag=$(printf '%s
' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
export EAL_ROUTE_TIMEOUT_SECONDS=14400
run experiments.closed_loop --domain cybersecurity --conditions incremental_typed --writer-targets "$W" --executor-targets gptoss_baseten --rounds 3 --loop-content both --batch-size 12 --writer-batch-size 20 --estimated-cost-usd 40 --tag "rounds3v2-both-cybersecurity-gptoss-$W"
echo "q_loop_cybersecurity_gptoss DONE $(date +%F_%H:%M)" >> results/parity_streams.done
