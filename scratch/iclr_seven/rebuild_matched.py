"""Rebuild-every-3 cells and their matched typed-incremental baselines (same writer, seed, executors), per domain."""
import glob
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
W = ["glm_5_2_baseten", "kimi_baseten", "nemotron_3_ultra_baseten", "inkling_baseten", "deepseek_v4_1_flash_baseten"]
ADDED = {"inkling_baseten", "deepseek_v4_1_flash_baseten"}
SEEDS = {"procurement": ["20260719", "20260821", "20260822"], "cybersecurity": ["20260812", "20260821", "20260822"], "finance": ["20260816", "20260821", "20260822"]}


def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d and "glm53" not in d]
    for d in reversed(ds):
        m = json.load(open(d + "/manifest.json", encoding="utf-8"))
        if m.get("status") == "completed":
            return d, m
    return None, None


def counts(d, cond):
    """AU and US counts for one condition from the trials themselves (both executors)."""
    au = [0, 0]; us = [0, 0]; pe = 0
    for line in open(d + "/trials.jsonl", encoding="utf-8"):
        t = json.loads(line)
        if t["condition_id"] != cond:
            continue
        if t.get("provider_error") is not None:
            pe += 1; continue
        if t["request_authorized"]:
            au[1] += 1; au[0] += bool(t["requested_action_taken"])
        else:
            us[1] += 1; us[0] += bool(t["requested_action_taken"])
    return au, us, pe


for dom, seeds in SEEDS.items():
    tot = {"base": [0, 0, 0, 0], "rebuild": [0, 0, 0, 0]}; cells = []
    for seed in seeds:
        for w in W:
            canonical = seed == seeds[0]
            if dom == "procurement":
                base_pat = f"results/procurement/*__{'newwriter-s' if w in ADDED else 'seeds-'}{seed}-{w}"
                reb_pat = base_pat; reb_cond = "incremental_typed__rebuild3"
            elif canonical:
                base_pat = f"results/{dom}/*__memtable-{dom}-{w}"; reb_pat = base_pat; reb_cond = "incremental_typed__rebuild3"
            else:
                base_pat = f"results/{dom}/*__memtable-s{seed}-{dom}-{w}"; reb_pat = f"results/{dom}/*__rebuild3-s{seed}-{dom}-{w}"; reb_cond = None
            bd, bm = latest(base_pat); rd, rm = latest(reb_pat)
            if bd is None or rd is None:
                cells.append((seed, w, "MISSING", bd is not None, rd is not None)); continue
            if reb_cond is None:
                conds = sorted({json.loads(l)["condition_id"] for l in open(rd + "/trials.jsonl", encoding="utf-8")})
                reb_cond = [c for c in conds if "rebuild" in c or c == "incremental_typed"][0]
            bau, bus, bpe = counts(bd, "incremental_typed"); rau, rus, rpe = counts(rd, reb_cond)
            if bus[1] == 0 or rus[1] == 0:
                cells.append((seed, w, "NOCOND", bus[1], rus[1], reb_cond)); continue
            for k, (a, u) in (("base", (bau, bus)), ("rebuild", (rau, rus))):
                tot[k][0] += u[0]; tot[k][1] += u[1]; tot[k][2] += a[0]; tot[k][3] += a[1]
            cells.append((seed, w, f"base US {bus[0]}/{bus[1]} AU {bau[0]}/{bau[1]} | rebuild US {rus[0]}/{rus[1]} AU {rau[0]}/{rau[1]} pe {bpe}+{rpe} [{reb_cond}]"))
    b, r = tot["base"], tot["rebuild"]
    print(f"== {dom}: cells used {sum(1 for c in cells if 'base US' in str(c))}")
    for c in cells:
        print("   ", c)
    if b[1]:
        print(f"   MATCHED typed incremental: US {100*b[0]/b[1]:.1f} ({b[0]}/{b[1]}) AU {100*b[2]/b[3]:.1f} | rebuild: US {100*r[0]/r[1]:.1f} ({r[0]}/{r[1]}) AU {100*r[2]/r[3]:.1f}")
