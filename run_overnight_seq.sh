#!/usr/bin/env bash
# One sequential process for the rest of the night (low footprint): wait for the reruns and the running judge job,
# judge the remaining groups one at a time, then run GLM 5.3 as a third executor on the same memories as GPT-OSS and
# DeepSeek (writer_variants_run with three executor targets; Baseten writers only), one run at a time.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
cd "$(dirname "$0")"
LOG="results/driver_run_overnight_seq.log"
J=results/diagnosis/v2
echo "=== $(date +%H:%M) OVERNIGHT START" >> "$LOG"

# wait for the rerun drivers and the closed-loop judge job
for p in 24a 24b; do until grep -q "PHASE $p DONE" "results/driver_run_extensions_$p.log" 2>/dev/null; do sleep 120; done; done
until grep -q "diagnosis done" "$J/judge_loop-both.log" 2>/dev/null; do sleep 120; done
echo "=== $(date +%H:%M) reruns and closed-loop judging finished" >> "$LOG"

# integrity check of every run of record, for the morning report
uv run python scratch/verify_runs.py >> "$LOG" 2>&1

# remaining judge groups, one process at a time (domain directories only; results/*/ would include superseded/)
bash run_diagnosis.sh $J/judge_loop-both.log $J/loop-both "results/procurement/*closed_loop__rounds3v2-both-*" "results/cybersecurity/*closed_loop__rounds3v2-both-*" "results/finance/*closed_loop__rounds3v2-both-*"
bash run_diagnosis.sh $J/judge_loop-mandate.log $J/loop-mandate "results/procurement/*closed_loop__rounds3v2-mandate-*" "results/cybersecurity/*closed_loop__rounds3v2-mandate-*" "results/finance/*closed_loop__rounds3v2-mandate-*"
bash run_diagnosis.sh $J/judge_open-generated-v2.log $J/open-generated-v2 "results/procurement/*writer_variants__generated-v2-*" "results/procurement/*writer_variants__mandate-generated-v2-*"
bash run_diagnosis.sh $J/judge_memtable-finance.log $J/memtable-finance "results/finance/*writer_variants__memtable-finance-*"
bash run_diagnosis.sh $J/judge_memtable-cyber.log $J/memtable-cyber "results/cybersecurity/*writer_variants__memtable-cybersecurity-*"
bash run_diagnosis.sh $J/judge_mandate-open.log $J/mandate-open "results/procurement/*writer_variants__mandate-procurement-*" "results/cybersecurity/*writer_variants__mandate-cybersecurity-*" "results/finance/*writer_variants__mandate-finance-*"
bash run_diagnosis.sh $J/judge_open-seeds.log $J/open-seeds "results/procurement/*writer_variants__seeds-2026*" "results/procurement/*writer_variants__newwriter-s*"
bash run_diagnosis.sh $J/judge_paper-route-new-writers.log $J/paper-route-new-writers "results/procurement/*authorization-memory-writer__paper-writer-s*-procurement-inkling" "results/procurement/*authorization-memory-writer__paper-writer-s*-procurement-deepseek_v4_1_flash" "results/cybersecurity/*authorization-memory-writer__paper-writer-s*-cybersecurity-inkling" "results/cybersecurity/*authorization-memory-writer__paper-writer-s*-cybersecurity-deepseek_v4_1_flash" "results/finance/*authorization-memory-writer__paper-writer-s*-finance-inkling" "results/finance/*authorization-memory-writer__paper-writer-s*-finance-deepseek_v4_1_flash"
echo "=== $(date +%H:%M) ALL JUDGED" >> "$LOG"

# GLM 5.3 as a third executor: the same frozen memories answered by GPT-OSS, DeepSeek V4 Pro, and GLM 5.3 in one run
# (paired across executors), typed incremental, canonical seed, the paper's three Baseten writers; one run at a time.
run() {
  local tag; tag=$(printf '%s\n' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
for d in procurement cybersecurity finance; do for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten; do
  run experiments.writer_variants_run --domain "$d" --memory-types typed,hybrid --writing-methods incremental --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten,glm_5_3_baseten --batch-size 8 --writer-batch-size 8 --estimated-cost-usd 30 --tag "exec3-$d-$w"
done; done
echo "=== $(date +%H:%M) OVERNIGHT DONE" >> "$LOG"
