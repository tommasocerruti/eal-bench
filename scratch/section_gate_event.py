"""The paper's two provenance mitigations on the added writers (Inkling, DeepSeek V4.1 Flash): the source-authority gate
(executor-only replay of each saved paper-route run, tags gate-s<seed>-<domain>-<writer>) and bounded event sourcing (one
run per domain and seed with both writers, tags event-s<seed>-<domain>, analyzed against the saved incremental typed
baselines). Both executors. Writes results/analysis/section_gate_event.md and, for event sourcing, one analysis directory per
run under results/analysis/event_sourcing/. Run from the eal-bench root:
  PYTHONIOENCODING=utf-8 PYTHONPATH=. uv run python scratch/section_gate_event.py"""
import collections
import glob
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, ".")
from analysis.source_authority_results import summarize_run  # noqa: E402

DOMAINS = ["procurement", "cybersecurity", "finance"]
WRITERS = {"inkling": "Inkling", "deepseek_v4_1_flash": "DeepSeek V4.1 Flash"}
WTARGET = {"inkling_baseten": "Inkling", "deepseek_v4_1_flash_baseten": "DeepSeek V4.1 Flash"}
EXEC = {"gptoss_baseten": "GPT-OSS-120B", "deepseek_baseten": "DeepSeek V4 Pro"}


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def pct(k, n):
    if not n:
        return "n/a"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% ({100 * lo:.1f}–{100 * hi:.1f})"


def completed(pattern):
    out = []
    for d in sorted(glob.glob(pattern)):
        if "superseded" in d:
            continue
        try:
            m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if m.get("status") == "completed":
            out.append((d, m))
    return out


class Acc(dict):
    def __init__(self):
        super().__init__(us_k=0, us_n=0, au_k=0, au_n=0)

    def add(self, us_k, us_n, au_k, au_n):
        self["us_k"] += us_k; self["us_n"] += us_n; self["au_k"] += au_k; self["au_n"] += au_n


out = ["## The paper's provenance mitigations on the added writers", ""]

# ---------------------------------------------------------------- gate
gate = collections.defaultdict(lambda: {"orig": Acc(), "gated": Acc(), "records_in": 0, "records_kept": 0, "memories_changed": 0, "memories": 0, "runs": 0})
gate_runs = 0
for dom in DOMAINS:
    for d, m in completed(f"results/{dom}/*__gate-s*-{dom}-*"):
        tag = d.split("__")[-1]
        mm = re.match(r"gate-s(\d+)-(\w+?)-(inkling|deepseek_v4_1_flash)$", tag)
        if not mm:
            continue
        seed, _, w = mm.groups()
        s = summarize_run(Path(d))
        s = s["runs"][0] if "runs" in s else s
        gate_runs += 1
        for key in ((dom, "all"), (dom, w), ("pooled", "all")):
            g = gate[key]
            g["runs"] += 1
            for f in s["formation"]:
                g["records_in"] += f["input_records"]; g["records_kept"] += f["retained_records"]; g["memories_changed"] += f["changed_memories"]; g["memories"] += f["memories"]
            for st in s["strata"]:
                for arm, acc in (("ORIGINAL", g["orig"]), ("GATED", g["gated"])):
                    b = st[arm]
                    acc.add(b["unauthorized_actions"], b["unauthorized_denominator"], b["authorized_successes"], b["authorized_denominator"])

out += [f"### Source-authority gate ({gate_runs} of 18 executor-only replays complete)", "",
        "The gate keeps a record only if every source it cites is a message from a principal allowed to grant authorization; it does not check that the source supports the record's scope or dates. "
        "Applied to the added writers' saved paper-route memories (typed incremental, three seeds per domain), then both executors answer the same requests from the original and the gated memory. No writer calls.", "",
        "| Domain | Writer | runs | memories changed by the gate | records kept / in | US original | US gated | AU original | AU gated | n per arm |", "|---|---|---|---|---|---|---|---|---|---|"]
for dom in DOMAINS + ["pooled"]:
    for w in (["all"] if dom == "pooled" else ["all", "inkling", "deepseek_v4_1_flash"]):
        g = gate.get((dom, w))
        if not g:
            continue
        o, gd = g["orig"], g["gated"]
        out.append(f"| {dom} | {'both' if w == 'all' else WRITERS[w]} | {g['runs']} | {g['memories_changed']} / {g['memories']} | {g['records_kept']} / {g['records_in']} | {pct(o['us_k'], o['us_n'])} | {pct(gd['us_k'], gd['us_n'])} | {pct(o['au_k'], o['au_n'])} | {pct(gd['au_k'], gd['au_n'])} | {o['us_n']} |")
out.append("")

# ---------------------------------------------------------------- event sourcing
ev = collections.defaultdict(lambda: {"typed": Acc(), "event": Acc(), "runs": 0})
ev_attempts = collections.defaultdict(collections.Counter)
ev_calls = collections.defaultdict(lambda: {"n": 0, "capped": 0})
ev_runs = 0
os.makedirs("results/analysis/event_sourcing", exist_ok=True)
for dom in DOMAINS:
    for d, m in completed(f"results/{dom}/*__event-s*-{dom}"):
        tag = d.split("__")[-1]
        seed = re.match(r"event-s(\d+)-", tag).group(1)
        sources = [p for p in glob.glob(f"results/{dom}/*__authorization-memory-writer__paper-writer-s{seed}-{dom}-*") if "superseded" not in p and re.search(r"-(inkling|deepseek_v4_1_flash)$", p)]
        outdir = Path("results/analysis/event_sourcing") / tag
        if not (outdir / "paired_metrics.jsonl").exists():
            cmd = [sys.executable, "-m", "analysis.event_sourcing", "--event-run", d, "--output", str(outdir)]
            for p in sources:
                cmd += ["--baseline-run", p]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                print("event analysis failed for", tag, r.stderr[-400:])
                continue
        ev_runs += 1
        for line in open(outdir / "paired_metrics.jsonl", encoding="utf-8"):
            r = json.loads(line)
            if r["metric"] not in ("unauthorized_submission", "authorized_use"):
                continue
            w = r["factors"]["target_id"]
            for key in ((dom, "all"), (dom, w), ("pooled", "all")):
                e = ev[key]
                if r["metric"] == "unauthorized_submission":
                    e["typed"].add(r["typed_incremental"]["numerator"], r["typed_incremental"]["denominator"], 0, 0)
                    e["event"].add(r["event_sourced"]["numerator"], r["event_sourced"]["denominator"], 0, 0)
                else:
                    e["typed"].add(0, 0, r["typed_incremental"]["numerator"], r["typed_incremental"]["denominator"])
                    e["event"].add(0, 0, r["event_sourced"]["numerator"], r["event_sourced"]["denominator"])
        for key in ((dom, "all"), ("pooled", "all")):
            ev[key]["runs"] += 1
        for line in open(os.path.join(d, "event_attempts.jsonl"), encoding="utf-8"):
            a = json.loads(line)
            ev_attempts[(a["writer"] or {}).get("target_id")][a["status"]] += 1
        for line in open(os.path.join(d, "calls.jsonl"), encoding="utf-8"):
            c = json.loads(line)
            if c.get("target_id") in WTARGET:
                ev_calls[c["target_id"]]["n"] += 1
                ev_calls[c["target_id"]]["capped"] += ((c.get("usage") or {}).get("completion_tokens") or 0) >= 4096

out += [f"### Bounded event sourcing ({ev_runs} of 9 paired runs complete)", "",
        "At each update the event writer sees the compact previous typed state and the new block and emits event deltas; a deterministic reducer applies accepted deltas, and a failed update keeps the previous state. "
        "The paired baseline is the writer's own saved incremental typed memory from the same seed; both arms are answered by both executors. The event writer runs at the paper's protocol budget of 4,096 completion tokens.", "",
        "| Domain | Writer | US typed incremental | US event-sourced | AU typed incremental | AU event-sourced | n per arm |", "|---|---|---|---|---|---|---|"]
for dom in DOMAINS + ["pooled"]:
    for w in (["all"] if dom == "pooled" else ["all", "inkling_baseten", "deepseek_v4_1_flash_baseten"]):
        e = ev.get((dom, w))
        if not e or not e["typed"]["us_n"]:
            continue
        t, v = e["typed"], e["event"]
        out.append(f"| {dom} | {'both' if w == 'all' else WTARGET[w]} | {pct(t['us_k'], t['us_n'])} | {pct(v['us_k'], v['us_n'])} | {pct(t['au_k'], t['au_n'])} | {pct(v['au_k'], v['au_n'])} | {t['us_n']} |")
out += ["", "Event-writer updates by outcome, and event-writer calls that used the full 4,096-token completion budget (a reasoning-in-completion writer is cut off there):", "",
        "| Writer | accepted | structurally invalid | other | calls at the 4,096 cap |", "|---|---|---|---|---|"]
for w, cnt in ev_attempts.items():
    acc = cnt.get("accepted", 0); inv = cnt.get("structural_invalid", 0); other = sum(cnt.values()) - acc - inv
    c = ev_calls.get(w, {"n": 0, "capped": 0})
    out.append(f"| {WTARGET.get(w, w)} | {acc} | {inv} | {other} | {c['capped']} / {c['n']} |")
out.append("")
text = "\n".join(out) + "\n"
open("results/analysis/section_gate_event.md", "w", encoding="utf-8", newline="\n").write(text)
print(text)
