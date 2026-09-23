"""Added-writer transition counts (error introduction, persistence, self-repair) over typed-incremental positions,
one failure_mechanisms call per run. Definitions match analysis/event_sourcing.py: prior = the same case's previous
state; introduction = error now and not before, persistence = error now and before, self-repair = clean now, error before."""
import json, glob, collections, sys
from pathlib import Path
sys.path.insert(0, ".")
import analysis.failure_mechanisms as fm
CANON = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
def latest(p):
    ds=[d for d in sorted(glob.glob(p)) if "superseded" not in d and "glm53" not in d and json.load(open(d+"/manifest.json",encoding="utf-8")).get("status")=="completed"]
    return ds[-1]
agg=collections.Counter()
for w in ("inkling","deepseek_v4_1_flash"):
    for dom,seeds in CANON.items():
        for seed in seeds:
            d=latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{w}")
            tid=json.load(open(d+"/manifest.json",encoding="utf-8"))["writer"]["target_routes"][0]["target_id"]
            fm.WRITER_LABELS.setdefault(tid,tid)
            tables,_=fm._build_rows([fm.RunSpec(dom,tid,Path(d))])
            st=[r for r in tables["state_observations.csv"] if r.get("condition_id")=="incremental_typed"]
            st.sort(key=lambda r:(str(r["case_id"]), int(r["update_index"])))
            prev={}
            c=collections.Counter()
            for r in st:
                sem = not r["semantic_correct"]; p=prev.get(str(r["case_id"]))
                c["positions"]+=1
                if sem and p is False: c["introduction"]+=1
                if sem and p is True: c["persistence"]+=1
                if (not sem) and p is True: c["self_repair"]+=1
                prev[str(r["case_id"])]=sem
            print(w,dom,seed,dict(c),flush=True); agg.update(c)
print("ADDED TOTALS", dict(agg))
five={"positions":5550,"introduction":587,"persistence":2869,"self_repair":207}
tot={k:five[k]+agg[k] for k in five}
print("SEVEN-WRITER TOTALS", tot)
for k in ("introduction","persistence","self_repair"):
    print(f"  {k}: {tot[k]}/{tot['positions']} = {100*tot[k]/tot['positions']:.1f}%")
json.dump({"added":dict(agg),"seven":tot}, open("scratch/iclr_seven/transitions_added.json","w"), indent=1)
