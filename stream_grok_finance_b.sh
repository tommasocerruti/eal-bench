#!/usr/bin/env bash
cd "$(dirname "$0")"
bash gstream_g_fin_s2.sh
bash gstream_g_loop_fin_deepseek.sh
echo "grok_finance_b DONE $(date +%F_%H:%M)" >> results/parity_streams.done
