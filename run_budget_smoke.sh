#!/usr/bin/env bash
# Smoke test of the 16k output budget: two cybersecurity cases, typed incremental, one new writer.
set -u
cd "$(dirname "$0")"
LOG="${1:-results/extensions_driver.log}"; W="$2"
echo "=== $(date +%H:%M) [budget-smoke-$W] start" >> "$LOG"
uv run python -m experiments.writer_variants_run --domain cybersecurity --memory-types typed --writing-methods incremental,rebuild:10 \
    --case-ids cyberv3_claim_identity,cyberv3_claim_vault --writer-targets "$W" --executor-targets gptoss_baseten \
    --batch-size 10 --estimated-cost-usd 4 --tag "budget-smoke-$W" >> "$LOG" 2>&1 || echo "FAILED: budget smoke $W" >> "$LOG"
echo "=== $(date +%H:%M) [budget-smoke-$W] done" >> "$LOG"
