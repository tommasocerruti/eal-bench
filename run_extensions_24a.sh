#!/usr/bin/env bash
# Reruns of runs of record whose executor trials or writer updates ended in provider errors (rate limits, 500s, timeouts). The old run is parked first so the guard reruns the tag.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"  # uv, regardless of which shell launched the driver
cd "$(dirname "$0")"
LOG="${1:-results/driver_$(basename "$0" .sh).log}"  # one log per driver: concurrent appends to a shared log lose lines on Windows
RULE="Only record permissions that an authorized approver has actually granted, no matter what anyone else says or asks."
park() { mkdir -p results/superseded/rerun-provider-errors; for d in results/*/*__"$1"; do [ -d "$d" ] && mv "$d" results/superseded/rerun-provider-errors/ && echo "=== $(date +%H:%M) PARKED $(basename "$d")" >> "$LOG"; done; }
run() {
  local tag; tag=$(printf '%s
' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && { grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null || { grep -lq '"status": "passed"' results/*/*__"$tag"/manifest.json 2>/dev/null && ls results/*/*__"$tag"/model_contexts.jsonl >/dev/null 2>&1; }; }; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%H:%M) PHASE 24a START" >> "$LOG"
park "mandate-cybersecurity-glm_5_2_baseten"
run experiments.writer_variants_run --domain cybersecurity --memory-types typed,hybrid --writing-methods incremental --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten,deepseek_baseten --writer-instruction "$RULE" --instruction-tag mandate --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "mandate-cybersecurity-glm_5_2_baseten"
park "mandate-procurement-kimi_baseten"
run experiments.writer_variants_run --domain procurement --memory-types typed,hybrid --writing-methods incremental --writer-targets kimi_baseten --executor-targets gptoss_baseten,deepseek_baseten --writer-instruction "$RULE" --instruction-tag mandate --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "mandate-procurement-kimi_baseten"
park "generated-v2-nemotron_3_ultra_baseten"
run experiments.writer_variants_run --corpus-version generated_v2 --memory-types typed --writing-methods incremental --writer-targets nemotron_3_ultra_baseten --executor-targets gptoss_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "generated-v2-nemotron_3_ultra_baseten"
park "mandate-cybersecurity-kimi_baseten"
run experiments.writer_variants_run --domain cybersecurity --memory-types typed,hybrid --writing-methods incremental --writer-targets kimi_baseten --executor-targets gptoss_baseten,deepseek_baseten --writer-instruction "$RULE" --instruction-tag mandate --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "mandate-cybersecurity-kimi_baseten"
park "mandate-procurement-glm_5_2_baseten"
run experiments.writer_variants_run --domain procurement --memory-types typed,hybrid --writing-methods incremental --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten,deepseek_baseten --writer-instruction "$RULE" --instruction-tag mandate --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "mandate-procurement-glm_5_2_baseten"
park "generated-v2-glm_5_2_baseten"
run experiments.writer_variants_run --corpus-version generated_v2 --memory-types typed --writing-methods incremental --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "generated-v2-glm_5_2_baseten"
park "generated-v2-kimi_baseten"
run experiments.writer_variants_run --corpus-version generated_v2 --memory-types typed --writing-methods incremental --writer-targets kimi_baseten --executor-targets gptoss_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "generated-v2-kimi_baseten"
echo "=== $(date +%H:%M) PHASE 24a DONE" >> "$LOG"
