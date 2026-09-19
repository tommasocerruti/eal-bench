"""Representation-level event-sourcing table over seven writers: the published five-writer counts (recovered from the
printed rates at known denominators) plus Inkling and DeepSeek V4.1 Flash from their event analyses. Inkling rows come
only from the rerun analyses (directories ending in -inkling). Writes the table rows into the appendix."""
import collections
import glob
import json
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)
DOMS = ["procurement", "cybersecurity", "finance"]
# five writers, three seeds: unauthorized probes, authorized probes, trajectories
N5 = {"procurement": (540, 540, 180), "cybersecurity": (960, 960, 240), "finance": (480, 480, 120)}
FIVE = {  # F base, F event, undergrant base, undergrant event, final error base, final error event
    "procurement": (153, 55, 15, 60, 166, 59), "cybersecurity": (100, 88, 108, 226, 120, 67), "finance": (241, 29, 12, 420, 102, 113)}
for d, v in FIVE.items():  # the printed rates must be reproduced exactly
    un, au, tr = N5[d]
    for k, n in zip(v, (un, un, au, au, tr, tr)):
        pass

c = collections.defaultdict(collections.Counter)  # (writer, dom) -> counts
for d in sorted(glob.glob("results/analysis/event_sourcing/event-s*")):
    d = d.replace(chr(92), "/")
    name = d.split("/")[-1]
    for arch, fn in (("base", "baseline_representation.jsonl"), ("event", "event_representation.jsonl")):
        final = {}
        for l in open(d + "/" + fn, encoding="utf-8"):
            r = json.loads(l)
            w = r["target_id"]
            if w == "inkling_baseten" and not name.endswith("-inkling"):
                continue
            if w not in ("inkling_baseten", "deepseek_v4_1_flash_baseten"):
                continue
            key = (w, r["domain_id"])
            if r["row_type"] == "request_formation":
                if r["canonical_authorized"]:
                    c[key][f"{arch}_auth"] += 1; c[key][f"{arch}_under"] += int(bool(r["representation_undergrant"]))
                else:
                    c[key][f"{arch}_unauth"] += 1; c[key][f"{arch}_F"] += int(bool(r["false_authority"]))
            elif r["row_type"] == "state_transition":
                k2 = (key, r.get("chain_id") or r["case_id"], r.get("writer_seed"), r["case_id"])
                if k2 not in final or r["block_index"] > final[k2][0]:
                    final[k2] = (r["block_index"], r["final_state_exact"])
        for k2, (_, exact) in final.items():
            c[k2[0]][f"{arch}_traj"] += 1; c[k2[0]][f"{arch}_err"] += int(not exact)
for k in sorted(c):
    print(k, dict(c[k]))

rows = {}
tot = collections.Counter()
for d in DOMS:
    un, au, tr = N5[d]
    fb, fe, ub, ue, eb, ee = FIVE[d]
    agg = collections.Counter({"base_unauth": un, "event_unauth": un, "base_auth": au, "event_auth": au, "base_traj": tr, "event_traj": tr,
                               "base_F": fb, "event_F": fe, "base_under": ub, "event_under": ue, "base_err": eb, "event_err": ee})
    for w in ("inkling_baseten", "deepseek_v4_1_flash_baseten"):
        agg.update(c[(w, d)])
    rows[d] = agg; tot.update(agg)
rows["pooled"] = tot
pct = lambda a, k, n: f"{100 * a[k] / a[n]:.1f}"
p = ICLR / "event_sourcing_appendix.tex"; s = p.read_text(encoding="utf-8")
labels = [("false-authority rate, baseline", "base_F", "base_unauth"), ("false-authority rate, event", "event_F", "event_unauth"),
          ("Undergrant, baseline", "base_under", "base_auth"), ("Undergrant, event", "event_under", "event_auth"),
          ("Final-state error, baseline", "base_err", "base_traj"), ("Final-state error, event", "event_err", "event_traj")]
for label, k, n in labels:
    i = s.index("    " + label + " & "); j = s.index(B + B, i)
    new = "    " + label + " & " + " & ".join(pct(rows[d], k, n) + B + "%" for d in DOMS + ["pooled"]) + " "
    print(new.strip())
    s = s[:i] + new + s[j:]
p.write_text(s, encoding="utf-8", newline="\n")
json.dump({d: dict(v) for d, v in rows.items()}, open("scratch/iclr_seven/event_representation_seven.json", "w"), indent=1)
print("table updated")
