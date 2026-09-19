#!/usr/bin/env bash
cd "$(dirname "$0")"
bash waittag.sh mandate-procurement-grok_4_3_openrouter
bash fast_run_extensions_29lA.sh
bash fast_parity_grok_loop_procurement.sh
echo "grok_proc DONE $(date +%F_%H:%M)" >> results/parity_streams.done
