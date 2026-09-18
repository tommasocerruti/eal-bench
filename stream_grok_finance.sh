#!/usr/bin/env bash
cd "$(dirname "$0")"
bash waittag.sh memtable-finance-grok_4_3_openrouter
bash fast_parity_grok_finance.sh
bash fast_parity_grok_loop_finance.sh
echo "grok_finance DONE $(date +%F_%H:%M)" >> results/parity_streams.done
