# EAL-Bench authorization-failure mechanism analysis

## Scope and data integrity

This report is derived entirely from the ten clean frozen writer runs listed in
`source_runs.json`: five writers in Procurement and the same five in Cybersecurity. No model calls
were made. All source artifact row counts and SHA-256 hashes were verified, every saved incremental
state was reconstructed, and recomputed typed fidelity matched the saved fidelity rows for every
state represented there.

The semantic sample contains 1,270 typed state observations and
140 complete incremental trajectories. Free-text trajectories
are present in the source runs but cannot be semantically scored because no blinded
`memory_annotations.jsonl` files exist. They are recorded without semantic labels in
`coverage_exclusions.csv` and remain represented in aggregate executor outcomes.

## Main findings

1. **Exposure-normalized error entry.** Conditional on the previous typed state being correct,
   introduction hazards were procurement: revocation 7/14 (50.0%; 95% CI 20.0%–75.0%), non authorization update 27/129 (20.9%; 95% CI 12.2%–30.1%), replacement 1/7 (14.3%; 95% CI 0.0%–25.0%), grant 2/59 (3.4%; 95% CI 0.0%–8.3%), narrowing 0/29 (0.0%; 95% CI 0.0%–0.0%), scope transition 0/5 (0.0%; 95% CI not estimable); cybersecurity: revocation 13/13 (100.0%; 95% CI 100.0%–100.0%), grant 68/90 (75.6%; 95% CI 63.6%–86.0%), portfolio replacement 24/64 (37.5%; 95% CI 30.8%–44.3%), narrowing 1/16 (6.2%; 95% CI 0.0%–15.0%), non authorization update 0/1 (0.0%; 95% CI not estimable), replacement 0/1 (0.0%; 95% CI not estimable). These denominators reverse the impression from raw
   counts: Procurement revocations were much riskier than grants, while both Cybersecurity grants
   and revocations were high-risk. Intervals cluster by domain case family; single-family cells are
   reported as not estimable.
2. **Introduction versus persistence.** Pooled typed incremental error introduction was
   143/428
   (33.4%; 95% case-family cluster bootstrap
   25.0%–42.6%). Once incorrect,
   persistence was
   497/562
   (88.4%; 95% case-family cluster bootstrap
   87.3%–89.7%). Procurement
   introduction/persistence were
   15.2%/
   100.0%; Cybersecurity were
   57.3%/
   87.9%.
3. **Persistence survival and spontaneous repair.** 65/
   143 introduced error episodes self-repaired
   eventually (45.5%), whereas 88.4% is the probability of remaining
   erroneous across one observed incorrect-origin transition. The Kaplan–Meier estimates were
   procurement S(1)=100.0%; cybersecurity S(1)=98.8%, S(4)=85.4%, S(7)=19.8%. Procurement repaired 0/37 introductions. Cybersecurity repaired 65/106, and
   portfolio-replacement updates accounted for 62/65
   repairs. Thus the domain contrast is primarily a sequence/representation effect: late
   portfolio replacement rewrites Cybersecurity's current-state portfolio, while Procurement
   retains historical records and its observed later updates never restored a fully correct state.
   Category changes, accumulation, and retained failed updates remain separate episode fields.
4. **Errors that create apparent authority.** The largest category-conditioned state counts were
   scope broadening 26/35 (74.3%), revoked record retention 7/13 (53.8%), boundary loss 26/54 (48.1%), hallucinated authority 4/10 (40.0%), scope substitution 4/10 (40.0%), cross record stitching 3/10 (30.0%). Categories with fewer than ten affected states are omitted from this ranking.
   These are state-level associations when a state carries multiple errors; direct record-level
   attribution is separately available in `semantic_errors.csv` and `category_authority_risk.csv`.
5. **Propagation to action.** Among 86 final typed memory–request pairs for which memory
   deterministically created apparent authority, at least one executor took the submitted action in
   85 and took any unauthorized action in 85/86
   (98.8%). The apparent 0/128 versus 1/128 repair
   discrepancy is an outcome-definition difference, not a data discrepancy: natural memories led
   to 126/128
   targeted submitted actions; exact repair reduced that same endpoint to
   0/128.
   Under the broader any-unauthorized-action endpoint, exact repair was
   1/128
   because one GPT-OSS Cybersecurity replay executed the separate operational alternative while
   rejecting the submitted request. Replay rows are not independent memory generations.
6. **Writer transfer.** All writers produced recurring categories; pairwise category-distribution
   similarity was procurement: median JSD 0.191, point range 0.078–0.240, pairwise 95% CI envelope 0.022–0.588, 12 families, 23–34 error instances per writer; cybersecurity: median JSD 0.076, point range 0.016–0.136, pairwise 95% CI envelope 0.008–0.231, 16 families, 201–571 error instances per writer. Each pairwise estimate now includes a paired case-family
   bootstrap interval and explicit per-writer support in `writer_similarity.csv` and
   `writer_similarity_support.csv`. Cybersecurity provides substantially more error instances and
   tighter intervals; Procurement supports recurrence but is too sparse for precise pairwise
   similarity claims. JSD remains descriptive: 0 means identical normalized distributions and 1
   means disjoint distributions.
7. **Domain transfer.** Shared observed categories were boundary_loss, hallucinated_authority, record_lineage_error, scope_broadening, scope_substitution, undergrant_omission.
   Procurement-only categories were historical_record_omission, record_state_error, stale_state_retention; Cybersecurity-only
   categories were cross_record_stitching, inactive_record_retention, revoked_record_retention. Domain differences partly reflect their
   distinct canonical representation: Procurement retains revoked/superseded history, while
   Cybersecurity memory represents current active state.
8. **Typed versus free text.** Typed memory makes structural and semantic drift directly observable,
   but the tables show that schema validity does not imply canonical authorization validity. The
   current artifacts support behavioral typed/free-text comparisons, not a semantic comparison of
   which free-text error classes occur. Unsafe-action counts over frozen unauthorized-request
   replays were procurement: one shot text 0/360 (0.0%), one shot typed 4/360 (1.1%), incremental text 74/360 (20.6%), incremental typed 111/360 (30.8%); cybersecurity: one shot text 3/640 (0.5%), one shot typed 8/640 (1.2%), incremental text 39/640 (6.1%), incremental typed 48/640 (7.5%).

## Strongest supported mechanistic claim

Within typed incremental memory in these frozen runs, particular history updates repeatedly introduce
deterministic authorization-state errors. Some errors persist or change form across later updates;
a subset creates request-level apparent authority absent from the canonical ledger, and downstream
executors often act on that apparent authority. Exact-repair experiments already frozen in the
source runs strengthen the memory-to-action interpretation, but this observational trajectory
analysis does not make each taxonomy label independently causal.

## Claims not supported

- The artifacts do not support a semantic taxonomy for free-text memory without completing the
  preregistered blinded extraction and human-validation workflow.
- Per-update rows are correlated within a memory chain; they do not establish independent Bernoulli
  hazards or a universal time-homogeneous failure probability.
- Category-conditioned propagation does not uniquely attribute an action when one state contains
  several simultaneous errors.
- Writer similarity does not prove an architecture-invariant cognitive mechanism; it shows recurring
  output-level failure classes under the shared memory-writing operation.
- Domain-specific absences are not evidence that a mechanism is impossible in that domain, especially
  for sparse categories.
- The approximate error × apparent-authority × action decomposition is presented with explicit,
  changing units and is not treated as an unconditional probability identity.

## Audit map

- `semantic_errors.csv`: one row per typed state, affected record, and deterministic category.
- `trajectory_transitions.csv`: one row per incremental state transition.
- `event_introduction_rates.csv`: event exposures, introductions, rates, and clustered intervals.
- `error_episodes.csv`: introduction, persistence, repair, category change, accumulation, and
  retained-update flags.
- `persistence_survival.csv`: Kaplan–Meier risk sets, repairs, censoring, and clustered intervals.
- `self_repair_summary.csv`: repair rates and the later events associated with repair.
- `apparent_authority.csv`: canonical-denied matched requests authorized by remembered state.
- `propagation_events.csv`: individual executor replays, explicitly linked to frozen memories.
- `taxonomy_summary.csv` and `mechanism_summary.csv`: Tables A and B.
- `repair_reconciliation.csv`: targeted-submission and any-action repair endpoints side by side.
- `formation_funnel.csv`, `trajectory_by_step.csv`, `writer_taxonomy.csv`, and
  `persistence_survival.csv`: exact underlying data for Figures A–E.
