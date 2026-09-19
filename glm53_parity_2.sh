#!/usr/bin/env bash
# GLM 5.3 executor-only replays of the frozen Grok 4.3 / Qwen-Plus memories (Baseten only).
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
export PYTHONIOENCODING=utf-8
cd "$(dirname "$0")"
LOG="results/driver_$(basename "$0" .sh).log"
run() {
  local tag; tag=$(printf '%s
' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; .venv/Scripts/python.exe -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-015634-712865__authorization-memory-writer_variants__newwriter-s20260822-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-newwriter-s20260822-grok_4_3_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260917-235549-586743__authorization-memory-writer_variants__memtable-finance-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-finance-grok_4_3_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-013610-570366__authorization-memory-writer_variants__mandate-s20260821-procurement-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-s20260821-procurement-grok_4_3_openrouter"
run experiments.writer_variants_run --domain cybersecurity --source-run "results/cybersecurity/20260918-031817-664364__authorization-memory-writer_variants__mandate-s20260822-cybersecurity-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-s20260822-cybersecurity-grok_4_3_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-030536-157629__authorization-memory-writer_variants__generated-v2-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-generated-v2-grok_4_3_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-001644-086609__authorization-memory-writer_variants__newwriter-s20260822-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-newwriter-s20260822-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-001634-887416__authorization-memory-writer_variants__memtable-finance-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-finance-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-032101-683378__authorization-memory-writer_variants__mandate-s20260821-procurement-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-s20260821-procurement-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain cybersecurity --source-run "results/cybersecurity/20260918-030224-901696__authorization-memory-writer_variants__mandate-s20260822-cybersecurity-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-s20260822-cybersecurity-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-031035-073970__authorization-memory-writer_variants__generated-v2-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-generated-v2-qwen_plus_0728_openrouter"
echo "glm53_parity_2 DONE $(date +%F_%H:%M)" >> results/parity_streams.done
