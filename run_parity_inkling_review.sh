#!/usr/bin/env bash
# Independent DeepSeek V4 Pro review of Inkling's writer-side compute pools (review-only, no Inkling calls).
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
cd "$(dirname "$0")"
LOG=results/driver_parity_inkling_review.log
P="experiments.run --domain procurement --corpus-version benchmark_v1 --presentation-version naturalistic_v1"
W=inkling_baseten; S=inkling
latest() { ls -d results/procurement/*__"$1" 2>/dev/null | grep -v superseded | tail -1; }
run() {
  local tag; tag=$(printf '%s\n' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%F_%H:%M) INKLING REVIEW START" >> "$LOG"
for k in 2 4 8; do
  SRCK=$(latest "authorization-memory-writer_ttc__procurement-v1-$S-ttc-k$k")
  [ -n "$SRCK" ] || { echo "FAILED: no k=$k pool for $S" >> "$LOG"; continue; }
  run $P --study writer_ttc --writer-targets "$W" --reviewer-target deepseek_baseten --executor-targets gptoss_baseten --writer-runs $k --ttc-review-only --source-run "$SRCK" --seed 20260719 --batch-size 10 --estimated-cost-usd 5 --tag "procurement-v1-$S-ttc-k$k-review"
done
echo "=== $(date +%F_%H:%M) INKLING REVIEW DONE" >> "$LOG"
