#!/usr/bin/env bash
cd "$(dirname "$0")"
bash fast_run_extensions_29mA.sh
bash fast_parity_qwen_loop_procurement.sh
echo "qwen_proc DONE $(date +%F_%H:%M)" >> results/parity_streams.done
