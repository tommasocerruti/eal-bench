import json, glob, collections, sys, csv
from pathlib import Path
sys.path.insert(0, ".")
import analysis.failure_mechanisms as fm
OUT = Path(r"C:/Users/mikad/.claude/jobs/e03609a8/tmp/seven/fm"); OUT.mkdir(exist_ok=True)
CANON = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d and "glm53" not in d and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    return ds[-1]
specs = []
for w in ("inkling", "deepseek_v4_1_flash"):
    for dom, seeds in CANON.items():
        for seed in seeds:
            d = latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{w}")
            tid = json.load(open(d + "/manifest.json", encoding="utf-8"))["writer"]["target_routes"][0]["target_id"]
            fm.WRITER_LABELS.setdefault(tid, tid)
            specs.append(fm.RunSpec(dom, tid, Path(d)))
tables, meta = fm._build_rows(specs)
for name, rows in tables.items():
    if rows:
        with open(OUT / name, "w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r})); wr.writeheader()
            for r in rows: wr.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in r.items()})
prop = tables["propagation_events.csv"]
rows = [r for r in prop if r["request_set"] == "final_matched_request" and r["condition_id"] == "incremental_typed"]
uniq = {}
for r in rows:
    key = (r["source_run"], r["state_id"], r["probe_id"])
    uniq.setdefault(key, []).append(r)
print("unique (run,state,probe):", len(uniq), "| unique (run,memory,probe):", len({(r['source_run'], r['memory_id'], r['probe_id']) for r in rows}), "| rows:", len(rows))
bad = [k for k, v in uniq.items() if len({x["memory_apparent_authority"] for x in v}) != 1 or len(v) != 2]
print("inconsistent/odd groups:", len(bad))
by = collections.defaultdict(collections.Counter)
for key, v in uniq.items():
    r = v[0]; F = bool(r["memory_apparent_authority"])
    for k in ((r["domain"], r["writer_target"]), (r["domain"], "ALL")):
        by[k]["n"] += 1; by[k]["F"] += F; by[k]["sub_trials"] += sum(bool(x["requested_action_taken"]) for x in v); by[k]["trials"] += len(v)
        by[k]["F_and_sub"] += sum(bool(x["requested_action_taken"]) for x in v if F); by[k]["notF_and_sub"] += sum(bool(x["requested_action_taken"]) for x in v if not F)
for k in sorted(by):
    c = by[k]; print(f"PF {k[0]:14s} {k[1]:28s} F={c['F']}/{c['n']}={100*c['F']/c['n']:.1f}%  US={c['sub_trials']}/{c['trials']}={100*c['sub_trials']/c['trials']:.1f}%  sub|F={c['F_and_sub']}/{2*c['F']}  sub|notF={c['notF_and_sub']}/{2*(c['n']-c['F'])}")
json.dump({"|".join(k): dict(v) for k, v in by.items()}, open(OUT.parent / "pf_added2.json", "w"), indent=1)
# per-seed and per-executor generated_final counts for the multiseed appendix
CONDS = ("one_shot_text", "incremental_text", "one_shot_typed", "incremental_typed")
per = collections.defaultdict(collections.Counter)
for s in specs:
    seed = json.load(open(s.path / "manifest.json", encoding="utf-8"))["writer"]["target_routes"][0]["call_profiles"][0]["effective_parameters"]["seed"]
    for l in open(s.path / "trials.jsonl", encoding="utf-8"):
        t = json.loads(l)
        if t["metadata"]["study"].get("evidence_role") != "generated_final" or t["condition_id"] not in CONDS: continue
        for key in ((s.domain, str(seed), t["condition_id"], "BOTH"), (s.domain, "ALL", t["condition_id"], t["executor"]["target_id"]), (s.domain, "ALL", "ALL", t["executor"]["target_id"])):
            c = per[key]; c["trials"] += 1
            if t["request_authorized"]: c["auth_n"] += 1; c["auth_use"] += bool(t["requested_action_taken"])
            else: c["unauth_n"] += 1; c["unauth_sub"] += bool(t["requested_action_taken"])
json.dump({"|".join(k): dict(v) for k, v in per.items()}, open(OUT.parent / "added_per_seed_executor.json", "w"), indent=1)
print("per-seed/executor keys:", len(per))
