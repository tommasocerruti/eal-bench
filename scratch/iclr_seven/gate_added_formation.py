"""Representation-level effect of the source-authority gate for the added writers (Inkling, DeepSeek V4.1 Flash),
from the frozen memories stored in their gate runs: origin 'writer' is the original typed incremental memory,
origin 'controlled' is the gated memory. Each probe of each case is replayed deterministically against both.
Prints per writer/domain/seed: unauthorized probes, false authority before and after the gate, authorized probes,
valid authority preserved after the gate; and writes scratch/iclr_seven/gate_added.json."""
import collections
import glob
import json
import sys

sys.path.insert(0, ".")
from domains import get_domain  # noqa: E402

SEEDS = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
W = ["inkling", "deepseek_v4_1_flash"]


def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d
          and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    assert ds, pattern
    return ds[-1]


out = {}
for dom, seeds in SEEDS.items():
    domain = get_domain(dom)
    cases = domain.corpus.load_cases("benchmark_v1")
    by_id = {domain.corpus.case_id(c): c for c in cases}
    for w in W:
        for seed in seeds:
            d = latest(f"results/{dom}/*__gate-s{seed}-{dom}-{w}")
            mem = collections.defaultdict(dict)
            for l in open(d + "/memories.jsonl", encoding="utf-8"):
                m = json.loads(l)
                assert m["condition_id"] == "incremental_typed", m["condition_id"]
                assert m["origin"] not in mem[m["case_id"]], (d, m["case_id"], m["origin"])
                mem[m["case_id"]][m["origin"]] = m["payload"]
            c = collections.Counter()
            for case_id, pair in sorted(mem.items()):
                case = by_id[case_id]
                before = domain.memory.parse_typed(pair["writer"])
                after = domain.memory.parse_typed(pair["controlled"])
                for probe in domain.corpus.probes(case):
                    canon = domain.executor.oracle(case, probe.request).authorized
                    rb = domain.memory.authorizes(case, before, probe.request).authorized
                    ra = domain.memory.authorizes(case, after, probe.request).authorized
                    c["probes"] += 1
                    if canon:
                        c["auth"] += 1
                        c["valid_before"] += rb
                        c["valid_after"] += ra
                    else:
                        c["unauth"] += 1
                        c["F_before"] += rb
                        c["F_after"] += ra
            out[f"{w}|{dom}|{seed}"] = dict(c)
            print(f"{w:20s} {dom:14s} {seed}  cases {len(mem):3d}  unauth {c['unauth']:4d}  F {c['F_before']:3d} -> {c['F_after']:3d}"
                  f"   auth {c['auth']:4d}  valid {c['valid_before']:4d} -> {c['valid_after']:4d}")
json.dump(out, open("scratch/iclr_seven/gate_added.json", "w", encoding="utf-8"), indent=1)
tot = collections.Counter()
for k, c in out.items():
    tot.update(c)
print("added writers, all seeds:", dict(tot))
