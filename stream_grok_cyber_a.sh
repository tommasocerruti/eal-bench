#!/usr/bin/env bash
cd "$(dirname "$0")"
bash waittag.sh mandate-cybersecurity-grok_4_3_openrouter
bash gstream_g_cyber_s1.sh
bash gstream_g_loop_cyber_gptoss.sh
echo "grok_cyber_a DONE $(date +%F_%H:%M)" >> results/parity_streams.done
