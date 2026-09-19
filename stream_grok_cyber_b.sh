#!/usr/bin/env bash
cd "$(dirname "$0")"
bash gstream_g_cyber_s2.sh
bash gstream_g_loop_cyber_deepseek.sh
echo "grok_cyber_b DONE $(date +%F_%H:%M)" >> results/parity_streams.done
