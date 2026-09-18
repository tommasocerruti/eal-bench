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
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260917-234318-745451__authorization-memory-writer_variants__newwriter-s20260719-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-newwriter-s20260719-grok_4_3_openrouter"
run experiments.writer_variants_run --domain cybersecurity --source-run "results/cybersecurity/20260918-021452-792456__authorization-memory-writer_variants__memtable-s20260821-cybersecurity-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-s20260821-cybersecurity-grok_4_3_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-014149-803433__authorization-memory-writer_variants__memtable-s20260822-finance-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-s20260822-finance-grok_4_3_openrouter"
run experiments.writer_variants_run --domain cybersecurity --source-run "results/cybersecurity/20260918-012854-113100__authorization-memory-writer_variants__mandate-cybersecurity-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-cybersecurity-grok_4_3_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-015953-204678__authorization-memory-writer_variants__mandate-s20260821-finance-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-s20260821-finance-grok_4_3_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-001641-993162__authorization-memory-writer_variants__newwriter-s20260719-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-newwriter-s20260719-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain cybersecurity --source-run "results/cybersecurity/20260918-001630-925257__authorization-memory-writer_variants__memtable-s20260821-cybersecurity-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-s20260821-cybersecurity-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-001639-327898__authorization-memory-writer_variants__memtable-s20260822-finance-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-s20260822-finance-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain cybersecurity --source-run "results/cybersecurity/20260918-030333-309437__authorization-memory-writer_variants__mandate-cybersecurity-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-cybersecurity-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-022417-672429__authorization-memory-writer_variants__mandate-s20260821-finance-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-s20260821-finance-qwen_plus_0728_openrouter"
echo "glm53_parity_0 DONE $(date +%F_%H:%M)" >> results/parity_streams.done
