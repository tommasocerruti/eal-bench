"""Item 21: final-state error under two definitions on the same typed-incremental memories.
event_sourcing.py counts an error in any field, including source_turn_ids (citations); writer_ttc.py excludes source_turn_ids."""
import json, glob, os, sys, collections
sys.path.insert(0, ".")
from domains import get_domain
def rows(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")] if os.path.exists(path) else []
def score(run_dir):
    man = json.load(open(run_dir + "/manifest.json", encoding="utf-8"))
    domain = get_domain(man["domain_id"]); cases = {domain.corpus.case_id(c): c for c in domain.corpus.load_cases(man["corpus_version"])}
    mem = {r["memory_id"]: r for r in rows(run_dir + "/memories.jsonl") if r.get("condition_id") == "incremental_typed"}
    states = [r for r in rows(run_dir + "/memory_states.jsonl") if r.get("condition_id") == "incremental_typed"]
    final = {}
    for s in states:
        k = (s.get("writer_run_id") or json.dumps(s.get("writer"), sort_keys=True), s["case_id"])
        if k not in final or int(s["block_index"]) > int(final[k]["block_index"]): final[k] = s
    out = collections.Counter()
    for (w, cid), s in final.items():
        m = mem.get(s.get("current_memory_id"))
        payload = domain.memory.parse_typed(m["payload"]) if m else domain.memory.empty_typed()
        rep = domain.fidelity.compare(cases[cid], payload, through_block_index=int(s["block_index"]))
        out["n"] += 1; out["err_all"] += any(f.errors for f in rep.fields); out["err_nosrc"] += any(f.errors for f in rep.fields if f.field != "source_turn_ids")
        out["src_only"] += (any(f.errors for f in rep.fields) and not any(f.errors for f in rep.fields if f.field != "source_turn_ids"))
    return man["domain_id"], out
tot = collections.defaultdict(collections.Counter)
targets = sys.argv[1:]
if targets == ["--from-events"]:
    targets = []
    for d in sorted(glob.glob("results/*/*__authorization-memory-event-sourcing__event-*")):
        if "superseded" in d or "glm53" in d: continue
        m = json.load(open(d + "/manifest.json", encoding="utf-8"))
        if m.get("status") != "completed": continue
        for b in m.get("source_runs", []):
            b = b.replace(chr(92), "/")
            if b not in targets and os.path.exists(b + "/memory_states.jsonl"): targets.append(b)
    print("baseline runs:", len(targets))
for d in targets:
    dom, c = score(d); tot[dom].update(c); print(os.path.basename(d)[-60:], dict(c), flush=True)
for dom, c in tot.items():
    print(f"TOTAL {dom}: n={c['n']} err_all={c['err_all']} ({100*c['err_all']/c['n']:.1f}%) err_nosrc={c['err_nosrc']} ({100*c['err_nosrc']/c['n']:.1f}%) source-only={c['src_only']}")
