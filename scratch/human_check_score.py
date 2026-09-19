"""Compare a person's labels (results/diagnosis/human_check/labels.csv, filled in) with the judges' majority label
(key.csv): agreement, Cohen's kappa, and the disagreements. Run from the eal-bench root:
  uv run python scratch/human_check_score.py [--dir results/diagnosis/human_check]
"""
import argparse
import collections
import csv
from pathlib import Path


def kappa(pairs):
    n = len(pairs)
    labels = sorted({a for a, _ in pairs} | {b for _, b in pairs})
    po = sum(a == b for a, b in pairs) / n
    pa, pb = collections.Counter(a for a, _ in pairs), collections.Counter(b for _, b in pairs)
    pe = sum(pa[l] * pb[l] for l in labels) / (n * n)
    return po, (po - pe) / (1 - pe) if pe < 1 else 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="results/diagnosis/human_check")
    a = ap.parse_args()
    d = Path(a.dir)
    key = {r["item"]: r for r in csv.DictReader(open(d / "key.csv", encoding="utf-8"))}
    human = {r["item"]: r["label"].strip() for r in csv.DictReader(open(d / "labels.csv", encoding="utf-8")) if r["label"].strip()}
    if not human:
        print("labels.csv has no labels yet")
        return 1
    pairs = [(human[i], key[i]["consensus_cause"]) for i in human]
    po, k = kappa(pairs)
    print(f"{len(pairs)} labeled items: agreement with the majority label {po:.1%}, Cohen's kappa {k:.2f}")
    by = collections.defaultdict(lambda: [0, 0])
    for i in human:
        by[key[i]["consensus_cause"]][1] += 1
        by[key[i]["consensus_cause"]][0] += human[i] == key[i]["consensus_cause"]
    for l, (agree, n) in sorted(by.items()):
        print(f"  {l:32s} {agree}/{n}")
    dis = [i for i in human if human[i] != key[i]["consensus_cause"]]
    if dis:
        print("disagreements (item: person / judges, agreement among judges):")
        for i in dis:
            print(f"  {i}: {human[i]} / {key[i]['consensus_cause']} ({key[i]['agreement']} of 3)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
