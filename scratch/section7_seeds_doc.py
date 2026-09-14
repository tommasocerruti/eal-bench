"""Moves Section 7 of docs/extension_studies.md, and every sentence elsewhere that describes the mandate's population, to
the three-seed, five-writer population from results/analysis/section7_seeds.md. Final-state wording only."""
import pathlib
import re

p = pathlib.Path("docs/extension_studies.md")
s = p.read_text(encoding="utf-8").replace("\r\n", "\n")
seeds = pathlib.Path("results/analysis/section7_seeds.md").read_text(encoding="utf-8")


def rep(old: str, new: str) -> None:
    global s
    assert old in s, old[:120]
    s = s.replace(old, new, 1)


tables = re.findall(r"(\|[^\n]*\n\|---[^\n]*\n(?:\|[^\n]*\n)+)", seeds)
pooled, per_seed, per_writer = (t.strip("\n") for t in tables[:3])

# ---- Section 7: what we ran, result table, reading, takeaway
rep("It is prepended to the writer's instructions for every update and compared with the same conditions without it, at the same seeds and executors: the open loop (typed and hybrid incremental, both executors) in all three domains, the three-round closed loop in all three domains, and the `generated_v2` corpus. Remaining failures are judged with the Section 6 method.",
    "It is prepended to the writer's instructions for every update and compared with the same conditions without it, at the same seeds and executors: the open loop (typed and hybrid incremental, both executors, all five writers, the paper's three seeds per domain) in all three domains, the three-round closed loop in all three domains at the canonical seed, and the `generated_v2` corpus. Remaining failures are judged with the Section 6 method.")

i = s.index("**Result, open loop.**")
j = s.index("**Result, closed loop.**")
s = s[:i] + f"""**Result, open loop.** Five writers and both executors pooled, the paper's three seeds per domain (90 runs, 180 writer-by-seed-by-executor-by-memory pairs, no provider-error trials). Baseline is the same condition without the line from the same seeds and writers. False permissions formed counts memories that authorize an unauthorized request. The paired change is the mean over pairs of the mandate rate minus the baseline rate, with a bootstrap 95% interval and a sign-flip permutation p-value.

{pooled}

The same comparison by seed, to show that the direction does not depend on which seed is used:

{per_seed}

And by writer, pooled over seeds, memories, and executors:

{per_writer}

""" + s[j:]

rep("**Reading.** One sentence in the writer's instructions is enough to remove most laundering where the failure is a misread message: procurement halves it in the open loop and cuts it to a quarter in the closed loop, finance goes to zero in both, and records minted from the agent's own actions all but disappear (91 → 4). It does not restore authorized use in the closed loop (procurement round 3: 59% without, 62% with), so the utility loss of Section 3 is not caused by the writer believing the wrong messages. In cybersecurity the line makes things worse, for the paper's writers and for the added ones (Section 5), and the judges say why: cybersecurity's failure was never about authority. The writer knows the duty officer's change set is the authoritative one; it fails to write the replacement, and with the extra instruction it fails more often. A rule about whose word counts cannot fix an update that is never applied.",
    "**Reading.** Where the failure is a misread message, one sentence in the writer's instructions removes most of it and costs nothing in authorized use. Procurement: unauthorized submission falls by 19.5 points under typed memory (25.4% to 5.8%) and 9.6 under hybrid, at every seed and for every writer, and authorized use rises (90.6% to 98.2%), because the writer also stops recording the restated figures that were making it refuse legitimate requests. Finance: 31.7% to 1.7% under typed memory at all three seeds, with no measurable change in authorized use; under hybrid memory the drop is smaller (11.7% to 3.8%). In the closed loop, records minted from the agent's own actions all but disappear (91 to 4), but authorized use at round 3 is unchanged (59% without, 62% with), so the utility loss of Section 3 is not caused by the writer believing the wrong messages. In cybersecurity the line makes things worse at every seed and for four of the five writers (Kimi is unchanged at 1.0%): unauthorized submission rises 11.4 points under typed memory (10.4% to 21.8%) and authorized use falls 10.4 points. The judges say why: cybersecurity's failure was never about authority. The writer knows the duty officer's change set is the authoritative one; it fails to write the replacement, and with the extra instruction it fails more often. A rule about whose word counts cannot fix an update that is never applied.")

# ---- Story section: population sentence, open item, claim row
rep("Populations must be stated on the figure: the paper's mitigations are five writers at three seeds; the mandate is the Baseten writers at the canonical seed (see open items).",
    "Populations must be stated on the figure: the paper's mitigations are its five writers at three seeds; the mandate and rebuild are the five Baseten writers, the mandate at the same three seeds, rebuild at three seeds in procurement and the canonical seed elsewhere.")
rep("2. **Seed alignment for the frontier.** The mandate ran at the canonical seed per domain; the paper's mitigations at three seeds. Running the mandate open loop at the two remaining seeds (typed and hybrid incremental, three domains, the Baseten writers) is about fifteen runs and removes the population caveat from the one comparison the story turns on.",
    "2. **Rebuild at three seeds in cybersecurity and finance.** The mandate and its baseline are at the paper's three seeds in every domain; rebuild-every-3 is at three seeds in procurement only. Two more seeds in the other two domains (ten runs) would put every point on the frontier at the same seed count.")
rep("| The mandate removes laundering where the cause is a misread message and hurts where it is an update failure (S7) | 3 writers × 2 executors, 1 seed per domain; open and closed loop; judged causes | moderate (single seed) for the effect sizes, which are large; the mechanism rests on the judges | as measured, with the judge caveat |",
    "| The mandate removes laundering where the cause is a misread message and hurts where it is an update failure (S7) | open loop: 5 writers × 2 executors × 3 seeds per domain, 180 paired cells, sign-flip p < 0.001 in procurement, finance (typed) and cybersecurity, same direction at every seed; closed loop at the canonical seed; judged causes | strong for the effect sizes; the mechanism rests on the judges | as measured, with the judge caveat |")

p.write_text(s, encoding="utf-8", newline="\n")
print("section 7 moved to three seeds")
