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
run experiments.writer_variants_run --domain cybersecurity --source-run "results/cybersecurity/20260917-235546-479159__authorization-memory-writer_variants__memtable-cybersecurity-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-cybersecurity-grok_4_3_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-010900-932770__authorization-memory-writer_variants__memtable-s20260821-finance-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-s20260821-finance-grok_4_3_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-024422-919717__authorization-memory-writer_variants__mandate-s20260822-procurement-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-s20260822-procurement-grok_4_3_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-004744-619994__authorization-memory-writer_variants__mandate-finance-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-finance-grok_4_3_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-035938-199914__authorization-memory-writer_variants__mandate-generated-v2-grok_4_3_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-generated-v2-grok_4_3_openrouter"
run experiments.writer_variants_run --domain cybersecurity --source-run "results/cybersecurity/20260918-001628-918204__authorization-memory-writer_variants__memtable-cybersecurity-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-cybersecurity-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-001636-911245__authorization-memory-writer_variants__memtable-s20260821-finance-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-memtable-s20260821-finance-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-013303-449042__authorization-memory-writer_variants__mandate-s20260822-procurement-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-s20260822-procurement-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain finance --source-run "results/finance/20260918-022357-231768__authorization-memory-writer_variants__mandate-finance-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-finance-qwen_plus_0728_openrouter"
run experiments.writer_variants_run --domain procurement --source-run "results/procurement/20260918-051041-911704__authorization-memory-writer_variants__mandate-generated-v2-qwen_plus_0728_openrouter" --executor-targets glm_5_3_baseten --batch-size 8 --estimated-cost-usd 10 --tag "glm53-mandate-generated-v2-qwen_plus_0728_openrouter"
echo "glm53_parity_3 DONE $(date +%F_%H:%M)" >> results/parity_streams.done
