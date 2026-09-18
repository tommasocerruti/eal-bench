"""Move unfinished run directories that were replaced by a later attempt of the same tag to results/superseded."""
import collections, glob, json, os, shutil
by_tag = collections.defaultdict(list)
for d in glob.glob("results/*/2026*__*"):
    d = d.replace(chr(92), "/")
    if "superseded" in d or "analysis" in d:
        continue
    try:
        st = json.load(open(d + "/manifest.json", encoding="utf-8")).get("status")
    except Exception:
        st = None
    by_tag[d.split("__")[-1]].append((d, st))
moved = 0
for tag, ds in by_tag.items():
    if len(ds) < 2:
        continue
    completed = [d for d, st in ds if st == "completed"]
    keep = sorted(completed)[-1] if completed else sorted(d for d, _ in ds)[-1]
    for d, st in ds:
        if d != keep and st != "completed":
            shutil.move(d, "results/superseded/" + os.path.basename(d)); moved += 1
print("superseded", moved, "stale directories")
