"""Recount false-authority formation for the added writers one run per _build_rows call.
failure_mechanisms matches apparent-authority rows by (state_id, probe_id) only; state ids repeat across seed runs,
so pooling several runs of one writer in one call inflates the count. One run per call has no collisions."""
import json, glob, collections, sys
from pathlib import Path
sys.path.insert(0, ".")
import analysis.failure_mechanisms as fm
CANON = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d and "glm53" not in d and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    return ds[-1]
out = {}
tot = collections.defaultdict(lambda: [0, 0])
for w in ("inkling", "deepseek_v4_1_flash"):
    for dom, seeds in CANON.items():
        for seed in seeds:
            d = latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{w}")
            tid = json.load(open(d + "/manifest.json", encoding="utf-8"))["writer"]["target_routes"][0]["target_id"]
            fm.WRITER_LABELS.setdefault(tid, tid)
            tables, meta = fm._build_rows([fm.RunSpec(dom, tid, Path(d))])
            rows = [r for r in tables["propagation_events.csv"] if r["request_set"] == "final_matched_request" and r["condition_id"] == "incremental_typed"]
            uniq = {}
            for r in rows: uniq.setdefault((r["state_id"], r["probe_id"]), []).append(r)
            f = sum(bool(v[0]["memory_apparent_authority"]) for v in uniq.values()); n = len(uniq)
            sub_f = sum(bool(x["requested_action_taken"]) for v in uniq.values() if v[0]["memory_apparent_authority"] for x in v)
            tf = sum(len(v) for v in uniq.values() if v[0]["memory_apparent_authority"])
            out[f"{w}|{dom}|{seed}"] = {"F": f, "n": n, "sub_given_F": sub_f, "trials_given_F": tf, "run": d}
            tot[dom][0] += f; tot[dom][1] += n
            print(w, dom, seed, f"F {f}/{n}  sub|F {sub_f}/{tf}", flush=True)
print("added-writer totals per domain:", dict(tot))
json.dump({"per_run": out, "added_totals": dict(tot)}, open("scratch/iclr_seven/pf_added_per_run.json", "w"), indent=1)
