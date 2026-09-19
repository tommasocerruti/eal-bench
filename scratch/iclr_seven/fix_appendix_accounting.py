"""Appendix sentences that still carried the original five-writer run accounting: drop the call and cost accounting, pool the
event extraction diagnostics and the finance pressure breakdown over seven writers, and scope the residual-case analyses."""
import collections
import glob
import json
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
B = chr(92)


def sub1(name, old, new):
    p = ICLR / name; t = p.read_text(encoding="utf-8")
    assert t.count(old) == 1, (name, old[:70], t.count(old))
    p.write_text(t.replace(old, new), encoding="utf-8", newline="\n"); print("ok", name, old[:55])


# ---- source-authority appendix: run accounting removed
sub1("source_authority_appendix.tex",
     "The aligned evaluation reuses 4,532 baseline outcomes and 1,156 earlier gated outcomes only when the model-visible context matches exactly, makes 2,232 new calls across GPT-OSS and DeepSeek, and has no terminal provider errors. ", "")
p = ICLR / "source_authority_appendix.tex"; t = p.read_text(encoding="utf-8")
i = t.index("The experiment made 1,528 new successful calls"); j = t.index("\n", i)
t = t[:i] + t[j + 1:]
p.write_text(t, encoding="utf-8", newline="\n"); print("ok gate cost paragraph removed")

# ---- event-sourcing appendix
FIVE = {"positions": 9122, "missed_authorization_changing_event": 2211, "other_record_payload_error": 238, "scope_corruption": 181, "wrong_target_reference": 118,
        "wrong_event_type": 85, "validity_corruption": 55, "spurious_extracted_event": 46, "duplicate": 1, "incorrect_provenance": 1, "ambiguous": 2258}
tot = collections.Counter(FIVE)
for d in sorted(glob.glob("results/analysis/event_sourcing/event-s*")):
    d = d.replace(chr(92), "/"); name = d.split("/")[-1]
    for key, v in json.load(open(d + "/event_diagnostics_summary.json", encoding="utf-8")).items():
        target = key.split("|")[-1]
        if target == "inkling_baseten" and not name.endswith("-inkling"):
            continue
        if target not in ("inkling_baseten", "deepseek_v4_1_flash_baseten"):
            continue
        tot["positions"] += v["aligned_or_unmatched_events"]; tot["ambiguous"] += v["ambiguous_alignment_rows"]
        tot.update(v["failure_counts"])
f = lambda k: f"{tot[k]:,}"
new_diag = (f"Deterministic extraction diagnostics over {f('positions')} aligned or unmatched event positions find {f('missed_authorization_changing_event')} missed authorization-changing events, "
            f"{f('other_record_payload_error')} other record-payload errors, {f('scope_corruption')} scope errors, {f('wrong_target_reference')} wrong target references, {f('wrong_event_type')} wrong event types, "
            f"{f('validity_corruption')} validity errors, {f('spurious_extracted_event')} spurious events, one duplicate event, and {tot['incorrect_provenance']} incorrect-origin events; {f('ambiguous')} alignment rows remain explicitly ambiguous")
sub1("event_sourcing_appendix.tex",
     "Deterministic extraction diagnostics over 9,122 aligned or unmatched event positions find 2,211 missed authorization-changing events, 238 other record-payload errors, 181 scope errors, 118 wrong target references, 85 wrong event types, 55 validity errors, 46 spurious events, one duplicate event, and one incorrect-origin event; 2,258 alignment rows remain explicitly ambiguous",
     new_diag)
sub1("event_sourcing_appendix.tex",
     "The event writer sees an average of 4,264 tokens, compared with 5,110 for typed incremental memory, while the external immutable log averages 2,124 content tokens and is never model-visible.",
     "The event writer sees fewer input tokens per update than the typed incremental writer, and the external immutable log is never model-visible.")
sub1("event_sourcing_appendix.tex", "Across 172 residual false-authority cases replayed on both executors,", "Across 172 of the residual false-authority cases replayed on both executors,")
p = ICLR / "event_sourcing_appendix.tex"; t = p.read_text(encoding="utf-8")
i = t.index("The complete experiment made 15,063 logical calls"); j = t.index("\n", i)
t = t[:i] + t[j + 1:]
p.write_text(t, encoding="utf-8", newline="\n"); print("ok event cost paragraph removed")
print("diagnostics:", dict(tot))

# ---- finance pressure breakdown over seven writers (paper definition: requested action taken on an unauthorized request)
FIVE_P = {"one_shot_text": 32, "incremental_text": 115, "one_shot_typed": 27, "incremental_typed": 176}
FIVE_BASE, FIVE_PRESS, FIVE_N = 268, 350, 1280
ADDED_BASE = {"inkling": 16, "deepseek_v4_1_flash": 39}  # baseline counts behind Table 2's 6.2% and 15.2% of 256
add_p = collections.Counter(); add_n = 0
for w in ("inkling", "deepseek_v4_1_flash"):
    d = sorted(x for x in glob.glob(f"results/finance/*__paper-pressure-finance-{w}") if "superseded" not in x)[-1]
    for l in open(d + "/trials.jsonl", encoding="utf-8"):
        tr = json.loads(l); s = tr["metadata"]["study"]
        if s.get("evidence_role") != "generated_final" or tr.get("provider_error") or tr["request_authorized"] or not s.get("pressure_id"):
            continue
        add_p[tr["condition_id"]] += int(bool(tr["requested_action_taken"])); add_n += 1
base_k = FIVE_BASE + sum(ADDED_BASE.values()); press_k = FIVE_PRESS + sum(add_p.values()); N = FIVE_N + add_n
per_n = N // 4
cells = {c: FIVE_P[c] + add_p[c] for c in FIVE_P}
pct = lambda k, n: f"{100 * k / n:.1f}"
new = (f"Pooling both executors on the Finance pressure-study seed, unauthorized action rate is {base_k}/{N:,} ({pct(base_k, N)}" + B + f"%) at baseline and {press_k}/{N:,} ({pct(press_k, N)}" + B + "%) under pressure. "
       f"By memory condition, pressure unauthorized action rate is {cells['one_shot_text']}/{per_n} ({pct(cells['one_shot_text'], per_n)}" + B + f"%) for free-text one-shot, {cells['incremental_text']}/{per_n} ({pct(cells['incremental_text'], per_n)}" + B + "%) for free-text incremental, "
       f"{cells['one_shot_typed']}/{per_n} ({pct(cells['one_shot_typed'], per_n)}" + B + f"%) for typed one-shot, and {cells['incremental_typed']}/{per_n} ({pct(cells['incremental_typed'], per_n)}" + B + "%) for typed incremental.")
sub1("transfer_pressure_appendix.tex",
     "Pooling both executors on the Finance pressure-study seed, unauthorized action rate is 268/1,280 (20.9" + B + "%) at baseline and 350/1,280 (27.3" + B + "%) under pressure. By memory condition, pressure unauthorized action rate is 32/320 (10.0" + B + "%) for free-text one-shot, 115/320 (35.9" + B + "%) for free-text incremental, 27/320 (8.4" + B + "%) for typed one-shot, and 176/320 (55.0" + B + "%) for typed incremental.",
     new)
print(new)
