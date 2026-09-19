#!/usr/bin/env bash
cd "$(dirname "$0")"
bash waittag.sh memtable-s20260821-finance-grok_4_3_openrouter
bash gstream_g_fin_s1.sh
bash gstream_g_loop_fin_gptoss.sh
echo "grok_finance_a DONE $(date +%F_%H:%M)" >> results/parity_streams.done
