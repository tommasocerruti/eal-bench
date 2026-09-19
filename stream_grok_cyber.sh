#!/usr/bin/env bash
cd "$(dirname "$0")"
bash waittag.sh memtable-cybersecurity-grok_4_3_openrouter
bash fast_parity_grok_cyber.sh
bash fast_parity_grok_loop_cybersecurity.sh
echo "grok_cyber DONE $(date +%F_%H:%M)" >> results/parity_streams.done
