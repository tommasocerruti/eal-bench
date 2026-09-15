"""Replaces the proposed-results outline in docs/extension_studies.md with an integration plan keyed to the Overleaf
manuscript's sections (main.tex of the paper repository), and records in the status block which runs are still open.
Final-state wording. Run from the eal-bench root."""
import pathlib

DOC = pathlib.Path("docs/extension_studies.md")
s = DOC.read_text(encoding="utf-8").replace("\r\n", "\n")

i = s.index("### Proposed results section")
j = s.index("### Open items before this can be written into the paper")
plan = r"""### Overleaf integration plan

Keyed to the manuscript as it stands (`main.tex`; section numbers are the current ones). The main text is about nine pages before the references; the plan holds that length by moving two current subsections to the appendix and adding three short ones. Every number comes from a script in this branch, listed at the end, so the Overleaf edit is a transcription, not a recomputation.

**Thesis, stated once in the introduction and once in the conclusion.** Endogenous authorization laundering has an identifiable trigger and an identifiable point of entry: an incremental writer treats a later message that repeats a superseded permission as new authority, and in a deployment that logs its actions the agent's own log lines are such messages. The point of entry differs by domain, and a mitigation works where it matches it.

| Manuscript location | Change | Source in this note |
|---|---|---|
| Abstract | "five LLMs as memory writers" becomes seven. Add one sentence: a single instruction about who may grant authority removes most laundering where the failure is a misread message and makes it worse where the writer fails to write a legitimate change; the agent's own logged actions become cited evidence and cut authorized use round over round. Keep the provenance-mitigation sentence. | S7 pooled table; S3 |
| §1 Introduction, contributions | Add a bullet: we locate the trigger (restatements of a superseded permission) and the writer's error (three labeled causes that separate by domain), and show the agent's own actions feed the channel. Reword the mitigation bullet: mitigations matched to the cause avoid the utility cost; unmatched ones pay it or reverse. | S4, S6, S3, S7 |
| §3.2 Histories, Memories, and Interventions | Add three short paragraphs: the generated corpus (matched stale-restatement levels, the other axes observational); the closed loop (write-back of the executor's log line, neutral control with the same update schedule, three rounds, re-dating rule); the diagnosis (deterministic localization to the block, three judges, four labels). Add the one-line mandate and rebuild-every-three-blocks to the interventions paragraph. | S4, S3, S6, S7, S1 |
| §4.1 Incremental updating produces the most failures | Keep the figure. Add one sentence and one appendix column: rebuilding from the history every three blocks removes most laundering in every domain (five Baseten writers, three seeds per domain). Hybrid and retrieval stay in the appendix with the writer-dependence stated. | S1, proposed table 1 |
| §4.2 Formation and propagation | Keep as is. Optionally add Inkling and Flash to the P(F) table (their typed incremental paper-route runs exist at three seeds). | S5 |
| New §4.3 What triggers laundering | The corpus table: stale 0 / 2 / 4 with P(F), US, AU; one sentence that amendment versus revoke-and-replace and the gap are observed differences on unmatched histories. Population: the paper's three Baseten writers, GPT-OSS executor; the added writers in the appendix. | S4, proposed table 2 |
| New §4.4 Where the error enters | The cause-by-setting table (memory updates, requests, records; four labels). One paragraph: procurement and finance apply restatements from someone without authority; the closed loop reads the agent's own line as a grant; cybersecurity fails at the block carrying the duty officer's signed change set, where the update is rejected. State that the labels are three LLM judges' majority (agreement figure) and unchecked by a person. | S6, proposed table 3 |
| New §4.5 The agent's own actions enter its memory | The closed-loop figure (two arms, three rounds, three domains). Records minted from write-back lines, authorized use down 24 points at round 3 pooled (47 in cybersecurity), unauthorized submission up by about two points with an interval that barely excludes zero over five writers and includes it over the paper's three; stated as small and uncertain. Population: the five Baseten writers, canonical seed. | S3, proposed figure 1 |
| §4.4 → §4.6 Mitigations frontier | Replace the pooled frontier by the domain-facet figure with four mitigations and two populations stated in the caption (the paper's five writers for gate and event sourcing; the five Baseten writers for the mandate and rebuild, at three seeds). Text: gate and event sourcing pay in authorized use everywhere and do nothing in cybersecurity; rebuild moves left with no loss; the mandate moves left at no measured cost in procurement and finance and right in cybersecurity, where the judged failures are rejected updates. The explanation of the reversal is stated as the reading the labels suggest. Gate and event sourcing on the added writers go to the existing appendices. | S7, S1, S5, proposed figure 2 |
| §4.3 → §4.7 Writer-general and travels with the memory | Compress to the seven-row table (Inkling and Flash rows from S5) and one sentence on executor agreement. Pressure columns move to the appendix with one sentence here. | S5, proposed table 4 |
| §4.5 Writer-side compute | Move to the appendix with the seven-writer synthesis; keep one sentence in §4.7 or §5. | S5 |
| §4.6 Limitations | Add: the cause labels are LLM judges' and unchecked by a person; the closed loop is at one seed per domain; the corpus lifecycle and gap comparisons are observational; hybrid's benefit is writer-dependent; the extension studies use the five writers available on Baseten and state their population wherever it differs from the paper's five. | claim table |
| §5 Conclusion | One added sentence: the trigger and the point of entry are measurable before deployment, and a mitigation that matches the point of entry avoids the safety–utility trade the provenance defenses pay. | |
| Appendices | New: corpus construction and generator; closed-loop protocol and one-pass variants; diagnosis labels, judge prompt, per-judge tables, agreement, worked examples; mandate at three seeds (pooled, by seed, by writer) and closed-loop mandate (three writers); rebuild timing; hybrid and retrieval; capacity ablation stays five-writer; evaluation cues at seven writers; the third-executor check with GLM 5.3 as an appendix-only note. Extend `source_authority_appendix.tex` and `event_sourcing_appendix.tex` with the added-writer tables. | S1–S7, `results/analysis/` |
| Acknowledgements, funding | Add the extension runs to the inference total (Baseten sponsored; OpenRouter spend as recorded). | |

**Order of work on the Overleaf.** (1) Regenerate every figure and table from this branch and copy the PDFs into `figures/`: `analysis/plot_closed_loop_figure.py`, `analysis/plot_mitigation_frontier.py`, `scratch/proposed_tables.py`, `scratch/section7_seeds.py`, `scratch/section6_v2.py`, `scratch/section_gate_event.py`, `scratch/section_cap2.py`. (2) Restructure the Results headings as in the table above and move §4.5 and the pressure columns to the appendix. (3) Write the three new subsections from Sections 3, 4 and 6 of this note, with the counts and intervals given there. (4) Rewrite §4.6 around the domain-facet frontier. (5) Update the abstract, contributions, limitations and conclusion. (6) One pass over every population statement: the paper's five writers, the five Baseten writers, or seven, named in each caption. The claim table below is the checklist for what each sentence may say.

**Not in the paper, and why.** Rebuild timing (one seed, one domain; appendix paragraph). Hybrid schema and retrieval (writer-dependent; appendix table). One-pass closed-loop variants (nothing compounds in one pass; appendix). GLM 5.3 as an executor (its replays cover the Baseten writers' open-loop studies only, and the paper's five writers' paper-route memories are not available for replay; appendix-only note). Unsafe actions over all requests (a metric the paper does not define; appendix).

"""
s = s[:i] + plan + s[j:]

# status block: the runs still open, so the note's coverage is read correctly
old = "Experiments considered and not run are listed in the appendix."
new = ("Runs still open at the time of this status, and therefore not yet in the tables below: bounded event sourcing for the added writers (cybersecurity complete, finance and procurement running), the cybersecurity capacity test for Inkling, rebuild every three blocks for Inkling at the two other cybersecurity seeds, and the closed loop for Grok 4.3 and Qwen Plus (one of twelve runs complete; the rest paused on OpenRouter credits). "
       "Experiments considered and not run are listed in the appendix.")
assert s.count(old) == 1
s = s.replace(old, new)
# open items: GLM 5.3 decision settled
old = "5. **GLM 5.3's role.** It is a writer in two studies and an executor in every open-loop study. Decide whether the paper reports it as a writer (two studies), as the third executor (with the closed loop, the pressure route and the paper's five writers' paper route stated as two-executor), or leaves it out."
new = "5. **Seven writers on the closed loop.** Grok 4.3 and Qwen Plus, the paper's two OpenRouter writers, have one of twelve closed-loop runs complete; the rest wait on OpenRouter credits (about $32 for the closed loop alone). Until they run, §4.5 states five writers."
assert s.count(old) == 1
s = s.replace(old, new)
DOC.write_text(s, encoding="utf-8", newline="\n")
print("plan written")
