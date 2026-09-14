"""Builds the 'Proposed paper figures and tables' section of docs/extension_studies.md from the analysis outputs in this
branch, and replaces the section between the <!-- proposed-start --> and <!-- proposed-end --> markers (inserting it
before '## The setup in one page' if the markers are absent). Inputs: results/figures/*.csv, results/analysis/*.md|txt,
results/diagnosis/failures.csv, the Section 5 paper-route table in the doc, and the run manifests for the rebuild rows.

    uv run python scratch/proposed_tables.py
"""
import collections
import csv
import glob
import json
import os
import pathlib
import re

DOC = pathlib.Path("docs/extension_studies.md")
W = ["glm_5_2_baseten", "kimi_baseten", "nemotron_3_ultra_baseten", "inkling_baseten", "deepseek_v4_1_flash_baseten"]
ADDED = {"inkling_baseten", "deepseek_v4_1_flash_baseten"}
SEEDS = {"procurement": [20260719, 20260821, 20260822], "cybersecurity": [20260812, 20260821, 20260822], "finance": [20260816, 20260821, 20260822]}
DOM = {"procurement": "Procurement", "cybersecurity": "Cybersecurity", "finance": "Finance", "pooled": "Pooled"}


def latest_completed(pattern):
    found = []
    for d in sorted(glob.glob(pattern)):
        if "superseded" in d:
            continue
        try:
            m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if m.get("status") == "completed":
            found.append(m)
    return found[-1] if found else None


def pct(k, n):
    return f"{100 * k / n:.1f}" if n else "n/a"


# ---- Table 1: typed incremental vs rebuild every 3, same runs (so same seeds), five writers
def table_formation():
    rows = []
    for dom, seeds in SEEDS.items():
        acc = {c: [0, 0, 0, 0] for c in ("incremental_typed", "incremental_typed__rebuild3")}
        used = 0
        for seed in seeds:
            for w in W:
                if dom == "procurement":
                    pat = f"results/procurement/*__{'newwriter-s' if w in ADDED else 'seeds-'}{seed}-{w}"
                elif seed == seeds[0]:
                    pat = f"results/{dom}/*__memtable-{dom}-{w}"
                else:
                    continue  # rebuild was not run at the other seeds in cybersecurity and finance
                m = latest_completed(pat)
                if m is None:
                    continue
                b = m["summary"]["behavior_by_condition"]
                if not all(c in b for c in acc):
                    continue
                used += 1
                for c in acc:
                    acc[c][0] += b[c]["unauthorized_action"]; acc[c][1] += b[c]["unauthorized_n"]
                    acc[c][2] += b[c]["authorized_use"]; acc[c][3] += b[c]["authorized_n"]
        i, r = acc["incremental_typed"], acc["incremental_typed__rebuild3"]
        seeds_used = "3 seeds" if dom == "procurement" else "canonical seed"
        rows.append(f"| {DOM[dom]} ({seeds_used}, {used} writer runs) | {pct(i[2], i[3])} | {pct(i[0], i[1])} | {pct(r[2], r[3])} | {pct(r[0], r[1])} | {i[1]} |")
    return ["| Domain | AU, typed incremental | US, typed incremental | AU, rebuild every 3 | US, rebuild every 3 | unauthorized requests per cell |", "|---|---|---|---|---|---|"] + rows


# ---- Table 2: trigger, from section4_tables.md (first two tables)
def table_trigger():
    text = pathlib.Path("results/analysis/section4_tables.md").read_text(encoding="utf-8")
    tables = re.findall(r"(\|[^\n]*\n\|---[^\n]*\n(?:\|[^\n]*\n)+)", text)
    return [t.strip("\n") for t in tables[:2]]


# ---- Table 3: cause by setting, from failures.csv
def table_causes():
    rows = list(csv.DictReader(open("results/diagnosis/failures.csv", encoding="utf-8")))
    labels = ["restatement_applied", "own_action_as_approval", "authoritative_change_misapplied", "update_failed", "other"]
    nice = {"restatement_applied": "restatement applied", "own_action_as_approval": "own action as approval", "authoritative_change_misapplied": "authoritative change misapplied", "update_failed": "update failed", "other": "other"}

    def setting(r):
        mandate = r["group"] in ("mandate-open", "loop-mandate")
        closed = r["group"] in ("loop-both", "loop-mandate", "onepass")
        writeback = r["loop_block"] == "True"
        if mandate:
            return "With the mandate, cybersecurity" if r["domain"] == "cybersecurity" else "With the mandate, procurement and finance"
        if closed and writeback:
            return "Closed loop, the agent's own write-back lines"
        if closed:
            return "Closed loop, shared history blocks"
        return f"Open loop, {r['domain']}"

    order = ["Open loop, procurement", "Open loop, finance", "Open loop, cybersecurity", "Closed loop, shared history blocks", "Closed loop, the agent's own write-back lines", "With the mandate, procurement and finance", "With the mandate, cybersecurity"]
    counts = collections.defaultdict(collections.Counter)
    for r in rows:
        counts[setting(r)][r["consensus_cause"] or "no majority"] += 1
    out = ["| Setting | failures | " + " | ".join(nice[l] for l in labels) + " |", "|---|---|" + "---|" * len(labels)]
    for s in order:
        c = counts[s]
        out.append(f"| {s} | {sum(c.values())} | " + " | ".join(str(c[l]) for l in labels) + " |")
    tot = collections.Counter()
    for c in counts.values():
        tot.update(c)
    out.append(f"| **All** | **{sum(tot.values())}** | " + " | ".join(f"**{tot[l]}**" for l in labels) + " |")
    return out


# ---- Table 4: closed loop, round 3, from the figure CSV and the five-writer paired analysis
def table_closed_loop():
    pts = {(r["domain"], r["arm"], int(r["round"])): r for r in csv.DictReader(open("results/figures/closed_loop_control.csv", encoding="utf-8"))}
    paired = pathlib.Path("results/analysis/loop_vs_null_five_writers.txt").read_text(encoding="utf-8")
    us = re.search(r"US \(unauthorized executed\).*?round 3.*?diff\s+([+-][\d.]+) pts\s+95% CI \[([^\]]+)\]\s+p=([\d.]+)", paired, re.S)
    au = re.search(r"AU \(authorized executed\).*?round 3.*?diff\s+([+-][\d.]+) pts\s+95% CI \[([^\]]+)\]\s+p=([\d.]+)", paired, re.S)
    out = ["| Domain | chains | AU open loop | AU round 3, own actions | AU round 3, control | US open loop | US round 3, own actions | US round 3, control |", "|---|---|---|---|---|---|---|---|"]
    for dom in SEEDS:
        a0 = pts[(dom, "action", 0)]; a3 = pts[(dom, "action", 3)]; n3 = pts[(dom, "neutral", 3)]
        out.append(f"| {DOM[dom]} | {a3['chains']} | {a0['au']} | {a3['au']} ({a3['au_lo']}–{a3['au_hi']}) | {n3['au']} ({n3['au_lo']}–{n3['au_hi']}) | {a0['us']} | {a3['us']} ({a3['us_lo']}–{a3['us_hi']}) | {n3['us']} ({n3['us_lo']}–{n3['us_hi']}) |")
    out.append("")
    out.append(f"Paired difference at round 3, own actions minus control, all domains and five writers (360 chains): AU {au.group(1)} points, 95% CI [{au.group(2)}], p={au.group(3)}; US {us.group(1)} points, 95% CI [{us.group(2)}], p={us.group(3)}.")
    return out


# ---- Table 5: mitigations by domain, from the frontier CSV
def table_mitigations():
    rows = list(csv.DictReader(open("results/figures/mitigation_frontier.csv", encoding="utf-8")))
    label = {"baseline": "Typed incremental", "gate": "Source-authority gate", "event": "Bounded event sourcing", "ours_baseline": "Typed incremental", "mandate": "One-line mandate", "rebuild": "Rebuild every 3 blocks"}
    pop = {"paper five writers": "paper's five writers, 3 seeds", "baseten five writers": "Baseten five writers, 3 seeds"}
    out = ["| Domain | Condition | Population | US | AU |", "|---|---|---|---|---|"]
    for dom in ["procurement", "cybersecurity", "finance", "pooled"]:
        for population in ("paper five writers", "baseten five writers"):
            for cond in (("baseline", "gate", "event") if population.startswith("paper") else ("ours_baseline", "mandate", "rebuild")):
                r = next((x for x in rows if x["domain"] == dom and x["population"] == population and x["condition"] == cond), None)
                if r is None:
                    continue
                p = pop[population]
                if cond == "rebuild" and dom != "procurement":
                    p = "Baseten five writers, canonical seed" if dom != "pooled" else "Baseten five writers, procurement 3 seeds, others canonical"
                out.append(f"| {DOM[dom]} | {label[cond]} | {p} | {r['us']} | {r['au']} |")
    return out


# ---- Table 6: generality, added-writer rows from the Section 5 paper-route table
def table_generality():
    doc = DOC.read_text(encoding="utf-8")
    sec = doc[doc.index("**Paper writer route.**"):]
    rows = {}
    for line in sec.splitlines():
        if line.startswith("| ") and "incremental, typed" in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            rows[cells[0]] = cells[2:4]
        if line.startswith("**Memory type"):
            break
    def au_us(cell):
        m = re.match(r"AU ([\d.]+)%, US ([\d.]+)%", cell)
        return (m.group(1), m.group(2)) if m else ("n/a", "n/a")
    out = ["| Writer | Procurement AU | Procurement US | Cybersecurity AU | Cybersecurity US | Finance AU | Finance US |", "|---|---|---|---|---|---|---|",
           "| GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Grok 4.3, Qwen Plus | as printed in the paper | | | | | |"]
    for i, name in ((0, "Inkling"), (1, "DeepSeek V4.1 Flash")):
        vals = []
        for dom in ("procurement", "cybersecurity", "finance"):
            vals += au_us(rows[dom][i])
        out.append(f"| {name} | " + " | ".join(vals) + " |")
    return out


def build():
    s = []
    s.append("<!-- proposed-start -->")
    s.append("## Proposed paper figures and tables")
    s.append("")
    s.append("Drafts of what would go into the main text under the structure above, built from the runs in this branch. Every number is regenerated by `scratch/proposed_tables.py`; the figures by the two `analysis/plot_*_figure.py` scripts. Populations are stated in each caption; the paper's five writers include two (Grok 4.3, Qwen Plus) that are not on Baseten and did not run the extension studies, so the extension rows use the five Baseten writers.")
    s.append("")
    s.append("### Figure: the agent's own actions in its memory (closed loop with control)")
    s.append("")
    s.append("![closed loop](../results/figures/closed_loop_control.png)")
    s.append("")
    s.append("*Caption draft.* Three rounds in which the executor's log lines are written back into the history (blue, filled circles) against a control that receives the same number of updates on the same schedule with neutral content (vermillion, hollow squares), forked from the same frozen memory (the open-loop point). Top: authorized use. Bottom: unauthorized submission. Five writers, both executors, canonical seed per domain; 360 chains. Error bars are 95% bootstrap intervals over chains.")
    s.append("")
    s.append("*Reading it.* Authorized use falls in the action arm in procurement and cybersecurity and does not move in finance; the control stays flat in cybersecurity and finance but also loses ground in procurement, so part of the procurement drop is the cost of any repeated update. Unauthorized submission is flat in both arms in every domain at this scale. The top panels start at 30%, as the paper's compute figure does; the bottom panels start at 0.")
    s.append("")
    s += table_closed_loop()
    s.append("")
    s.append("### Figure: mitigations on one frontier")
    s.append("")
    s.append("![frontier by domain](../results/figures/mitigation_frontier_domains.png)")
    s.append("")
    s.append("![frontier pooled](../results/figures/mitigation_frontier.png)")
    s.append("")
    s.append("*Caption draft.* Unauthorized submission against authorized use, typed incremental memory. Filled markers: the paper's population (five writers, three seeds per domain): baseline (circle), source-authority gate and bounded event sourcing (squares), from the paper's appendix tables. Hollow markers: the five Baseten writers, three seeds per domain: baseline (circle), the one-line mandate (diamond), and rebuild-from-history every three blocks (diamond; three seeds in procurement, canonical seed in cybersecurity and finance). Dashed lines join each mitigation to its own baseline.")
    s.append("")
    s.append("*Reading it.* The domain panels carry the result: in procurement and finance the mandate and rebuild move left with no loss of authorized use, where the gate and event sourcing move left and far down; in cybersecurity the mandate moves right and down while the gate does nothing and rebuild moves left and up. The pooled panel hides this: the mandate's cybersecurity harm nets against its gains elsewhere. If one panel has to go to the appendix, it should be the pooled one. The two baselines differ (19.9 against 25.3 pooled) because the populations differ; nothing is compared across the two families without saying so.")
    s.append("")
    s += table_mitigations()
    s.append("")
    s.append("### Table: formation and propagation, with rebuild as the one design change that helps")
    s.append("")
    s.append("Adds one row pair to the paper's condition table. Same runs for both conditions, so seeds match within a row. Five Baseten writers, both executors.")
    s.append("")
    s += table_formation()
    s.append("")
    s.append("### Table: the trigger (generated corpus)")
    s.append("")
    s.append("Three writers (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra), GPT-OSS as executor, 108 matched groups; 324 unauthorized requests per row.")
    s.append("")
    s += table_trigger()
    s.append("")
    s.append("### Table: the cause, by setting (three LLM judges, majority label)")
    s.append("")
    s.append("Every failure in every run of this note. Rows group failures by where they occur; the mandate rows include open- and closed-loop runs with the line. Labels are the judges' and have not been checked by a human.")
    s.append("")
    s += table_causes()
    s.append("")
    s.append("### Table: generality (the paper's writer table with two added rows)")
    s.append("")
    s.append("Incremental typed memory on the paper's writer route, three seeds per domain, both executors. The paper's five rows stay as printed (with their pressure columns); the two added rows come from Section 5 of this note.")
    s.append("")
    s += table_generality()
    s.append("<!-- proposed-end -->")
    return "\n".join(s) + "\n"


def main():
    section = build()
    doc = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")
    if "<!-- proposed-start -->" in doc:
        i = doc.index("<!-- proposed-start -->"); j = doc.index("<!-- proposed-end -->") + len("<!-- proposed-end -->\n")
        doc = doc[:i] + section + doc[j:]
    else:
        k = doc.index("## The setup in one page")
        doc = doc[:k] + section + "\n" + doc[k:]
    DOC.write_text(doc, encoding="utf-8", newline="\n")
    pathlib.Path("results/analysis/proposed_paper_tables.md").write_text(section, encoding="utf-8", newline="\n")
    print(section)


if __name__ == "__main__":
    main()
