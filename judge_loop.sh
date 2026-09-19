#!/usr/bin/env bash
# After the two running judge passes end, judge newly completed parity runs every five minutes until STOP_JUDGE exists.
cd "$(dirname "$0")"
export PYTHONIOENCODING=utf-8 PYTHONPATH=.
while ! ( grep -q "^loop-both" results/driver_judge_incremental_1.log && grep -q "^loop-both" results/driver_judge_incremental_2.log ); do sleep 60; done
n=3
while [ ! -f STOP_JUDGE ]; do
  .venv/Scripts/python.exe scratch/iclr_seven/judge_incremental.py > results/driver_judge_incremental_$n.log 2>&1
  n=$((n+1)); sleep 300
done
echo "judge loop stopped $(date +%F_%H:%M)" >> results/driver_judge_loop.log
