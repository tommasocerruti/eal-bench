#!/usr/bin/env bash
# Inkling on Baseten: event sourcing at a completion budget its in-completion reasoning fits, then the two missing cybersecurity rebuild seeds.
set -u
export PATH="$HOME/.local/bin:/c/Users/mikad/.local/bin:$PATH"
export EAL_EVENT_WRITER_MAX_TOKENS=32768
cd "$(dirname "$0")"
LOG=results/driver_parity_inkling.log
run() {
  local tag; tag=$(printf '%s\n' "$@" | awk '/^--tag$/{getline; print; exit}')
  if [ -n "$tag" ] && ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then echo "=== $(date +%H:%M) SKIP $tag" >> "$LOG"; return 0; fi
  echo "=== $(date +%F_%H:%M) $*" >> "$LOG"; uv run python -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"
}
echo "=== $(date +%F_%H:%M) INKLING CHAIN START (event budget $EAL_EVENT_WRITER_MAX_TOKENS)" >> "$LOG"
ev() { run experiments.run --domain "$1" --study event_sourcing --writer-targets inkling_baseten --executor-targets gptoss_baseten,deepseek_baseten --source-run "$2" --batch-size 6 --estimated-cost-usd 15 --tag "event-s$3-$1-inkling"; }
ev procurement results/procurement/20260907-005931-906340__authorization-memory-writer__paper-writer-s20260719-procurement-inkling 20260719
ev cybersecurity results/cybersecurity/20260907-020100-204117__authorization-memory-writer__paper-writer-s20260812-cybersecurity-inkling 20260812
ev finance results/finance/20260912-182621-935987__authorization-memory-writer__paper-writer-s20260816-finance-inkling 20260816
ev procurement results/procurement/20260913-040715-719855__authorization-memory-writer__paper-writer-s20260821-procurement-inkling 20260821
ev cybersecurity results/cybersecurity/20260907-030704-632480__authorization-memory-writer__paper-writer-s20260821-cybersecurity-inkling 20260821
ev finance results/finance/20260912-194855-372742__authorization-memory-writer__paper-writer-s20260821-finance-inkling 20260821
ev procurement results/procurement/20260907-014252-803048__authorization-memory-writer__paper-writer-s20260822-procurement-inkling 20260822
ev cybersecurity results/cybersecurity/20260907-040631-133475__authorization-memory-writer__paper-writer-s20260822-cybersecurity-inkling 20260822
ev finance results/finance/20260912-211450-775567__authorization-memory-writer__paper-writer-s20260822-finance-inkling 20260822
for seed in 20260821 20260822; do
  run experiments.writer_variants_run --domain cybersecurity --memory-types typed --writing-methods rebuild:3 --executor-targets gptoss_baseten,deepseek_baseten --batch-size 4 --writer-batch-size 4 --estimated-cost-usd 15 --writer-targets inkling_baseten --seed "$seed" --tag "rebuild3-s${seed}-cybersecurity-inkling_baseten"
done
echo "=== $(date +%F_%H:%M) INKLING CHAIN DONE" >> "$LOG"
