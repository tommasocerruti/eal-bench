import csv, json, glob, collections, sys
sys.stdout.reconfigure(encoding="utf-8")
rows = list(csv.DictReader(open("results/diagnosis/failures.csv", encoding="utf-8")))
g = collections.defaultdict(lambda: collections.Counter())
upd = collections.defaultdict(set)
for r in rows:
    key = (r["group"], r["domain"])
    g[key]["failures"] += 1
    upd[key].add((r["run_tag"], r["chain_id"], r["error_block"], r["arm"] if r["loop_block"] == "True" else ""))
print("group, domain: failures, distinct (run,chain,block[,arm]) updates")
for key in sorted(g):
    print(f"  {key[0]:28s} {key[1]:14s} {g[key]['failures']:5d} {len(upd[key]):5d}")
allu = set()
for k, v in upd.items(): allu |= v
print("distinct updates overall (approx key):", len(allu), "rows", len(rows))
# refusal per domain in the closed-loop action arm
print("\n== closed-loop decisions by domain (three-round runs)")
tags = collections.Counter(); dec = collections.defaultdict(collections.Counter)
for d in glob.glob("results/*/*closed_loop__rounds3*"):
    if "superseded" in d or "mandate" in d: continue
    m = json.load(open(d + "/manifest.json", encoding="utf-8"))
    if m.get("status") != "completed": continue
    dom = m["domain_id"]; tag = d.split("__")[-1]
    for line in open(d + "/trials.jsonl", encoding="utf-8"):
        t = json.loads(line); st = t["metadata"]["study"]
        arm = st.get("arm") or (("action" if st.get("loop_writer") == "same" else "control") if st.get("loop") == "closed" else "open")
        tags[(tag.split("-")[0], arm)] += 1
        if arm == "action": dec[dom][t["decision"]] += 1
print(sorted(tags.items()))
for dom, c in dec.items():
    n = sum(c.values()); ref = c["escalate"] + c["decline"]
    print(f"  {dom:14s} positions {n} escalate {c['escalate']} decline {c['decline']} refusal {100*ref/n:.1f}% executed {100*c['execute_requested']/n:.1f}% other {100*c['execute_other']/n:.1f}%")
