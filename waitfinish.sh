#!/usr/bin/env bash
# Wait for the last two Qwen runs, then stop the judge loop and run the finish pipeline.
cd "$(dirname "$0")"
while true; do
  ok=1
  for t in mandate-generated-v2-qwen_plus_0728_openrouter rounds3v2-both-cybersecurity-deepseek-qwen_plus_0728_openrouter; do
    d=$(ls -td results/*/*__$t 2>/dev/null | grep -v superseded | head -1)
    grep -q '"status": "completed"' "$d/manifest.json" 2>/dev/null || ok=0
  done
  [ $ok = 1 ] && break
  sleep 60
done
echo "$(date +%H:%M) last qwen runs DONE" >> results/parity_streams.done
touch STOP_JUDGE
# let the current judge pass finish (it exits at the loop check)
while ! grep -q "judge loop stopped" results/driver_judge_loop.log 2>/dev/null; do sleep 20; done
echo "$(date +%H:%M) judge loop stopped, starting finish" >> results/parity_streams.done
bash run_parity_finish.sh
echo "$(date +%H:%M) FINISH PIPELINE DONE" >> results/parity_streams.done
