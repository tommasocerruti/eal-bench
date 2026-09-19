#!/usr/bin/env bash
# waittag TAG: block while a run with this tag is still being written by another process; return when it is completed or has gone quiet for 15 minutes.
tag="$1"
while true; do
  if ls -d results/*/*__"$tag" >/dev/null 2>&1 && grep -lq '"status": "completed"' results/*/*__"$tag"/manifest.json 2>/dev/null; then exit 0; fi
  newest=$(ls -t results/*/*__"$tag"/calls.jsonl 2>/dev/null | head -1)
  [ -n "$newest" ] || exit 0
  age=$(( $(date +%s) - $(stat -c %Y "$newest") ))
  [ "$age" -gt 900 ] && exit 0
  sleep 60
done
