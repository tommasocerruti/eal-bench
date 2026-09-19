"""Section 6 tables from results/diagnosis/v2/<group>/*.jsonl: consensus cause by setting (open loop / closed loop base
blocks / closed loop write-back blocks, and the born/recited records), per-judge counts, agreement. Prints markdown.
Run from the eal-bench root: PYTHONIOENCODING=utf-8 uv run python scratch/section6_v2.py"""
import collections
import glob
import json
import os

CAUSES = ["restatement_applied", "own_action_as_approval", "authoritative_change_misapplied", "update_failed", "other"]
LABEL = {"restatement_applied": "restatement applied", "own_action_as_approval": "own action as approval",
         "authoritative_change_misapplied": "authoritative change misapplied", "update_failed": "update failed", "other": "other"}
GROUPS = [
    ("open-seeds", "open loop, procurement memory grid (paper's three seeds; all five writers)"),
    ("memtable-cyber", "open loop, cybersecurity memory grid"),
    ("memtable-finance", "open loop, finance memory grid"),
    ("memtable-seeds", "open loop, cybersecurity and finance typed and hybrid incremental at the paper's other two seeds (mandate baselines)"),
    ("open-generated-v2", "open loop, generated corpus (with and without the mandate)"),
    ("mandate-open", "open loop, mandate (all domains, three seeds)"),
    ("paper-route-new-writers", "paper writer route, added writers (all domains)"),
    ("onepass", "closed loop, one pass"),
    ("loop-both", "closed loop, three rounds, action and neutral arms"),
    ("loop-mandate", "closed loop, three rounds, mandate"),
]


def rows_of(group):
    """Rows of a judged group; a file is named by its run tag, and rows of a tag whose live run is newer than the judged
    one (a rerun replaced it) are dropped."""
    out = []
    live = {}
    for d in glob.glob("results/*/2026*__*"):
        if "superseded" in d:
            continue
        b = os.path.basename(d)
        live[b.split("__")[-1]] = b
    for f in glob.glob(f"results/diagnosis/v2/{group}/*.jsonl"):
        tag = os.path.basename(f)[:-6]
        if tag not in live:
            continue
        for l in open(f, encoding="utf-8"):
            r = json.loads(l)
            if r.get("run") and r["run"] != live[tag]:
                continue
            r["run"] = r.get("run") or live[tag]  # early rows did not record their run; the file is named by its tag
            out.append(r)
    return out


def update_key(r):
    """One memory update: a chain at a block (in a write-back block, of one arm). Several requests can be authorized by
    the same update, so distinct updates are fewer than judged rows."""
    return (r["run"], r.get("chain_id"), r.get("arm") if r.get("loop_block") else "", r.get("error_block"))


def table(rows, split_loop):
    lines = []
    def emit(name, rs):
        c = collections.Counter(r.get("consensus_cause") or "no consensus" for r in rs)
        n = len(rs)
        if not n:
            return
        updates = len({update_key(r) for r in rs})
        requests = sum(1 for r in rs if r["failure"] == "false_authorization")
        records = n - requests
        cells = [str(c.get(k, 0)) for k in CAUSES] + [str(c.get("no consensus", 0))]
        lines.append(f"| {name} | {updates} | {requests} | {records} | " + " | ".join(cells) + " |")
    if split_loop:
        emit("history blocks (shared by both arms)", [r for r in rows if r["failure"] == "false_authorization" and not r.get("loop_block")])
        emit("write-back blocks, false permissions", [r for r in rows if r["failure"] == "false_authorization" and r.get("loop_block")])
        emit("records born from the agent's own lines", [r for r in rows if r["failure"] == "record_born_from_action"])
        emit("existing records re-cited to the agent's own lines", [r for r in rows if r["failure"] == "record_recited_from_action"])
    else:
        emit("all", rows)
    return lines


out = []
header = "| Where the failure enters | distinct updates | requests | records | " + " | ".join(LABEL[c] for c in CAUSES) + " | no majority |"
sep = "|---|---|---|---|" + "---|" * (len(CAUSES) + 1)
grand = []
per_judge = collections.defaultdict(collections.Counter)
agree = collections.Counter()
for g, title in GROUPS:
    rows = rows_of(g)
    if not rows:
        continue
    grand += rows
    out.append(f"*{title}* ({len(rows)} failures from {len({update_key(r) for r in rows})} memory updates)\n")
    out.append(header)
    out.append(sep)
    out += table(rows, split_loop=g.startswith("loop") or g == "onepass")
    out.append("")
    for r in rows:
        agree[r.get("agreement")] += 1
        for j, v in (r.get("judges") or {}).items():
            per_judge[j][(v or {}).get("cause") or "none"] += 1
if grand:
    c = collections.Counter(r.get("consensus_cause") or "no consensus" for r in grand)
    ups = collections.defaultdict(set)
    for r in grand:
        ups[update_key(r)].add(r.get("consensus_cause") or "no consensus")
    uc = collections.Counter(next(iter(v)) if len(v) == 1 else "mixed" for v in ups.values())
    n_req = sum(1 for r in grand if r["failure"] == "false_authorization")
    out.append(f"*All groups* ({len(grand)} failures: {n_req} requests and {len(grand) - n_req} records, from {len(ups)} distinct memory updates). By row: " + ", ".join(f"{LABEL.get(k, k)} {v}" for k, v in c.most_common()) + ". By update: " + ", ".join(f"{LABEL.get(k, k)} {v}" for k, v in uc.most_common()) + " (an update is 'mixed' when its rows carry different labels).\n")
    out.append("Judge agreement: " + ", ".join(f"{agree[k]} rows with {k} of 3 judges on the majority label" for k in sorted(agree, key=lambda x: -(x or 0))) + ".\n")
    out.append("| Judge | " + " | ".join(LABEL[c] for c in CAUSES) + " |")
    out.append("|---|" + "---|" * len(CAUSES))
    names = {"deepseek_baseten": "DeepSeek V4 Pro", "glm_5_3_baseten": "GLM 5.3", "nemotron_3_ultra_baseten": "Nemotron 3 Ultra"}
    for j, cnt in per_judge.items():
        out.append(f"| {names.get(j, j)} | " + " | ".join(str(cnt.get(k, 0)) for k in CAUSES) + " |")
print("\n".join(out))
