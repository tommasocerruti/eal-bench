import json, glob, collections, sys
OUT = r"C:/Users/mikad/.claude/jobs/e03609a8/tmp/seven"
CANON = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
FIXED = {"procurement": 20260719, "cybersecurity": 20260812, "finance": 20260816}
CONDS = ("one_shot_text", "incremental_text", "one_shot_typed", "incremental_typed")
def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d and "glm53" not in d and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    assert len(ds) >= 1, pattern
    return ds[-1]
def cnt(rows):
    a = [r for r in rows if r["request_authorized"] is True]; u = [r for r in rows if r["request_authorized"] is False]
    return {"trials": len(rows), "pe": sum(r.get("provider_error") is not None for r in rows), "auth_n": len(a), "auth_use": sum(bool(r["requested_action_taken"]) for r in a), "unauth_n": len(u), "unauth_sub": sum(bool(r["requested_action_taken"]) for r in u)}
res = {"fixed_seed_by_executor": {}, "roles": {}, "pressure": {}, "repair": {}}
for w in ("inkling", "deepseek_v4_1_flash"):
    for dom, seeds in CANON.items():
        # roles + repair + fixed seed per executor
        for seed in seeds:
            d = latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{w}")
            rows = [json.loads(l) for l in open(d + "/trials.jsonl", encoding="utf-8")]
            roles = collections.Counter((r["metadata"]["study"].get("evidence_role"), "repair" in r["condition_id"]) for r in rows)
            res["roles"][f"{w}|{dom}|{seed}"] = {str(k): v for k, v in roles.items()}
            if seed == FIXED[dom]:
                for ex in ("gptoss_baseten", "deepseek_baseten"):
                    for c in CONDS:
                        sel = [r for r in rows if r["executor"]["target_id"] == ex and r["condition_id"] == c and r["metadata"]["study"].get("evidence_role") == "generated_final"]
                        res["fixed_seed_by_executor"][f"{w}|{dom}|{ex}|{c}"] = cnt(sel)
        # pressure run
        dp = latest(f"results/{dom}/*__authorization-memory-pressure__paper-pressure-{dom}-{w}")
        prow = [json.loads(l) for l in open(dp + "/trials.jsonl", encoding="utf-8")]
        keys = collections.Counter((r["metadata"]["study"].get("evidence_role"), r["metadata"]["study"].get("arm") or r["metadata"]["study"].get("pressure_arm") or ("pressure" if r["metadata"]["study"].get("pressure_id") else None), r["condition_id"] in CONDS) for r in prow)
        res["pressure"][f"{w}|{dom}|__keys"] = {str(k): v for k, v in keys.items()}
        st_keys = collections.Counter()
        for r in prow: st_keys.update(r["metadata"]["study"].keys())
        res["pressure"][f"{w}|{dom}|__study_keys"] = dict(st_keys)
        res["pressure"][f"{w}|{dom}|__manifest_counts"] = json.load(open(dp + "/manifest.json", encoding="utf-8")).get("counts")
        res["pressure"][f"{w}|{dom}|__dir"] = dp
json.dump(res, open(OUT + "/added_counts_v2.json", "w"), indent=1)
for k, v in res["roles"].items(): print("ROLES", k, v)
for k, v in res["pressure"].items():
    if "__keys" in k or "__study_keys" in k: print("PRESS", k, json.dumps(v)[:600])
print(json.dumps(res["pressure"]["inkling|procurement|__manifest_counts"])[:800])
