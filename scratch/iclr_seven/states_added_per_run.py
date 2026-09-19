"""State-level typed-incremental counts for the added writers, one run per _build_rows call (see pf_added_per_run.py)."""
import json, glob, collections, sys
from pathlib import Path
sys.path.insert(0, ".")
import analysis.failure_mechanisms as fm
CANON = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d and "glm53" not in d and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    return ds[-1]
agg = collections.Counter(); keys_printed = False
for w in ("inkling", "deepseek_v4_1_flash"):
    for dom, seeds in CANON.items():
        for seed in seeds:
            d = latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{w}")
            tid = json.load(open(d + "/manifest.json", encoding="utf-8"))["writer"]["target_routes"][0]["target_id"]
            fm.WRITER_LABELS.setdefault(tid, tid)
            tables, meta = fm._build_rows([fm.RunSpec(dom, tid, Path(d))])
            st = [r for r in tables["state_observations.csv"] if r.get("condition_id") == "incremental_typed"]
            if not keys_printed:
                print(sorted(st[0].keys()), flush=True); keys_printed = True
            fin = [r for r in st if r.get("is_final") or r.get("role") == "final" or r.get("block_role") == "final"]
            c = collections.Counter(positions=len(st), semantic=sum(not r["semantic_correct"] for r in st), gain=sum(int(r["authority_gain_error_count"]) > 0 for r in st),
                                    final_states=len(fin), final_not_exact=sum(not r["fidelity_exact"] for r in fin), apparent_states=sum(bool(r["apparent_authority"]) for r in st))
            print(w, dom, seed, dict(c), flush=True); agg.update(c)
print("ADDED TOTALS", dict(agg))
json.dump(dict(agg), open("scratch/iclr_seven/states_added_per_run.json", "w"), indent=1)
