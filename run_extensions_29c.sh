#!/usr/bin/env bash
# Cybersecurity with the oversize write failure removed, baseline arm (Section 7 mechanism test). In the judged
# cybersecurity failures most rejected updates at the change-set block are either a profile over the memory's size limit
# (55 of 98 at that block) or a malformed patch. --capacity-scale 2 doubles the calibrated primary capacity (2646 -> 5292
# tokens; the largest rejected candidate was 4231) so an oversize profile now fits. Typed incremental, canonical seed,
# five writers, both executors; compare with run_extensions_29d.sh (same, with the one-line mandate).
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
cd "$(dirname "$0")"
LOG="${1:-results/driver_$(basename "$0" .sh).log}"
run() {
  local tag; tag=$(printf '%s\n' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP (completed run exists) $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%H:%M) PHASE 29c START" >> "$LOG"
for w in glm_5_2_baseten kimi_baseten nemotron_3_ultra_baseten inkling_baseten deepseek_v4_1_flash_baseten; do
  run experiments.writer_variants_run --domain cybersecurity --memory-types typed --writing-methods incremental --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --writer-batch-size 8 --estimated-cost-usd 15 --writer-targets "$w" --seed 20260812 --capacity-scale 2 --tag "cap2-cybersecurity-${w}"
done
echo "=== $(date +%H:%M) PHASE 29c DONE" >> "$LOG"
