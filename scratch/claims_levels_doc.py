"""Adds an evidence-level column to the claim table of docs/extension_studies.md, following the three-level framework of
Gupta et al., "Anthropomorphic Misalignment Research Needs Stronger Evidence" (arXiv:2606.07612): L1 behavioral (a rate
under a stated setting and evaluator), L2 functional (the behavior reliably produces a downstream effect across
variations), L3 causal-mechanistic (an intervention with controls supports an attribution). Run from the eal-bench root."""
import pathlib

DOC = pathlib.Path("docs/extension_studies.md")
s = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")

LEVELS = {
    "Incremental writing launders; rebuilding removes most of it (S1)": "L2 for laundering (false permissions in memory are acted on by every executor, across writers and domains); L3, narrow, for the writing method (same runs, method varied)",
    "The hybrid schema helps (S1)": "L1 (rates by writer; no intervention isolates the schema)",
    "Rebuild timing matters (S2)": "L1",
    "Action write-back mints records and cuts authorized use (S3)": "L3 for the content of the write-back (matched control: same updates, same schedule, neutral content)",
    "Action write-back raises unauthorized submission (S3)": "L3 design, result not detected",
    "Restatements are the trigger (S4)": "L3, narrow (only the restatements vary within a group; 0 restatements is the control)",
    "Amendments launder more than revoke-and-replace; the gap does not matter (S4)": "L1 (observed across differently drawn histories)",
    "Added writers reproduce the paper (S5)": "L2 (the same downstream effect across writers)",
    "A third executor acts on the same memories the same way (S5, third executor)": "L2 (the same downstream effect across executors, memories held fixed)",
    "Flash's closed loop raises unauthorized submission (S5)": "L3 design, one writer, one seed",
    "Three causes by setting and domain (S6)": "L1 (a labeled description of where and how each failure enters; no intervention)",
    "The mandate lowers unauthorized submission in procurement and finance and raises it in cybersecurity (S7)": "L3 for the effect of the line (paired intervention on the writer's instructions)",
    "Why the mandate reverses in cybersecurity (S7)": "L1 (rejected updates observed in the logs); the reading is a hypothesis awaiting the intervention in the last column",
    "The mandate does not recover the closed-loop utility loss (S7)": "L1",
}

i = s.index("| Claim | Evidence | Strength | How it is stated | What a stronger claim would need |")
j = s.index("**Open checks before the paper.**")
lines = s[i:j].rstrip("\n").split("\n")
out = ["| Claim | Evidence | Strength | Evidence level | How it is stated | What a stronger claim would need |", "|---|---|---|---|---|---|"]
seen = set()
for line in lines[2:]:
    cells = line.split(" | ")
    claim = cells[0].lstrip("| ").strip()
    assert claim in LEVELS, claim
    seen.add(claim)
    cells.insert(3, LEVELS[claim])
    out.append(" | ".join(cells))
assert seen == set(LEVELS), set(LEVELS) - seen
s = s[:i] + "\n".join(out) + "\n\n" + s[j:]

old = "**How far each claim is supported.** Strength is judged by design (paired or controlled), size, and seeds; \"single seed\" means the canonical seed of each domain. The last column says what evidence a stronger statement would need."
new = ("**How far each claim is supported.** Strength is judged by design (paired or controlled), size, and seeds; \"single seed\" means the canonical seed of each domain. "
       "The evidence level follows the three-level framework of Gupta et al. (arXiv:2606.07612): L1, behavioral, a rate under a stated setting and evaluator; L2, functional, the behavior reliably produces a downstream effect across variations; L3, causal-mechanistic, an intervention with controls supports an attribution. "
       "Levels are relative to the claim, not a ranking of the studies: the paper's central claim (a false permission in memory is acted on) is L2, most mechanism statements here are L1 descriptions with an L3 test named in the last column, and the two matched interventions (write-back content, restatements) are L3 for their narrow claims.")
assert s.count(old) == 1
s = s.replace(old, new)
DOC.write_text(s, encoding="utf-8", newline="\n")
print("levels added")
