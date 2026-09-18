"""Primary-seed representation-level gate effect for the added writers' one-shot typed memories (the incremental typed
half comes from gate_added.json). Applies the same cited-source gate offline and replays every probe deterministically.
Prints the seven-writer rows of the primary-seed representation table and writes scratch/iclr_seven/gate_added_table.json."""
import collections
import glob
import json
import sys

sys.path.insert(0, ".")
from domains import get_domain  # noqa: E402
from experiments.mitigations.source_authority.gate import apply_cited_source_authority_gate  # noqa: E402

PRIMARY = {"procurement": 20260719, "cybersecurity": 20260812, "finance": 20260816}
W = ["inkling", "deepseek_v4_1_flash"]
# published five-writer rows: F before, F after, unauthorized probes, valid preserved after, authorized probes
FIVE = {"procurement": (58, 2, 360, 177, 360), "cybersecurity": (28, 28, 640, 606, 640), "finance": (80, 0, 320, 204, 320)}
inc = json.load(open("scratch/iclr_seven/gate_added.json", encoding="utf-8"))


def latest(pattern):
    ds = [d for d in sorted(glob.glob(pattern)) if "superseded" not in d and "glm53" not in d
          and json.load(open(d + "/manifest.json", encoding="utf-8")).get("status") == "completed"]
    assert ds, pattern
    return ds[-1]


table = {}
for dom, seed in PRIMARY.items():
    domain = get_domain(dom)
    cases = domain.corpus.load_cases("benchmark_v1")
    by_id = {domain.corpus.case_id(c): c for c in cases}
    fb, fa, un, va, au = FIVE[dom]
    tot = collections.Counter({"F_before": fb, "F_after": fa, "unauth": un, "valid_after": va, "auth": au})
    for w in W:
        d = latest(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-{w}")
        rows = [json.loads(l) for l in open(d + "/evidence.jsonl", encoding="utf-8")]
        one = [r for r in rows if r["condition_id"] == "one_shot_typed"]
        assert len(one) == len(by_id), (d, len(one), len(by_id))
        c = collections.Counter()
        for r in one:
            case = by_id[r["case_id"]]
            before = domain.memory.parse_typed(r["payload"])
            last_block = max(int(b.block_index) for b in domain.corpus.blocks(case))
            gate = apply_cited_source_authority_gate(domain, case, before, through_block_index=last_block)
            after = domain.memory.parse_typed(gate.gated_state)
            for probe in domain.corpus.probes(case):
                canon = domain.executor.oracle(case, probe.request).authorized
                rb = domain.memory.authorizes(case, before, probe.request).authorized
                ra = domain.memory.authorizes(case, after, probe.request).authorized
                if canon:
                    c["auth"] += 1; c["valid_before"] += rb; c["valid_after"] += ra
                else:
                    c["unauth"] += 1; c["F_before"] += rb; c["F_after"] += ra
        i = inc[f"{w}|{dom}|{seed}"]
        print(f"{w:20s} {dom:14s} one-shot: unauth {c['unauth']:3d} F {c['F_before']:2d}->{c['F_after']:2d} valid {c['valid_before']:3d}->{c['valid_after']:3d}"
              f" | incremental: unauth {i['unauth']:3d} F {i['F_before']:2d}->{i['F_after']:2d} valid {i['valid_before']:3d}->{i['valid_after']:3d}")
        for k in ("F_before", "F_after", "unauth", "valid_after", "auth"):
            tot[k] += c[k] + i[k]
    table[dom] = dict(tot)
    print(f"ROW {dom}: {tot['F_before']}/{tot['unauth']} ({100*tot['F_before']/tot['unauth']:.1f}%) & {tot['F_after']}/{tot['unauth']} ({100*tot['F_after']/tot['unauth']:.1f}%)"
          f" & {100*(1-tot['F_after']/tot['F_before']) if tot['F_before'] else 0:.1f}% & {tot['valid_after']}/{tot['auth']} ({100*tot['valid_after']/tot['auth']:.1f}%)")
allc = collections.Counter()
for v in table.values():
    allc.update(v)
table["all"] = dict(allc)
print(f"ROW all: {allc['F_before']}/{allc['unauth']} ({100*allc['F_before']/allc['unauth']:.1f}%) & {allc['F_after']}/{allc['unauth']} ({100*allc['F_after']/allc['unauth']:.1f}%)"
      f" & {100*(1-allc['F_after']/allc['F_before']):.1f}% & {allc['valid_after']}/{allc['auth']} ({100*allc['valid_after']/allc['auth']:.1f}%)")
json.dump(table, open("scratch/iclr_seven/gate_added_table.json", "w", encoding="utf-8"), indent=1)
