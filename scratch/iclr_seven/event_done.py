"""All nine event-sourcing runs for the added writers are complete: update the paper's provenance appendix and the repo note."""
from pathlib import Path

ICLR = Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
REPO = Path(r"C:/Users/mikad/Documents/GitHub/eal-bench")
T = Path(r"C:/Users/mikad/.claude/jobs/e03609a8/tmp/seven")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


# ---- paper appendix
p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "Bounded event sourcing lowers DeepSeek V4.1 Flash's unauthorized submission in cybersecurity from 10.4\\% to 3.1\\% with authorized use rising from 87.5\\% to 100.0\\%, and in finance from 35.9\\% to 0.0\\% with authorized use falling from 99.5\\% to 66.7\\%. Inkling reasons inside its completion: 261 of 1{,}391 event-writer calls hit the protocol's 4{,}096-token budget and 627 of 1{,}389 event updates are rejected as invalid, so its event-sourced memory falls behind the history and authorized use drops to 0.0\\% in cybersecurity and 8.3\\% in finance. That is a limit of the budget, not of the mitigation.",
         "Bounded event sourcing lowers unauthorized submission for the two writers in procurement from 21.1\\% to 2.8\\% with authorized use unchanged (94.7\\% to 94.2\\%), and for DeepSeek V4.1 Flash in cybersecurity from 10.4\\% to 3.1\\% with authorized use rising from 87.5\\% to 100.0\\% and in finance from 35.9\\% to 0.0\\% with authorized use falling from 99.5\\% to 66.7\\%. Inkling reasons inside its completion: 262 of 1{,}552 event-writer calls hit the protocol's 4{,}096-token budget and 658 of 1{,}550 event updates are rejected as invalid, so on the longer cybersecurity and finance histories its event-sourced memory falls behind and authorized use drops to 0.0\\% and 8.3\\%. That is a limit of the budget, not of the mitigation.", "provenance paragraph")
p.write_text(s, encoding="utf-8", newline="\n")

# ---- repo note
raw = (T / "gate_event.md").read_bytes()
try:
    ge = raw.decode("utf-8")
except UnicodeDecodeError:
    ge = raw.decode("cp1252")
ge = ge.replace("\u2013", "-").replace("\ufffd", "-")
(REPO / "results/analysis/section_gate_event.md").write_text(ge, encoding="utf-8", newline="\n")
ge = ge.replace("## The paper's provenance mitigations on the added writers", "### Provenance mitigations for the added writers")
ge = ge.replace("### Source-authority gate (18 of 18 executor-only replays complete)", "**Source-authority gate (18 of 18 executor-only replays complete).**")
ge = ge.replace("### Bounded event sourcing (9 of 9 paired runs complete)", "**Bounded event sourcing (9 of 9 paired runs complete).**")
ge = ge.strip() + "\n\nAuthorized use and unauthorized submission use the paper's definitions (the requested action taken on authorized, respectively unauthorized, requests), counted from each replay's own trials per arm. The gate's `original` arm is a fresh replay of the saved memory, so it differs from the paper-route numbers of the same memories by sampling only. Inkling's event arm is limited by the protocol's 4,096-token event-writer budget on the longer cybersecurity and finance histories and is never pooled with Flash.\n\n"
doc = (REPO / "docs/extension_studies.md").read_text(encoding="utf-8")
i = doc.index("### Provenance mitigations for the added writers"); j = doc.index("### Third executor: GLM 5.3")
doc = doc[:i] + ge + doc[j:]
doc = sub1(doc, "bounded event sourcing for the added writers in procurement (one of three seeds complete; cybersecurity and finance are complete), the cybersecurity capacity test for Inkling,",
           "the cybersecurity capacity test for Inkling,", "status open list")
doc = sub1(doc, "Done for the gate (all 18 replays) and for event sourcing in cybersecurity and finance (Section 5, \"Provenance mitigations\"); event sourcing in procurement has one of three seeds.",
           "Done: the gate on all 18 replays and event sourcing on all 9 paired runs (Section 5, \"Provenance mitigations\").", "open item 3")
(REPO / "docs/extension_studies.md").write_text(doc, encoding="utf-8", newline="\n")
print("event_done applied")
