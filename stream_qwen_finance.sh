#!/usr/bin/env bash
cd "$(dirname "$0")"
bash fast_parity_qwen_finance.sh
bash fast_parity_qwen_loop_finance.sh
echo "qwen_finance DONE $(date +%F_%H:%M)" >> results/parity_streams.done
