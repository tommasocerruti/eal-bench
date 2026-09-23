"""Take the 'update rejected' label from the harness write-validation log instead of the judge panel.

An update is rejected when the last recorded write attempt at the failing block is neither accepted nor a no-change,
in which case the manager keeps the previous profile. For rows where the write did land, the label is the judges'
majority among the remaining categories. Prints the new failure-cause table, the mechanism figure rows, and every
prose number derived from them."""
import collections, csv, json

ROWS = list(csv.DictReader(open("results/diagnosis/failures.csv", encoding="utf-8")))
LABELS = ["restatement_applied", "own_action_as_approval", "authoritative_change_misapplied", "update_failed", "other"]
JUDGES = ("deepseek", "glm_5_3", "nemotron")


def rejected(r):
    st = [s for s in r["attempt_statuses"].split(";") if s]
    return bool(st) and st[-1] not in ("accepted", "no_change")


def det_cause(r):
    if rejected(r):
        return "update_failed"
    votes = collections.Counter(r[j] for j in JUDGES if r[j] and r[j] != "update_failed")
    if not votes:
        return "other"
    top, n = votes.most_common(1)[0]
    ties = [c for c, k in votes.items() if k == n]
    return top if len(ties) == 1 else "other"


def setting(r):
    mandate = r["group"] in ("mandate-open", "loop-mandate"); closed = r["group"] in ("loop-both", "loop-mandate", "onepass"); wb = r["loop_block"] == "True"
    if mandate:
        return "With the instruction, cybersecurity" if r["domain"] == "cybersecurity" else "With the instruction, procurement and finance"
    if closed and wb:
        return "Closed loop, the agent's own lines"
    if closed:
        return "Closed loop, shared history blocks"
    return f"Open loop, {r['domain']}"


ORDER = ["Open loop, procurement", "Open loop, finance", "Open loop, cybersecurity", "Closed loop, shared history blocks",
         "Closed loop, the agent's own lines", "With the instruction, procurement and finance", "With the instruction, cybersecurity"]
for name, key in (("JUDGE PANEL", lambda r: r["consensus_cause"] or "other"), ("HARNESS LOG", det_cause)):
    counts = collections.defaultdict(collections.Counter); updates = collections.defaultdict(set)
    for r in ROWS:
        s = setting(r); counts[s][key(r)] += 1
        updates[s].add((r["run_tag"], r["chain_id"], r["arm"] if r["loop_block"] == "True" else "", r["error_block"]))
    print(f"=== {name}")
    tot = collections.Counter(); upd_all = set()
    for s in ORDER:
        c = counts[s]; n = sum(c.values()); tot.update(c); upd_all |= updates[s]
        print(f"   {s:46s} upd={len(updates[s]):4d} fail={n:5d} " + " ".join(f"{c[l]:5d}" for l in LABELS))
    print(f"   {'All':46s} upd={len(upd_all):4d} fail={sum(tot.values()):5d} " + " ".join(f"{tot[l]:5d}" for l in LABELS))
    print(f"   rows summed over settings: {sum(len(u) for u in updates.values())}")

# mechanism figure counts: the same settings, restricted to the seven writers' pooled failures the figure plots
det = {r["probe_id"] + r["record_id"] + r["run_tag"] + r["chain_id"] + r["error_block"]: det_cause(r) for r in ROWS}
mech = []
for s in ORDER:
    c = collections.Counter(det_cause(r) for r in ROWS if setting(r) == s)
    mech.append([s, [c[l] for l in LABELS]])
print("\n=== mechanism rows (deterministic)"); [print("  ", m) for m in mech]

# prose numbers
INCR = ("incremental_typed", "incremental_hybrid"); INCR_M = ("incremental_typed__mandate", "incremental_hybrid__mandate")
def cnt(pred, cause_fn):
    rows = [r for r in ROWS if pred(r)]
    return sum(1 for r in rows if cause_fn(r) == "update_failed"), len(rows)
ins = lambda r: r["group"] == "mandate-open" and r["domain"] == "cybersecurity" and r["condition_id"] in INCR_M
base = lambda r: r["group"] in ("memtable-cyber", "memtable-seeds") and r["domain"] == "cybersecurity" and r["condition_id"] in INCR
for nm, pred in (("C.3 instruction runs", ins), ("C.3 same seeds without", base)):
    j = cnt(pred, lambda r: r["consensus_cause"]); d = cnt(pred, det_cause)
    print(f"{nm}: judge {j[0]}/{j[1]}  ->  harness {d[0]}/{d[1]}")
# unanimity among the rows the panel still decides
land = [r for r in ROWS if not rejected(r)]
unan = sum(1 for r in land if r["deepseek"] and r["deepseek"] == r["glm_5_3"] == r["nemotron"])
print(f"panel-decided rows: {len(land)}, unanimous {unan} = {100*unan/len(land):.0f}%")
allunan = sum(1 for r in ROWS if r["deepseek"] and r["deepseek"] == r["glm_5_3"] == r["nemotron"])
print(f"all rows unanimous: {allunan}/{len(ROWS)} = {100*allunan/len(ROWS):.0f}%")
agree = sum(1 for r in ROWS if (r["consensus_cause"] == "update_failed") == rejected(r))
print(f"panel vs log agreement on the rejected label: {agree}/{len(ROWS)} = {100*agree/len(ROWS):.1f}%")
json.dump(mech, open("scratch/iclr_seven/mechanism_det.json", "w"), indent=1)
