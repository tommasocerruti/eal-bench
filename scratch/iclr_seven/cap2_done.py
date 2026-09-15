"""Inkling runs abandoned; cybersecurity capacity test into the note and one sentence into the paper's appendix."""
from pathlib import Path

ICLR = Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")
REPO = Path(r"C:/Users/mikad/Documents/GitHub/eal-bench")
T = Path(r"C:/Users/mikad/.claude/jobs/e03609a8/tmp/seven")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:160]}"
    return text.replace(old, new)


# ---- note
cap = (T / "cap2.md").read_text(encoding="utf-8").replace("\u2013", "-")
cap = cap.replace("## Cybersecurity mandate with the oversize write failure removed", "### Cybersecurity at double capacity")
cap = cap.replace("Missing arms: 2x:with:inkling_baseten", "Inkling completed the 2x arm without the instruction only; its 2x arm with the instruction and its rebuild-every-3 runs at seeds 20260821 and 20260822 were abandoned after six attempts each hit the 3,600-second route limit or lost updates to provider timeouts, so Inkling is left out of this table.")
(REPO / "results/analysis/section_cap2.md").write_text(cap, encoding="utf-8", newline="\n")
doc = (REPO / "docs/extension_studies.md").read_text(encoding="utf-8")
doc = sub1(doc, "## 8. Bugs found", cap.strip() + "\n\n## 8. Bugs found", "cap2 insert")
doc = sub1(doc, "Runs still open at the time of this status and not in the tables below: the cybersecurity capacity test for Inkling, rebuild every three blocks for Inkling at the two other cybersecurity seeds, and the closed loop for Grok 4.3 and Qwen Plus (one of twelve runs complete; the rest paused on OpenRouter credits).",
           "Not run: Inkling's cybersecurity capacity test with the instruction and its rebuild every three blocks at seeds 20260821 and 20260822 (abandoned after repeated attempts hit the 3,600-second route limit or lost updates to provider timeouts; stated as not run wherever they would appear), and the closed loop for Grok 4.3 and Qwen Plus (one of twelve runs complete; the rest paused on OpenRouter credits).", "status open list")
doc = sub1(doc, "rebuild-every-3 is at three seeds in procurement and finance and, in cybersecurity, at three seeds for four writers and the canonical seed for Inkling (two runs open).",
           "rebuild-every-3 is at three seeds in procurement and finance and, in cybersecurity, at three seeds for four writers and the canonical seed for Inkling; Inkling's two other cybersecurity seeds were abandoned (route limit and provider timeouts).", "open item 2")
(REPO / "docs/extension_studies.md").write_text(doc, encoding="utf-8", newline="\n")

# ---- paper appendix: one sentence on capacity in cybersecurity
p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
s = sub1(s, "in cybersecurity none is, and in 376 of 403 both attempts to write the duty officer's change set are rejected as invalid output, against 212 of 216 failures without the instruction.}",
         "in cybersecurity none is, and in 376 of 403 both attempts to write the duty officer's change set are rejected as invalid output, against 212 of 216 failures without the instruction. Doubling the memory capacity in cybersecurity removes most of that failure (unauthorized submission 12.5\\% to 1.6\\% at the canonical seed for GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, and DeepSeek V4.1 Flash), and the instruction still raises it, to 8.2\\%.}", "capacity sentence")
p.write_text(s, encoding="utf-8", newline="\n")
print("cap2_done applied")
