"""Accept or reject a completed writer_variants or closed_loop run by provider failures (timeouts, rate limits) in its writer stage.

A writer call that exceeds the canonical 180-second limit is recorded as a writer_error attempt. An update is *lost to a
timeout* when none of its attempts was accepted (or a no-change) and at least one attempt timed out; the memory then keeps
an earlier state for a reason that is provider slowness, not the writer's behavior. Exit code 0 = accept (no update lost to
a timeout), 1 = reject, 2 = no completed run for the tag. Usage: python scratch/check_inkling_run.py <run tag>"""
import glob
import json
import os
import re
import sys

tag = sys.argv[1]
runs = [d for d in glob.glob(f"results/*/*__{tag}") if "superseded" not in d]
runs = [d for d in runs if json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8")).get("status") == "completed"]
if not runs:
    print(f"{tag}: no completed run")
    sys.exit(2)
d = sorted(runs)[-1]
updates = {}
timeouts = 0
for line in open(os.path.join(d, "memory_attempts.jsonl"), encoding="utf-8"):
    a = json.loads(line)
    key = (a["case_id"], a.get("writer_run_id"), a["condition_id"], a["block_index"])
    timed_out = bool(re.search(r"Timeout|TooManyRequests|RateLimit|status_code.: 429", json.dumps(a.get("detail"))))
    timeouts += timed_out
    updates.setdefault(key, []).append((a["status"], timed_out))
lost = [k for k, v in updates.items() if all(s not in ("accepted", "no_change") for s, _ in v) and any(t for _, t in v)]
affected = sum(1 for v in updates.values() if any(t for _, t in v))
print(f"{tag}: {timeouts} timed-out attempts, {affected} of {len(updates)} updates with a timed-out attempt, {len(lost)} lost to a timeout" + (f" {lost}" if lost else ""))
print(d)
sys.exit(1 if lost else 0)
