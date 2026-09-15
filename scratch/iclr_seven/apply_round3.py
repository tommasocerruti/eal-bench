"""Round 3: the eight round-two edits, applied as exact single-match replacements to the current files."""
import pathlib

ICLR = pathlib.Path(r"C:/Users/mikad/Documents/GitHub/eal-bench-iclr")


def sub1(text, old, new, label):
    n = text.count(old)
    assert n == 1, f"{label}: expected 1 match, found {n}\n{old[:200]}"
    return text.replace(old, new)


p = ICLR / "main.tex"; s = p.read_text(encoding="utf-8")
# 1
s = sub1(s, "No unauthorized submission occurs on a request the memory does not authorize, so formation is an upper bound on submission, and the gap is requests the executor escalated or declined despite the memory}.",
         "For Inkling and DeepSeek V4.1 Flash no unauthorized submission occurs on a request the memory does not authorize (0 of 1,106 such trials), which is why the pooled formation rate now exceeds the pooled submission rate where the five original writers' rates were within a point of each other}.", "item 1")
# 2
s = sub1(s, "In cybersecurity 270 of 303 are instead a rejected update at the block carrying the duty officer's signed replacement",
         "In cybersecurity 270 of 303 are instead a rejected update, nearly all at the block carrying the duty officer's signed replacement", "item 2")
# 3
s = sub1(s, "and neither says which message the writer misread. Which error a deployment faces decides whether a given defense helps, costs utility, or backfires.}",
         "and neither says which message the writer misread. We therefore also ask what the writer reacts to, and the answer, which differs by domain, decides whether a given defense helps, costs utility, or backfires.}", "item 3")
# 4
s = sub1(s, "deterministic typed-state fidelity an oracle selection ceiling, and GPT-OSS-120B remains the fixed executor. We separately test",
         "deterministic typed-state fidelity an oracle selection ceiling, and GPT-OSS-120B remains the fixed executor\\added{ (Appendix~\\ref{app:writer-ttc-details})}. We separately test", "item 4a")
s = sub1(s, "produces better candidates but leaves a selection bottleneck. Together, these results",
         "produces better candidates but leaves a selection bottleneck\\added{ (Appendix~\\ref{app:writer-ttc-details})}. Together, these results", "item 4b")
# 5
s = sub1(s, "(Appendix~\\ref{app:rebuild}; GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash, three seeds, both executors). A hybrid schema",
         "(Appendix~\\ref{app:rebuild}; GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash, both executors, three seeds except Inkling's cybersecurity rebuild). A hybrid schema", "item 5a")
s = sub1(s, "cuts unauthorized submission from 25.4\\% to 6.0\\%, from 10.0\\% to 6.0\\%, and from 31.7\\% to 0.0\\% with no loss of authorized use.",
         "cuts unauthorized submission from 25.4\\% to 6.0\\%, from 10.0\\% to 6.0\\% over the 13 writer-seed runs with a rebuild counterpart, and from 31.7\\% to 0.0\\%, with no loss of authorized use.", "item 5b")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "extension_results_appendix.tex"; s = p.read_text(encoding="utf-8")
# 6
s = sub1(s, "and cybersecurity is where the executor escalates most often (53\\% of action-arm positions, against 40\\% over all domains; the executor executes as submitted at 48\\% of positions, escalates at 40\\%, declines at 10\\%, and executes an alternative at 2\\%).",
         "and cybersecurity is where the executor refuses most often: over all rounds of the action arm it escalates or declines at 57\\% of cybersecurity positions against 44\\% in procurement and 32\\% in finance, and executes as submitted at 39\\%, 52\\%, and 68\\% (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, Inkling, DeepSeek V4.1 Flash).", "item 6")
# 7
s = sub1(s, "so with seven writers formation is an upper bound on submission rather than equal to it; the gap is widest",
         "so for these two writers formation bounds submission from above, and the seven-writer $P(F)$ in Table~\\ref{tab:formation-vs-submission} exceeds unauthorized submission in every domain where the five original writers' rates were within a point of each other; the gap is widest", "item 7")
# 8
n = s.count("\\resizebox{\\linewidth}{!}{")
assert n == 4, n
s = s.replace("\\resizebox{\\linewidth}{!}{", "\\resizebox{\\ifdim\\width>\\linewidth\\linewidth\\else\\width\\fi}{!}{")
p.write_text(s, encoding="utf-8", newline="\n")

p = ICLR / "extension_mitigations_appendix.tex"; s = p.read_text(encoding="utf-8")
# 5 appendix table
s = sub1(s, "both executors, three seeds per domain except Inkling's cybersecurity rebuild (canonical seed). The rebuild column's matched typed-incremental baseline, from the same writers, seeds, and executors, is 25.4 / 90.6 in procurement, 10.0 / 88.9 in cybersecurity, and 31.7 / 99.9 in finance.}}",
         "both executors, three seeds per domain. $^\\dagger$13 writer-seed runs (Inkling at the canonical seed); their matched typed-incremental baseline is 10.0 / 88.9, against the 15-run 10.4 / 88.3 in the first column.}}", "item 5 caption")
s = sub1(s, "    Cybersecurity & 10.4 & 88.3 & 12.7 & 86.5 & 6.0 & 93.0 & 21.8 & 77.9 \\\\",
         "    Cybersecurity & 10.4 & 88.3 & 12.7 & 86.5 & 6.0$^\\dagger$ & 93.0$^\\dagger$ & 21.8 & 77.9 \\\\", "item 5 dagger")
n = s.count("\\resizebox{\\linewidth}{!}{")
assert n == 1, n
s = s.replace("\\resizebox{\\linewidth}{!}{", "\\resizebox{\\ifdim\\width>\\linewidth\\linewidth\\else\\width\\fi}{!}{")
p.write_text(s, encoding="utf-8", newline="\n")
print("round 3 applied")
