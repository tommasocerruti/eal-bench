#!/usr/bin/env bash
# Root-cause diagnosis of every false permission in a set of runs (deterministic localization + judge).
set -u
cd "$(dirname "$0")"
LOG="$1"; OUT="$2"; shift 2
echo "=== $(date +%H:%M) diagnosis start -> $OUT" >> "$LOG"
uv run python -m experiments.diagnose_formation "$@" --out "$OUT" >> "$LOG" 2>&1 || echo "FAILED: diagnosis $OUT" >> "$LOG"
echo "=== $(date +%H:%M) diagnosis done -> $OUT" >> "$LOG"
