#!/usr/bin/env bash
# One-off: the same two-case cyber writer job (GLM 5.3, typed, full rebuild at the last block) on this platform.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"; TAG="$2"; PY="${3:-uv run python}"
echo "=== $(date +%H:%M) [$TAG] platform check start" >> "$LOG"
$PY -m experiments.writer_variants_run --domain cybersecurity --memory-types typed --writing-methods rebuild:10,incremental \
    --case-ids cyberv3_claim_identity,cyberv3_claim_vault --writer-targets glm_5_3_baseten --executor-targets gptoss_baseten \
    --batch-size 10 --estimated-cost-usd 3 --tag "$TAG" >> "$LOG" 2>&1 || echo "FAILED: platform check $TAG" >> "$LOG"
echo "=== $(date +%H:%M) [$TAG] platform check done" >> "$LOG"
