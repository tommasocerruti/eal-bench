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
echo "=== $(date +%H:%M) PHASE 24b START" >> "$LOG"
park "memtable-cybersecurity-kimi_baseten"
run experiments.writer_variants_run --domain cybersecurity --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 --writer-targets kimi_baseten --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 40 --tag "memtable-cybersecurity-kimi_baseten"
park "memtable-finance-kimi_baseten"
run experiments.writer_variants_run --domain finance --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 --writer-targets kimi_baseten --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 40 --tag "memtable-finance-kimi_baseten"
park "memtable-cybersecurity-glm_5_2_baseten"
run experiments.writer_variants_run --domain cybersecurity --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3 --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 40 --tag "memtable-cybersecurity-glm_5_2_baseten"
park "paper-writer-s20260821-procurement-inkling"
run experiments.run --domain procurement --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study writer --writer-targets inkling_baseten --executor-targets gptoss_baseten,deepseek_baseten --writer-runs 1 --executor-runs 1 --writer-max-attempts 2 --capacity-tier primary --seed 20260821 --batch-size 10 --estimated-cost-usd 40 --tag "paper-writer-s20260821-procurement-inkling"
park "mandate-cybersecurity-inkling_baseten"
run experiments.writer_variants_run --domain cybersecurity --memory-types typed,hybrid --writing-methods incremental --writer-targets inkling_baseten --executor-targets gptoss_baseten,deepseek_baseten --writer-instruction "$RULE" --instruction-tag mandate --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 30 --tag "mandate-cybersecurity-inkling_baseten"
echo "=== $(date +%H:%M) PHASE 24b DONE" >> "$LOG"
