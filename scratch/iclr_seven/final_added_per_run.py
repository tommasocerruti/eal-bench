import json, glob, collections, sys
from pathlib import Path
sys.path.insert(0, ".")
import analysis.failure_mechanisms as fm
CANON = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d and "glm53" not in d and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    return ds[-1]
agg = collections.Counter(); status = collections.Counter()
for w in ("inkling", "deepseek_v4_1_flash"):
    for dom, seeds in CANON.items():
        for seed in seeds:
            d = latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{w}")
            tid = json.load(open(d + "/manifest.json", encoding="utf-8"))["writer"]["target_routes"][0]["target_id"]
            fm.WRITER_LABELS.setdefault(tid, tid)
            tables, meta = fm._build_rows([fm.RunSpec(dom, tid, Path(d))])
            st = [r for r in tables["state_observations.csv"] if r.get("condition_id") == "incremental_typed"]
            for r in st: status[str(r["state_status"])] += 1
            last = {}
            for r in st: last[(r["memory_id"])] = r  # one final state per memory (last update index)
            byc = {}
            for r in st:
                k = r["case_id"]
                if k not in byc or int(r["update_index"]) > int(byc[k]["update_index"]): byc[k] = r
            c = collections.Counter(final_memories=len(byc), final_not_exact=sum(not r["fidelity_exact"] for r in byc.values()),
                                    final_status_not_exact=sum(not r["fidelity_exact"] for r in st if str(r["state_status"]) == "final"), final_status_n=sum(str(r["state_status"]) == "final" for r in st))
            print(w, dom, seed, dict(c), flush=True); agg.update(c)
print("STATUS VALUES", dict(status)); print("ADDED TOTALS", dict(agg))
json.dump({"agg": dict(agg), "status": dict(status)}, open("scratch/iclr_seven/final_added_per_run.json", "w"), indent=1)
