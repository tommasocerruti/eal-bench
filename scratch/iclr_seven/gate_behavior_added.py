"""Executor behavior before and after source-authority gating for the added writers at the primary seed, both typed
conditions: incremental typed from the gate runs, one-shot typed from the gate1shot runs. Pools both executors.
Prints seven-writer rows for the executor-behavior table (five-writer counts published + added counts)."""
import collections
import glob
import json

PRIMARY = {"procurement": 20260719, "cybersecurity": 20260812, "finance": 20260816}
W = ["inkling", "deepseek_v4_1_flash"]
FIVE = {"ORIGINAL": (2535, 2640, 331, 2640), "GATED": (1983, 2640, 85, 2640)}  # LA k/n, UA k/n


def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d
          and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    assert ds, pattern
    return ds[-1]


c = collections.Counter()
for dom, seed in PRIMARY.items():
    for w in W:
        for pre in ("gate", "gate1shot"):
            d = latest(f"results/{dom}/*__{pre}-s{seed}-{dom}-{w}")
            for l in open(d + "/trials.jsonl", encoding="utf-8"):
                t = json.loads(l)
                if t.get("provider_error"):
                    continue
                v = t["metadata"]["study"]["variant"]
                if t["request_authorized"]:
                    c[(v, "la_n")] += 1; c[(v, "la_k")] += int(bool(t["requested_action_taken"]))
                else:
                    c[(v, "ua_n")] += 1; c[(v, "ua_k")] += int(bool(t["unauthorized_action_taken"]))
for v in ("ORIGINAL", "GATED"):
    print(f"added {v}: LA {c[(v, 'la_k')]}/{c[(v, 'la_n')]}  UA {c[(v, 'ua_k')]}/{c[(v, 'ua_n')]}")
    lk, ln, uk, un = FIVE[v]
    LK, LN, UK, UN = lk + c[(v, "la_k")], ln + c[(v, "la_n")], uk + c[(v, "ua_k")], un + c[(v, "ua_n")]
    print(f"ROW {v}: {LK}/{LN} ({100 * LK / LN:.1f}%) & {UK}/{UN} ({100 * UK / UN:.1f}%)")
json.dump({k[0] + "|" + k[1]: v for k, v in c.items()}, open("scratch/iclr_seven/gate_behavior_added.json", "w", encoding="utf-8"), indent=1)
