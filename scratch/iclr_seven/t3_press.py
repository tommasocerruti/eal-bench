import json, glob, collections
CANON = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
FIXED = {"procurement": 20260719, "cybersecurity": 20260812, "finance": 20260816}
CONDS = ("one_shot_text", "incremental_text", "one_shot_typed", "incremental_typed")
def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d and "glm53" not in d and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    return ds[-1]
def cnt(rows):
    a = [r for r in rows if r["request_authorized"] is True]; u = [r for r in rows if r["request_authorized"] is False]
    return {"trials": len(rows), "pe": sum(r.get("provider_error") is not None for r in rows), "auth_n": len(a), "auth_use": sum(bool(r["requested_action_taken"]) for r in a), "unauth_n": len(u), "unauth_sub": sum(bool(r["requested_action_taken"]) for r in u)}
t3 = collections.defaultdict(collections.Counter); press = {}
for w in ("inkling", "deepseek_v4_1_flash"):
    for dom, seeds in CANON.items():
        for seed in seeds:
            d = latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{w}")
            for l in open(d + "/trials.jsonl", encoding="utf-8"):
                t = json.loads(l); role = t["metadata"]["study"].get("evidence_role")
                if role == "natural_exact_repair": role = "exact_repair"
                if role not in ("natural_error", "exact_repair"): continue
                assert t["request_authorized"] is False and t.get("provider_error") is None
                for key in ((dom, w), (dom, "ALL")):
                    t3[key][role + "_n"] += 1; t3[key][role + "_taken"] += bool(t["requested_action_taken"])
        dp = latest(f"results/{dom}/*__authorization-memory-pressure__paper-pressure-{dom}-{w}")
        prow = [json.loads(l) for l in open(dp + "/trials.jsonl", encoding="utf-8") ]
        base = [json.loads(l) for l in open(latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{FIXED[dom]}-{dom}-{w}") + "/trials.jsonl", encoding="utf-8")]
        src = {r["metadata"]["study"]["source_run"] for r in prow}
        for ex in ("gptoss_baseten", "deepseek_baseten", "BOTH"):
            f = (lambda r: True) if ex == "BOTH" else (lambda r: r["executor"]["target_id"] == ex)
            P = cnt([r for r in prow if f(r) and r["condition_id"] in CONDS and r["metadata"]["study"]["evidence_role"] == "generated_final"])
            B = cnt([r for r in base if f(r) and r["condition_id"] in CONDS and r["metadata"]["study"]["evidence_role"] == "generated_final"])
            press[f"{w}|{dom}|{ex}"] = {"B": B, "P": P}
            print(f"PRESS {w:20s} {dom:14s} {ex:16s} B: AU={B['auth_use']}/{B['auth_n']}={100*B['auth_use']/B['auth_n']:.1f} US={B['unauth_sub']}/{B['unauth_n']}={100*B['unauth_sub']/B['unauth_n']:.1f} | P: AU={P['auth_use']}/{P['auth_n']}={100*P['auth_use']/P['auth_n']:.1f} US={P['unauth_sub']}/{P['unauth_n']}={100*P['unauth_sub']/P['unauth_n']:.1f} pe={P['pe']} src={[s.split('__')[-1][:60] for s in src]}")
for k in sorted(t3): c = t3[k]; print(f"T3 {k[0]:14s} {k[1]:20s} nat={c['natural_error_taken']}/{c['natural_error_n']} repair={c['exact_repair_taken']}/{c['exact_repair_n']}")
json.dump({"t3": {"|".join(k): dict(v) for k, v in t3.items()}, "press": press}, open(r"C:/Users/mikad/.claude/jobs/e03609a8/tmp/seven/t3_press.json", "w"), indent=1)
