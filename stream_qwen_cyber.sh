#!/usr/bin/env bash
cd "$(dirname "$0")"
bash fast_parity_qwen_cyber.sh
bash fast_parity_qwen_loop_cybersecurity.sh
echo "qwen_cyber DONE $(date +%F_%H:%M)" >> results/parity_streams.done
