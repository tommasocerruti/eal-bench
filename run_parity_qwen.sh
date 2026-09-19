#!/usr/bin/env bash
# Qwen-Plus parity chain: open-loop extension runs, then the closed loop. Sequential, one run at a time.
cd "$(dirname "$0")"
LOG=results/driver_parity_qwen.log
for s in run_extensions_29mA.sh run_extensions_29mB.sh run_extensions_29k_procurement.sh run_extensions_29k_cybersecurity.sh run_extensions_29k_finance.sh; do
  echo "=== $(date +%F_%H:%M) CHAIN START $s" >> "$LOG"; bash "$s" "$LOG"; echo "=== $(date +%F_%H:%M) CHAIN END $s" >> "$LOG"
done
echo "=== $(date +%F_%H:%M) PARITY QWEN DONE" >> "$LOG"
