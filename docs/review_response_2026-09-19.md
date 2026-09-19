# Response to the 2026-09-19 read-through

Line numbers refer to the reviewer's list. For every item: what the data say, what a fix requires, and whether it was applied. Only the typo and mechanics items at the end were changed in the paper; every substantive item is a proposal awaiting your decision.

Data sources used: `scratch/iclr_seven/parity_pool.json`, `results/analysis/section7_seven.md`, `results/diagnosis/failures.csv`, the event-sourcing analyses under `results/analysis/event_sourcing/`, the failure-mechanism CSVs behind Table 10, the generated corpus trials, the paper-route trials of Inkling and Flash, and the closed-loop figure CSV.

## Substantive errors and contradictions

### 1. Conclusion mislabels the mitigations (lines 478 to 481)

**Finding.** Confirmed. The sentence describes the writer instruction (procurement and finance improve without a legitimate-use cost, cybersecurity worsens); source filtering drops legitimate actions to 12.8% in procurement and 28.0% in finance and changes nothing in cybersecurity. The sentence is in the co-author's rewrite of the conclusion, so I did not touch it.

**Fix.** Replace "Source-authority rules" with "A writer instruction about authority" in that sentence, and give source filtering its own clause: "source filtering and event sourcing remove most laundering in procurement and finance at a large cost in legitimate actions and change nothing in cybersecurity". Wording only; every number needed is already in Tables 28, 31 and 33.

### 2. The 5.4% surviving false-authority rate (line 430) is not in the appendix

**Finding.** Correct. 5.4% is the three-seed, seven-writer, typed-incremental representation-level rate after the gate: 149 of 2,772 unauthorized requests (five original writers 108 of 1,980, Inkling and Flash 41 of 792, all 41 in cybersecurity). It was computed by `gate_added_formation.py` from the frozen gated memories in the gate runs and never written into C.1. The 2.4% in Table 29 is a different population (primary seed only, one-shot and incremental typed together).

**Fix.** Add one sentence to C.1 after the aligned behavioral table: "At the representation level on the same three-seed population, false authority survives the gate for 149 of 2,772 unauthorized requests (5.4%), all but eight of them in cybersecurity." Data in hand; no run needed.

### 3. Table 32 and Table 10 disagree on the typed-incremental false-authority rate

**Finding.** Real, and it is on our side, not a filtered population. The five original writers carry the same published counts in both tables (153/540, 100/960, 241/480), so the only fresh computation, and the only disagreement, is for the added writers:

| Domain | Table 10 added writers (failure-mechanism script) | Table 32 added writers (event-sourcing baseline) |
|---|---|---|
| procurement | 52 / 216 | 43 / 216 |
| cybersecurity | 83 / 384 | 41 / 384 |
| finance | 104 / 192 | 64 / 192 |

Both scripts call the same ledger function `domain.memory.authorizes` on a typed memory, so the difference is in which memory state each evaluates for a request, not in the definition. Per writer in finance, Flash is 68/96 in one and 36/96 in the other. The cybersecurity value equalling the unauthorized action rate is not suspicious in itself: both executors act on every false grant there, so UA is exactly twice F on twice the trials.

**Fix.** A per-request diff of the two evaluations for one writer and seed (about an hour) to find which state the failure-mechanism script picks up, then recompute whichever is wrong. This matters beyond Table 10: the abstract's "up to 51.3%", the main text's 27.1%, and A.5's 733/2,772 all come from the failure-mechanism side. If the event-sourcing side is right, the headline becomes 45.4% and the pooled rate 23.2%. I recommend doing this before anything else in this list.

### 4. Main-text instruction comparison mixes baselines (lines 459 to 464)

**Finding.** Correct, and it was introduced today when Table 2 and Table 35 were given Table 5's typed-incremental cells while Table 33 kept its own paired baseline. Three typed-incremental cybersecurity baselines now appear: 10.5 (paper writer route, Table 5), 12.2 (the design runs, which rerun typed incremental memory alongside the variants), 12.5 (capacity test, canonical seed, four writers). Table 33's hybrid column matches Table 2 exactly because both come from the design runs; its typed column does not because Table 2's typed row comes from the writer route.

**Fix, two options.** (a) Use the design-run typed baseline (25.7, 12.2, 42.8) in Table 2's last block, Table 35 and the frontier, so every writer-side comparison is paired within its own runs, and say in one sentence that the design runs rerun typed incremental memory. (b) Keep Table 5's numbers and state in C.3 that Table 33's paired baseline differs from the writer route by at most three points. Either way the §4.6 sentence must quote one baseline per domain. I recommend (a): the paired analysis is the one with intervals, and the reader can see the 26.6 versus 25.7 difference as run-to-run noise rather than an unexplained edit.

### 5. B.6 factorial does not multiply to 108 (line 1461)

**Finding.** The text is missing a factor. The corpus has three lifecycle variants, not two: amend in place (36 cases), revoke and issue an explicit replacement (36), and revoke and issue an implicit replacement (36). Four themes times three restatement levels times three gaps times three lifecycles is 108, and 36 cases per restatement level times seven writers gives the 252 memories per row.

**Fix.** Wording in B.6: "whether the change amends the grant in place, revokes it and issues an explicit replacement, or revokes it and issues an implicit one". The lifecycle comparison in the text ("amendments fail about three times as often as revoke-and-replace") should then say it pools both replacement variants, or be recomputed for each; the generator tags them, so this is a short recount.

### 6. "Written by hand" (B.6) versus LLM-assisted generation (§3.3)

**Finding.** Contradiction confirmed. §3.3 is the accurate statement.

**Fix.** B.6 first sentence: "Because the benchmark histories were authored case by case, the features that might drive the failure are confounded with one another." Wording only.

### 7. Orphaned Grok paragraph (lines 1400 to 1402)

**Finding.** Stale. The paragraph survives from an earlier finance version of the paper; the current finance pressure data give Grok 65 of 256 under pressure, not 11. It matches nothing in the current tables.

**Fix.** Delete the paragraph.

### 8. Table 31 versus Table 13 numerators; Table 28's 26.7 versus 26.6

**Finding.** Explained. The event-sourcing and gate runs replay the baseline memories through the executors inside the paired run rather than reusing the writer-route trials, so the baseline arm is a fresh executor sample on the same memories (for example Inkling procurement: 194 of 216 legitimate actions on the writer route, 193 in the event run; Flash finance: 71 of 192 unauthorized versus 69). Denominators are equal because nothing was excluded.

**Fix.** One clause in the captions of Tables 28 and 31: "baseline trials are re-executed within the paired runs, so they differ from Table 13 by executor sampling." Wording only.

### 9. Table 34's 512 and Table 18's 60

**Finding.** 512 is four writers (GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, DeepSeek V4.1 Flash) times 64 unauthorized requests times two executors; Inkling's capacity arms were abandoned and Grok and Qwen were never run. 60 is the original five writers times 12 procurement cases with one executor. Both captions lost their population statements in the pass that removed "run on these models" wording.

**Fix.** Restore the two population statements in the captions, or run the missing capacity arms (Inkling on Baseten; Grok and Qwen would cost OpenRouter credit). A reviewer will divide the denominators, so the statements should come back.

### 10. C.4: Inkling cybersecurity hybrid "18.8% to 62.5%" versus Table 16's 10.9

**Finding.** Both numbers are real but from different runs: 18.8 to 62.5 is Inkling's canonical-seed cell in the design runs (typed incremental then hybrid, both executors); Table 16's 10.9 is the writer-route plate.

**Fix.** Either quote the design-run pair with "in the design runs" or replace the example with the paired change from Table 33's population. Wording only.

### 11. Table 1 checks for AuthMem-Bench and PPMF on "Formation vs. propagation"

**Finding.** The table gives both a check; the related-work text says separating formation from propagation is what distinguishes EAL-Bench from both. One of the two is wrong. From the text's own descriptions (AuthMem-Bench holds the downstream task fixed while varying source authority; PPMF is a non-amplification property on origin records), neither measures formation and propagation as separate quantities.

**Fix.** Change the two checks to crosses, or soften the text to "measures both and relates them". Content decision for the authors.

## Claims not supported or overstated

### 12. §3.2 promises broadening and a surface sham (line 209)

**Finding.** No result for broadening or the sham appears in any version of the paper, including the submission; only exact repair is reported.

**Fix.** Drop the two interventions from the method sentence, or report them (the controlled-intervention analysis exists in the code, so results could be produced from the frozen memories without new writer runs, but executor replays would be needed).

### 13. "All writers and executors pass model inclusion criteria" (line 247)

**Finding.** §3.2 defines calibration for executors only.

**Fix.** "All executors pass the calibration controls of Section 3.2", or define the writer criterion (writers had to complete the writer route without lost updates).

### 14. "A single write-back has no effect" (line 370) versus the 3.8-point round-1 loss

**Finding.** The sentence refers to the one-pass variant (the actions written back once, no further rounds), which shows no effect; round 1 of the three-round loop is a different measurement and does lose 3.8 points. As written the two are conflated. "Barely moves" for unauthorized actions describes +2.7 points with an interval of +0.7 to +4.6; small, but not zero.

**Fix.** "Writing the actions back once, without further rounds, has no effect" and "the unauthorized action rate rises by under three points". Wording only.

### 15. "Least safe condition throughout" (line 268)

**Finding.** True of the four memory conditions; false once the writer-side rows are in the same table (cybersecurity instruction 20.4, hybrid 14.0).

**Fix.** "the least safe of the four memory conditions in every domain". Wording only.

### 16. "Better writers improve both at once" (line 349)

**Finding.** Inkling has the second-lowest unauthorized rate and the second-lowest legitimate rate, so the claim does not hold writer by writer.

**Fix.** Either compute and quote the correlation across the seven writers or soften to "the two rates are not in tension across writers". Wording, or a one-line computation from Table 3.

### 17. §4.6 title "Pareto frontier" while rebuilding dominates

**Finding.** Already discussed today; your decision was to keep the title. The reviewer's objection is the one I raised: with rebuilding in the plot, the non-dominated set is a single point unless cost is an axis.

**Fix.** Your call. If the title stays, the caption's "trade legitimate actions for safety" and the cost clause carry the argument.

### 18. C.4: rebuild at block 4 then two patches (48.1%) worse than never rebuilding (38.0%)

**Finding.** From the one-seed rebuild-timing study on the five original writers (12 procurement cases). At that sample size the two cells are a handful of requests apart and the difference is inside the noise; the sentence presents it without comment.

**Fix.** Add "within the run-to-run variation of a single seed" or drop the two-patch cell. Wording only.

### 19. GLM 5.3 (executor and judge) and Trustcall are unintroduced and uncited

**Finding.** Correct.

**Fix.** One sentence in §3.3 naming GLM 5.3 as the third executor and one of the three judges, plus bib entries for GLM 5.3 and Trustcall. Mechanical, but it adds citations, so I left it for you.

## Worth verifying

### 20. Table 23 open-loop procurement LA 97.0 versus 95.6 from Table 15

**Finding.** Explained: the closed-loop runs rewrite their base memories at the canonical seed inside the run (168 chains), so round 0 is a fresh writer sample, not the plate's memories. UA happens to coincide at 26.4; LA differs by 1.4 points.

**Fix.** One clause in the Table 23 caption. Wording only.

### 21. B.1 final-state error 60.7% at k=1 versus Table 32's 93.3%

**Finding.** Different runs and seeds: the compute study's k=1 pools are separate writer runs at the fixed seed; Table 32 is the writer route at three seeds. The gap is large enough that it deserves a check of the two definitions (the compute study scores the selected candidate's final state; Table 32 scores the final state of the incremental chain). Not resolved here.

**Fix.** Confirm the two definitions match, then either add a footnote or align them. About an hour.

### 22. C.3's 520 of 574 versus Table 26's 571 of 637

**Finding.** Confirmed as open loop versus pooled: the open-loop instruction runs contribute 574 failures with 520 rejected updates; the closed loop with the instruction adds 63 and 51, giving Table 26's 637 and 571.

**Fix.** "of 574 open-loop failures" in C.3. Wording only.

## Typos and mechanics (applied)

- "has the writer" to "have the writer"; "a event-based" to "an event-based"; "source-filtering keeps" to "source filtering keeps".
- Heading period on "Estimation, uncertainty, and reproducibility."; sentence case for "Understanding and preventing false authority."
- Table 25 label "authoritative change misapplied" shortened to "change misapplied", matching Tables 26 and 27, which removes the wrap that produced "misapplieda".
- Finance schema table (Table 9): field column widened so the long field names no longer run into the type column.
- The self-citation of B.5 from inside B.5 removed.
- "two-sentence message" corrected to "three-sentence message" in D.1.
- Range style unified to "to" in the two flagged sentences.
- "disaggregated values" changed to "exact counts" for Table 5.
- McFadyen title: {LLM} protected in the bib entry.

Not applied: the Figure 4 caption's "four strategies" (the baseline is one of the four points); it is your co-author's caption, so I left it. "the three mitigations and the baseline" would be exact.

## Deeper findings and what was applied (2026-09-19, evening)

### Item 3 (Table 10 versus Table 32): root cause found, Table 10 was wrong

`analysis/failure_mechanisms.py` matches a trial to its apparent-authority row by `(state_id, probe_id)` only. State ids are content hashes that repeat across the seed runs of one writer, so when the 18 added-writer runs were passed to one `_build_rows` call (`pf_added2.py`), a trial in the seed-20260821 run could be matched to the apparent-authority row of the same state id in the seed-20260816 run. Only inflation is possible. Recounting one run per call (`pf_added_per_run.py`) gives the added writers 43/216, 41/384 and 64/192, which reproduces the event-analysis baseline row exactly. The direct check on the disputed memory (`authorizes` false at every block, executor acted on 0 of 32 disputed requests) agrees.

Corrected seven-writer false authority: 196/756 (25.9%), 141/1,344 (10.5%), 305/672 (45.4%), pooled 642/2,772 (23.2%). The same collision also merged the per-state error lists (`state_errors[state_id]`), so the A.5 state counts changed: 4,419/7,770 (56.9%) semantic errors and 527/7,770 (6.8%) authority-gaining errors; 7,770 positions and 543/756 non-exact final states were unaffected. The original five-writer numbers (153/540, 100/960, 241/480) were never affected, because they come from the frozen counts.

Applied: Table 10, A.5, Section 4.2 ("25.9% ... within one point"), abstract and contributions ("up to 45.4%"). Table 32 was already right. Propagation (99.0%, 1 of 390) comes from the repair witnesses, not from this matching, and is unchanged.

### Item 4 (two typed-incremental baselines): one baseline now

Both numbers were typed incremental memory over seven writers, three seeds and both executors; the writer route (Table 5) and the design runs that carry the instruction arm were separate samples of the same configuration, differing by at most 3 points. Nothing required two numbers. Table 33 now uses the Table 5 baseline for its typed rows (26.6, 10.5, 45.9; legitimate 96.2, 88.4, 98.8), and the paired changes are recomputed over writer-by-seed pairs with both executors pooled (21 pairs per row), because the frozen five-writer counts carry writer-by-seed cells only. Hybrid rows keep the design-run hybrid baseline at the same pairing unit. Section 4.6 now reads 10.5% to 20.4% for cybersecurity. Direction is still the same at every seed in every domain. Script: `table33_paper_baseline.py`.

### Item 5 (B.6 factorial): three lifecycle variants

108 = 4 themes x 3 restatement levels x 3 gaps x 3 lifecycles (amend in place 36, revoke and explicit replacement 36, revoke and implicit replacement 36). False authority by lifecycle: 140/756 (18.5%) amend, 61/756 (8.1%) explicit replacement, 36/756 (4.8%) implicit replacement; the printed 6.4% pools both replacement variants. B.6 now names the three variants and gives the split.

### Item 21 (60.7% versus 93.3% semantic exactness)

Both use the same notion (fidelity comparison with no field errors, source turn ids excluded). The 60.7% is the fixed-seed compute study, the 93.3% the three-seed writer route; the gap is a difference between the two run sets and stays flagged, with no wording change.

### Rulings applied in this pass

Items 1, 5, 6, 7, 8, 10, 13 ("All executors pass..."), 14, 15, 18, 20 as proposed; item 9 through captions (Table 34 four writers, capacity table five writers). Item 19 not applied: no Section 3.3 sentence and no new citations. Trustcall is the structured-extraction library inside LangMem that the memory writer uses; it appears only in the writer appendix. GLM 5.3 appears only in the appendix as the replay executor and one of three judges. Item 11 (Table 1 checks) and item 16 are untouched pending a ruling; across the seven writers the correlation between average baseline unauthorized and legitimate rates is -0.46.

### Item 21 resolved (2026-09-19, late): two definitions of "exact"

`analysis/event_sourcing.py` marks a final state erroneous when any fidelity field differs, including `source_turn_ids` (the cited source turns); `analysis/writer_ttc.py` excludes `source_turn_ids`. Scoring the same writer-route baseline memories both ways (`final_state_defs.py`, added writers, three seeds):

| Domain | Any field | Without citations | Citation-only |
|---|---|---|---|
| Procurement | 69/72 (95.8%) | 41/72 (56.9%) | 28 |
| Cybersecurity | 49/96 (51.0%) | 49/96 (51.0%) | 0 |
| Finance | 37/48 (77.1%) | 18/48 (37.5%) | 19 |

So Table 32's 93.3% and B.1's 60.7% are the same quantity under two field sets, and cybersecurity's row is unaffected. Applied: one clause in the Table 32 caption naming the difference. Recomputing Table 32 without the citation field would need the five original writers' memories, which are not in the repository (their row comes from the frozen values), so the caption clause is the fix.
