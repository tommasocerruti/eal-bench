"""Run the event-sourcing analysis for each completed Inkling event rerun against its paper-writer source run."""
import glob, json, re, subprocess, sys, os
src_lines = open("run_parity_inkling.sh", encoding="utf-8").read()
for d in sorted(glob.glob("results/*/*__event-s*-inkling")):
    d = d.replace(chr(92), "/")
    try:
        if json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") != "completed":
            continue
    except Exception:
        continue
    tag = d.split("__")[-1]; m = re.match(r"event-s(\d+)-([a-z]+)-inkling", tag)
    seed, dom = m.group(1), m.group(2)
    src = re.search(r"ev " + dom + r" (results/" + dom + r"/\S*paper-writer-s" + seed + r"-" + dom + r"-inkling) " + seed, src_lines)
    if not src:
        print("no source for", tag); continue
    out = "results/analysis/event_sourcing/" + tag
    if os.path.exists(out + "/paired_metrics.jsonl"):
        print("exists", tag); continue
    r = subprocess.run([sys.executable, "-m", "analysis.event_sourcing", "--event-run", d, "--baseline-run", src.group(1), "--output", out], capture_output=True, text=True)
    print(tag, "ok" if r.returncode == 0 else "FAILED " + r.stderr[-300:])
