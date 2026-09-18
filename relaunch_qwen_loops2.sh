#!/usr/bin/env bash
cd "$(dirname "$0")"
while ! grep -q "^q_cyber_s0 DONE" results/parity_streams.done; do sleep 120; done
for s in q_loop_procurement_gptoss q_loop_procurement_deepseek q_loop_cybersecurity_gptoss q_loop_cybersecurity_deepseek q_loop_finance_gptoss q_loop_finance_deepseek; do (nohup bash $s.sh > /dev/null 2>&1 &); sleep 2; done
echo "qwen loops relaunched (6 streams) $(date +%F_%H:%M)" >> results/driver_relaunch.log
