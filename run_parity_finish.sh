#!/usr/bin/env bash
# After the parity streams: judge the new failures, refresh every analysis over all seven writers, regenerate the
# figures, and update the paper. Each step logs to results/driver_parity_finish.log; a failed step is reported, not hidden.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")"
LOG=results/driver_parity_finish.log
S="C:/Users/mikad/AppData/Local/Temp/claude/C--Users-mikad-Documents-GitHub-llm-compliance/e03609a8-99b6-4cf4-a446-8278e2da42ad/scratchpad"
step() { echo "=== $(date +%F_%H:%M) $1" >> "$LOG"; shift; "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }
PY=.venv/Scripts/python.exe

step "retire stale unfinished run directories" $PY scratch/iclr_seven/supersede_stale.py
step "event-sourcing analysis for Inkling reruns" env PYTHONPATH=. $PY scratch/iclr_seven/event_inkling_analysis.py
step "judge new failures" env PYTHONPATH=. $PY scratch/iclr_seven/judge_incremental.py
step "failures.csv" $PY scratch/build_failures_csv.py
step "pool designs, hybrid cells, review, event, refusal" env PYTHONPATH=. $PY scratch/iclr_seven/parity_pool.py
step "instruction paired (seven writers)" $PY scratch/iclr_seven/section7_seven.py
step "restatements without instruction" bash -c "$PY scratch/section4_v2.py 'generated-v2-glm_5_2_baseten' 'generated-v2-kimi_baseten' 'generated-v2-nemotron_3_ultra_baseten' 'generated-v2-inkling_baseten' 'generated-v2-deepseek_v4_1_flash_baseten' 'generated-v2-grok_4_3_openrouter' 'generated-v2-qwen_plus_0728_openrouter' > results/analysis/section4_seven_without.md"
step "restatements with instruction" bash -c "$PY scratch/section4_v2.py 'mandate-generated-v2-glm_5_2_baseten' 'mandate-generated-v2-kimi_baseten' 'mandate-generated-v2-nemotron_3_ultra_baseten' 'mandate-generated-v2-inkling_baseten' 'mandate-generated-v2-deepseek_v4_1_flash_baseten' 'mandate-generated-v2-grok_4_3_openrouter' 'mandate-generated-v2-qwen_plus_0728_openrouter' > results/analysis/section4_seven_with.md"
step "closed loop paired, all writers" bash -c "PYTHONPATH=. $PY scratch/loop_vs_null.py 'results/*/*rounds3v2-both-*' > results/analysis/loop_vs_null_seven.txt"
for W in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten inkling_baseten deepseek_v4_1_flash_baseten grok_4_3_openrouter qwen_plus_0728_openrouter; do
  step "closed loop paired, $W" bash -c "PYTHONPATH=. $PY scratch/loop_vs_null.py 'results/*/*rounds3v2-both-*-$W' > results/analysis/loop_vs_null_$W.txt"
done
step "closed loop figure" bash -c "PYTHONPATH=. $PY -m analysis.plot_closed_loop_figure 'results/*/*rounds3v2-both-*' --out results/figures/closed_loop_control"
step "cause table" bash -c "$PY scratch/section6_v2.py > results/analysis/section6_seven.md"
step "paper update" bash -c "$PY scratch/iclr_seven/apply_parity.py \"$S\""
step "compile" bash -c "cd ../eal-bench-iclr && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex > /dev/null 2>&1; grep -c -E \"undefined|multiply\" main.log; pdfinfo main.pdf | grep Pages"
echo "=== $(date +%F_%H:%M) PARITY FINISH DONE" >> "$LOG"
