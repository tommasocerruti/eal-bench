"""Health check for the extension drivers: per-model request rate over the last window, retries, errors,
per-driver progress, process counts. Read-only. Usage: uv run python monitor_health.py [window_minutes]"""
import glob, json, os, re, subprocess, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

window = int(sys.argv[1]) if len(sys.argv) > 1 else 15
now = datetime.now(timezone.utc)
since = now - timedelta(minutes=window)
LAUNCH = "20260914-1039"  # run dirs created before this belong to earlier launches
RUN_RE = re.compile(r"^\d{8}-\d{6}-")
print(f"# health {now.astimezone().strftime('%H:%M')} local, window {window} min")

# processes
try:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(bash|uv|python)[.]exe$' } | Group-Object Name | ForEach-Object { \"$($_.Name)=$($_.Count)\" }"],
        capture_output=True, text=True, timeout=60).stdout.split()
    print("processes:", " ".join(out) or "none")
except Exception as e:  # noqa: BLE001
    print("processes: ?", e)

# drivers
for log in sorted(glob.glob("results/driver_run_extensions_*.log")):
    lines = open(log, encoding="utf-8", errors="replace").read().splitlines()
    starts = [l for l in lines if l.startswith("=== ")]
    failed = sum(1 for l in lines if l.startswith("FAILED:"))
    tb = sum(1 for l in lines if l.startswith("Traceback"))
    last = starts[-1] if starts else "(no START yet)"
    name = os.path.basename(log)[len("driver_run_extensions_"):-4]
    flag = "  <-- CHECK" if failed or tb else ""
    print(f"driver {name:>3}: {len([l for l in starts if 'SKIP' not in l and 'PHASE' not in l])} launched, {len([l for l in starts if 'SKIP' in l])} skipped, FAILED={failed} Traceback={tb}{flag}")
    print(f"      last: {last[:150]}")

# runs from this launch
runs = sorted(d for d in glob.glob("results/*/*__*") if RUN_RE.match(os.path.basename(d)) and os.path.basename(d) >= LAUNCH and os.path.isdir(d))
calls = defaultdict(Counter)
lat = defaultdict(list)
print(f"runs from this launch: {len(runs)}")
for d in runs:
    tag = os.path.basename(d).split("__")[-1]
    m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8")) if os.path.exists(os.path.join(d, "manifest.json")) else {}
    status = m.get("status", "?")
    counts = {os.path.basename(f)[:-6]: sum(1 for _ in open(f, encoding="utf-8", errors="replace")) for f in glob.glob(os.path.join(d, "*.jsonl"))}
    print(f"  {status:>9} {tag}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    cf = os.path.join(d, "calls.jsonl")
    if os.path.exists(cf):
        with open(cf, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = datetime.fromisoformat(r["ts"])
                if ts < since:
                    continue
                t = r.get("target_id", "?")
                calls[t]["n"] += 1
                if r.get("error"):
                    calls[t]["error"] += 1
                    err = str(r["error"])
                    if "429" in err or "rate" in err.lower():
                        calls[t]["error_429"] += 1
                if (r.get("attempts") or 1) > 1:
                    calls[t]["retried"] += 1
                if r.get("latency_ms") is not None:
                    lat[t].append(r["latency_ms"])
print(f"API calls in the last {window} min, per model (target: rpm, retried, errors, 429/rate errors, median latency):")
for t in sorted(calls):
    c = calls[t]
    ls = sorted(lat[t])
    med = ls[len(ls) // 2] / 1000 if ls else 0
    print(f"  {t:<26} {c['n'] / window:6.1f} rpm  retried={c['retried']:<4} errors={c['error']:<3} rate={c['error_429']:<3} med={med:.1f}s")
