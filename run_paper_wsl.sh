#!/usr/bin/env bash
# Paper writer and pressure routes for the new writers on cybersecurity (and finance once its route is open),
# run under WSL because the release checks key file hashes by POSIX relative path.
set -u
cd /mnt/c/Users/mikad/Documents/GitHub/eal-bench || exit 1
export PATH="$HOME/.local/bin:$PATH"
PY=/home/mika/eal-venv/bin/python
LOG="${1:-results/extensions_driver.log}"
DOMAINS="${2:-cybersecurity}"; DOMAINS="${DOMAINS//,/ }"
BATCH="${3:-10}"
run() { echo "=== $(date +%H:%M) [wsl] $*" >> "$LOG"; "$PY" -m "$@" >> "$LOG" 2>&1 || echo "FAILED: $*" >> "$LOG"; }

echo "=== $(date +%H:%M) [wsl] PAPER ROUTES START ($DOMAINS)" >> "$LOG"
for w in glm_5_3_baseten inkling_baseten; do
  short=${w%_baseten}
  for d in $DOMAINS; do
    case "$d" in
      cybersecurity) seeds="20260812 20260821 20260822";;
      finance) seeds="20260816 20260821 20260822";;
      procurement) seeds="20260719 20260821 20260822";;
    esac
    for seed in $seeds; do
      run experiments.run --domain "$d" --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study writer \
          --writer-targets "$w" --executor-targets gptoss_baseten,deepseek_baseten --writer-runs 1 --executor-runs 1 \
          --writer-max-attempts 2 --capacity-tier primary --seed "$seed" --batch-size "$BATCH" --estimated-cost-usd 30 \
          --tag "paper-writer-s$seed-$d-$short"
    done
    fixed=${seeds%% *}
    src=$(ls -d results/$d/*__authorization-memory-writer__paper-writer-s$fixed-$d-$short 2>/dev/null | tail -1)
    if [ -n "$src" ]; then
      run experiments.run --domain "$d" --corpus-version benchmark_v1 --presentation-version naturalistic_v1 --study pressure \
          --source-run "$src" --batch-size "$BATCH" --estimated-cost-usd 12 --tag "paper-pressure-$d-$short"
    else
      echo "FAILED: no writer run found for pressure on $d $short" >> "$LOG"
    fi
  done
done
echo "=== $(date +%H:%M) [wsl] PAPER ROUTES DONE ($DOMAINS)" >> "$LOG"
