#!/usr/bin/env bash
# Grok 4.3 parity chain: open-loop extension runs, then the closed loop. Sequential, one run at a time.
cd "$(dirname "$0")"
LOG=results/driver_parity_grok.log
for s in run_extensions_29lA.sh run_extensions_29lB.sh run_extensions_29j_procurement.sh run_extensions_29j_cybersecurity.sh run_extensions_29j_finance.sh; do
  echo "=== $(date +%F_%H:%M) CHAIN START $s" >> "$LOG"; bash "$s" "$LOG"; echo "=== $(date +%F_%H:%M) CHAIN END $s" >> "$LOG"
done
echo "=== $(date +%F_%H:%M) PARITY GROK DONE" >> "$LOG"
