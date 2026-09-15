"""results/diagnosis/failures.csv: one row per judged failure across every group in results/diagnosis/v2, with each judge's label."""
import csv, glob, json, os
JUDGES = [("deepseek", "deepseek_baseten"), ("glm_5_3", "glm_5_3_baseten"), ("nemotron", "nemotron_3_ultra_baseten")]
cols = ["group", "run_tag", "domain", "writer", "condition_id", "arm", "case_id", "chain_id", "probe_id", "record_id", "request_kind", "failure", "error_block", "loop_block", "consensus_cause", "agreement", "deepseek", "glm_5_3", "nemotron", "attempt_statuses"]
rows = []
for f in sorted(glob.glob("results/diagnosis/v2/*/*.jsonl")):
    group = os.path.basename(os.path.dirname(f))
    for line in open(f, encoding="utf-8"):
        if not line.strip(): continue
        r = json.loads(line)
        run = r.get("run") or ""
        rows.append({"group": group, "run_tag": run.split("__")[-1] if run else os.path.basename(f)[:-6], "domain": r.get("domain", ""), "writer": r.get("writer", ""), "condition_id": r.get("condition_id", ""), "arm": r.get("arm") or "", "case_id": r.get("case_id", ""), "chain_id": r.get("chain_id", ""), "probe_id": r.get("probe_id") or "", "record_id": r.get("record_id") or "", "request_kind": r.get("request_kind") or "", "failure": r.get("failure", ""), "error_block": r.get("error_block", ""), "loop_block": r.get("loop_block", ""), "consensus_cause": r.get("consensus_cause", ""), "agreement": r.get("agreement", ""), **{short: (r.get("judges", {}).get(t) or {}).get("cause", "") for short, t in JUDGES}, "attempt_statuses": ";".join(r.get("attempt_statuses") or [])})
with open("results/diagnosis/failures.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
print(len(rows), "rows")
