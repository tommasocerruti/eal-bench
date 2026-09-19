#!/usr/bin/env bash
cd "$(dirname "$0")"
export EAL_ROUTE_TIMEOUT_SECONDS=14400
bash fast_parity_qwen_loop_procurement.sh
bash fast_parity_qwen_loop_finance.sh
echo "q_loop_pf DONE $(date +%F_%H:%M)" >> results/parity_streams.done
