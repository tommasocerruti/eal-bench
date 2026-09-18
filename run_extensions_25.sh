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
echo "=== $(date +%H:%M) PHASE 25 START" >> "$LOG"

# --- evaluation cue, writer stage: three seeds x three levels per writer (the paper's e1-writer runs)
for spec in "inkling_baseten inkling" "deepseek_v4_1_flash_baseten deepseek_v4_1_flash"; do set -- $spec; W=$1; S=$2
  for seed in 20260816 20260817 20260818; do for lvl in l0 l1 l2; do
    run $P --study evaluation_cue --intervention-stage writer --cue-level $lvl --writer-targets "$W" --executor-targets gptoss_baseten --writer-runs 1 --writer-max-attempts 2 --capacity-tier primary --seed $seed --batch-size 10 --estimated-cost-usd 6 --tag "e1-writer-s$seed-$lvl-$S"
  done; done
done

# --- evaluation cue, executor stage: frozen canonical-seed memories of both added writers, both executors
SRC_I=$(latest "authorization-memory-writer__paper-writer-s20260719-procurement-inkling")
SRC_F=$(latest "authorization-memory-writer__paper-writer-s20260719-procurement-deepseek_v4_1_flash")
for lvl in l0 l1 l2; do
  run $P --study evaluation_cue --intervention-stage executor --cue-level $lvl --executor-targets gptoss_baseten,deepseek_baseten --source-run "$SRC_I" --source-run "$SRC_F" --batch-size 10 --estimated-cost-usd 6 --tag "e1-executor-$lvl-inkling-flash"
done

# --- writer-side inference scaling: nested pools k=2 (from the canonical writer run), k=4 (from k=2), k=8 (from k=4);
#     for each k the DeepSeek independent review and the typed-oracle selection replay, GPT-OSS fixed as executor
for spec in "inkling_baseten inkling" "deepseek_v4_1_flash_baseten deepseek_v4_1_flash"; do set -- $spec; W=$1; S=$2
  SRC=$(latest "authorization-memory-writer__paper-writer-s20260719-procurement-$S")
  run $P --study writer_ttc --writer-targets "$W" --executor-targets gptoss_baseten --writer-runs 2 --source-run "$SRC" --seed 20260719 --batch-size 10 --estimated-cost-usd 40 --tag "procurement-v1-$S-ttc-k2"
  K2=$(latest "authorization-memory-writer_ttc__procurement-v1-$S-ttc-k2")
  run $P --study writer_ttc --writer-targets "$W" --executor-targets gptoss_baseten --writer-runs 4 --source-run "$K2" --seed 20260719 --batch-size 10 --estimated-cost-usd 40 --tag "procurement-v1-$S-ttc-k4"
  K4=$(latest "authorization-memory-writer_ttc__procurement-v1-$S-ttc-k4")
  run $P --study writer_ttc --writer-targets "$W" --executor-targets gptoss_baseten --writer-runs 8 --source-run "$K4" --seed 20260719 --batch-size 10 --estimated-cost-usd 60 --tag "procurement-v1-$S-ttc-k8"
  K8=$(latest "authorization-memory-writer_ttc__procurement-v1-$S-ttc-k8")
  for pair in "2 $K2" "4 $K4" "8 $K8"; do set -- $pair; k=$1; SRCK=$2
    [ -n "$SRCK" ] || { echo "FAILED: no k=$k pool for $S" >> "$LOG"; continue; }
    run $P --study writer_ttc --writer-targets "$W" --reviewer-target deepseek_baseten --executor-targets gptoss_baseten --writer-runs $k --ttc-review-only --source-run "$SRCK" --seed 20260719 --batch-size 10 --estimated-cost-usd 5 --tag "procurement-v1-$S-ttc-k$k-review"
    run $P --study writer_ttc --writer-targets "$W" --executor-targets gptoss_baseten --writer-runs $k --ttc-oracle-only --source-run "$SRCK" --seed 20260719 --batch-size 10 --estimated-cost-usd 2 --tag "procurement-v1-$S-ttc-k$k-typed-oracle-replay"
  done
done
echo "=== $(date +%H:%M) PHASE 25 DONE" >> "$LOG"
