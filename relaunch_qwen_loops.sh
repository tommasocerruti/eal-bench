#!/usr/bin/env bash
# Start the Qwen closed-loop streams once the large Qwen memory-design runs have finished and freed memory.
cd "$(dirname "$0")"
while ! ( grep -q "^q_cyber_s0 DONE" results/parity_streams.done && grep -q "^q_fin_s0 DONE" results/parity_streams.done ); do sleep 120; done
(nohup bash stream_q_loop_cyber.sh > /dev/null 2>&1 &)
sleep 2
(nohup bash stream_q_loop_pf.sh > /dev/null 2>&1 &)
echo "qwen loops relaunched $(date +%F_%H:%M)" >> results/driver_relaunch.log
