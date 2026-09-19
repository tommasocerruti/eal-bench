#!/usr/bin/env bash
# One-shot typed source-authority gate runs for Inkling and Flash at the primary seed (Baseten only).
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
run experiments.run --domain procurement --study source_authority --source-run "results/procurement/20260907-005931-906340__authorization-memory-writer__paper-writer-s20260719-procurement-inkling" --writer-strategy one_shot --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --estimated-cost-usd 6 --tag "gate1shot-s20260719-procurement-inkling"
run experiments.run --domain cybersecurity --study source_authority --source-run "results/cybersecurity/20260907-020100-204117__authorization-memory-writer__paper-writer-s20260812-cybersecurity-inkling" --writer-strategy one_shot --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --estimated-cost-usd 6 --tag "gate1shot-s20260812-cybersecurity-inkling"
run experiments.run --domain finance --study source_authority --source-run "results/finance/20260912-182621-935987__authorization-memory-writer__paper-writer-s20260816-finance-inkling" --writer-strategy one_shot --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --estimated-cost-usd 6 --tag "gate1shot-s20260816-finance-inkling"
run experiments.run --domain procurement --study source_authority --source-run "results/procurement/20260912-182648-422469__authorization-memory-writer__paper-writer-s20260719-procurement-deepseek_v4_1_flash" --writer-strategy one_shot --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --estimated-cost-usd 6 --tag "gate1shot-s20260719-procurement-deepseek_v4_1_flash"
run experiments.run --domain cybersecurity --study source_authority --source-run "results/cybersecurity/20260912-192002-963969__authorization-memory-writer__paper-writer-s20260812-cybersecurity-deepseek_v4_1_flash" --writer-strategy one_shot --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --estimated-cost-usd 6 --tag "gate1shot-s20260812-cybersecurity-deepseek_v4_1_flash"
run experiments.run --domain finance --study source_authority --source-run "results/finance/20260912-182706-038487__authorization-memory-writer__paper-writer-s20260816-finance-deepseek_v4_1_flash" --writer-strategy one_shot --executor-targets gptoss_baseten,deepseek_baseten --batch-size 6 --estimated-cost-usd 6 --tag "gate1shot-s20260816-finance-deepseek_v4_1_flash"
echo "gate_oneshot_added DONE $(date +%F_%H:%M)" >> results/parity_streams.done
