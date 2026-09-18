#!/usr/bin/env bash
# Added writers (Inkling, DeepSeek V4.1 Flash) through the paper's procurement-only secondary studies, with the paper's
# exact commands: evaluation-cue (writer stage, seeds 20260816/17/18, levels l0/l1/l2; executor stage on the frozen
# canonical-seed memories, both executors) and writer-side inference scaling (nested k=2,4,8 pools from the canonical
# writer run, then the DeepSeek independent-review and typed-oracle selection replays). One process, sequential.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
cd "$(dirname "$0")"
LOG="${1:-results/driver_$(basename "$0" .sh).log}"
run() {
  local tag; tag=$(printf '%s\n' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && { grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null || { grep -lq '"status": "passed"' results/*/*__"$tag"/manifest.json 2>/dev/null && ls results/*/*__"$tag"/model_contexts.jsonl >/dev/null 2>&1; }; }; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
latest() { ls -d results/procurement/*__"$1" 2>/dev/null | grep -v superseded | tail -1; }
P="experiments.run --domain procurement --corpus-version benchmark_v1 --presentation-version naturalistic_v1"
echo "=== $(date +%H:%M) PHASE 25b3 START" >> "$LOG"
# --- evaluation cue, writer stage: three seeds x three levels per writer (the paper's e1-writer runs)
for spec in "deepseek_v4_1_flash_baseten deepseek_v4_1_flash"; do set -- $spec; W=$1; S=$2
  for seed in 20260818; do for lvl in l0 l1 l2; do
    run $P --study evaluation_cue --intervention-stage writer --cue-level $lvl --writer-targets "$W" --executor-targets gptoss_baseten --writer-runs 1 --writer-max-attempts 2 --capacity-tier primary --seed $seed --batch-size 10 --estimated-cost-usd 6 --tag "e1-writer-s$seed-$lvl-$S"
  done; done
done

echo "=== $(date +%H:%M) PHASE 25b3 DONE" >> "$LOG"
