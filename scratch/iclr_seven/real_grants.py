"""Real, active permission records per chain in the closed loop, by arm, against the frozen starting memory.
A record is real if at least one cited source is not a written-back line. Cybersecurity, all writers, both executors."""
import collections
import glob
import json
import sys

WRITERS = sys.argv[1].split(",") if len(sys.argv) > 1 else None
tot = collections.defaultdict(lambda: [0, 0])  # arm -> [records, chains]
for d in sorted(glob.glob("results/*/*rounds3v2-both-cybersecurity-*")):
    if "superseded" in d or (WRITERS and not any(d.endswith(w) for w in WRITERS)):
        continue
    m = json.load(open(d + "/manifest.json", encoding="utf-8"))
    if m.get("status") != "completed" or m["options"].get("loop_content") != "both":
        continue
    arm = {}
    for l in open(d + "/written_back.jsonl", encoding="utf-8"):
        w = json.loads(l)
        if w.get("loop_chain_id"):
            arm[w["loop_chain_id"]] = w["arm"]
    final = {}  # chain -> memory with the largest block index
    for l in open(d + "/memories.jsonl", encoding="utf-8"):
        mem = json.loads(l)
        if mem["architecture"] != "typed":
            continue
        c = mem["chain_id"]
        if c not in final or mem["block_index"] > final[c]["block_index"]:
            final[c] = mem
    for c, mem in final.items():
        a = arm.get(c, "frozen")
        n = 0
        for rec in mem["payload"].get("authorizations", []):
            if rec.get("status") != "active":
                continue
            v = rec.get("source_turn_ids") or ()
            ids = [p.strip() for p in v.split("|")] if isinstance(v, str) else list(v)
            if ids and all(i.startswith("src_loop_") for i in ids):
                continue
            n += 1
        tot[a][0] += n
        tot[a][1] += 1
for a, (r, c) in sorted(tot.items()):
    print(f"{a:8s} chains {c:4d}  real active records per chain {r / c:.1f}")
