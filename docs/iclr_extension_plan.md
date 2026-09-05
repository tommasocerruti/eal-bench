# EAL-Bench for ICLR 2027: proposed additions

Working document, not committed. 2026-09-04. Written against the PALM draft in
`eal-bench-paper/main.tex` and the public repo at `24bb9ee` (only `main` exists on origin; all
PRs are merged; the source-authority gate and event-sourcing code are not in the public repo, so
they must live in a private checkout).

ICLR 2027: abstract Sept 18, full paper Sept 25 (AoE).

Each addition below states the research question, how it is run, and how it ties into the
existing paper. All of them are memory conditions, controls, interventions, or replays on the
same frozen cases, scored by the same deterministic oracle, with the same paired case-family
cluster bootstrap. The paper's 2x2 of representation (free-text, typed) x update strategy
(one-shot, incremental) is kept; one factor is added (the memory system that carries out the
update); everything else holds the frozen memory fixed and changes exactly one thing, as the
pressure and exact-repair interventions already do.

Two facts about the current pipeline that the additions build on:

- The executor cannot write to memory. Its only tools are `submit_order`,
  `request_authorization`, and `decline_order`. It receives memory as a frozen, hashed
  `FrozenEvidence` payload inside `<PERSISTENT_MEMORY>`, reused across probes and both executors.
- Incremental free-text memory in LangMem is already rolling compaction: the writer receives the
  previous memory and the new block and rewrites the whole profile. "Compaction" is not a missing
  condition; other systems and other read-time behavior are.

---

## 1. Memory type and writing method (extends Section 3.2, "Memory construction")

**Scope rule (Tommaso, 2026-09-05).** Every variant keeps the paper's pipeline: a LangMem
writer turns the history into one bounded memory, and the executor reads only that memory.
Nothing that skips memory writing or hands the executor raw history is in scope (the
full-history and faithful controls already cover that side). A plain transcript summary is
the paper's free-text memory, so it is not a new condition.

**Research question.** Does laundering depend on how the memory is shaped (memory type) or on
how the writer is fed at each update (writing method), holding the writer, the memory system,
and the executor fixed?

**How.** Two new factors on the writer route, crossed on the same cases and seeds.

- *Memory type.* Beside typed and free text, one hybrid, with the typed/free split fixed
  before any run: every field the oracle checks stays in the typed records and one free-text
  notes field holds pending changes, informal requests, and context. It runs through the same
  LangMem writer with the extended schema; P(F) is measured on the records as for typed memory.
- *Writing method.* Beside incremental (previous memory, new block): periodic rebuild, where
  every k blocks the writer rebuilds memory from the accumulated raw history instead of
  updating the previous memory; and writer-side retrieval, where the writer also sees the k
  earlier messages most similar to the new block. The executor still receives only the
  bounded memory.

Procurement first, one seed, two or three writers, one executor; three domains later if the
effect is clear. Code: `experiments/writer_variants_run.py`.

**Ties in.** Section 4.1 attributes the failures to incremental updating within one system;
this separates what is due to the memory's shape from what is due to the update input, and
tests the two most natural fixes a practitioner would try first (rebuild from source
periodically; give the writer more context) without changing the executor. Related work
(compaction papers, MemIR) slots in here.

---

## 2. Closed loop (new intervention, Section 3.2)

**Research question.** Right now the executor's decisions never go back into memory. If they do,
does one bad decision make the next one more likely?

**How.** Same experiment as the paper, one change. Each case has six requests. Today all six are
answered against the same frozen memory. Instead, answer them one at a time: after each answer,
add one line to the history saying what the agent did ("Order placed: TableWorks, coffee service,
USD 5,700" or "Order escalated for approval"), let the same writer update memory as usual, then
ask the next request. The first request is identical to the paper, so it doubles as a check. The
added line comes from the system, not the CFO, so the true permissions never change. Nothing else
changes, and the paper's existing numbers are the baseline.

**What we measure.** The same AU, US, and P(F), plotted by request position 1 to 6 with the
paper's rate as a flat line. Plus one new count: how often a stored permission cites the agent's
own action as its source.

**Scale.** Procurement, 12 cases, five writers, GPT-OSS executor, one seed: about 600 writer
updates and 720 executor calls.

**Ties in.** The paper shows bad memory causes bad actions (exact repair, 98.6% to 0%). This asks
whether bad actions cause bad memory, which closes the loop and tests whether the absorbing state
grows rather than just persists. It is also what makes "no attacker needed" bite: Zombie Agents
gets this loop by injection; here it comes from normal operation.

**Follow-ups, only if the effect is nonzero.** Let the executor write memory itself through an
`update_memory` tool instead of a separate writer. Answer the unauthorized requests first versus
last. Record the action as the agent's own note instead of a system line. Run the six requests
through twice.

**Setup (code).** A `closed_loop` study route in `domains/procurement/studies/routes.py`, copied
from how the pressure route reuses a finished writer run via `--source-run`. Per request: call
`executor_plan`, turn the returned tool call into a one-turn block (`actor_id =
procurement_system`, time = the request's action time), pass it to `langmem_writer` as an
ordinary `new_conversation_block` update, repeat. Templates must not contain hidden IDs or the
leakage validator rejects them. Scoring is unchanged plus the self-citation count over
`source_turn_ids`.

---

## 3. Generated histories (extends Section 3.3 "Cases and experimental units")

**Research question.** What about a history makes the writer get the permissions wrong? The
paper has 12 hand-written procurement cases, so it can say that revocations are where errors
enter, but not what makes a revocation easy or hard to track. Concretely: does it matter how many
blocks pass between a permission being granted and being revoked; how often people keep
repeating the old, revoked permission afterwards; how long the history is overall; how many
permissions are in play at the same time; and whether the revocation is stated outright ("I
revoke auth_catering") or only implied ("coffee is now handled under the framework contract")?

**How.** Write a generator that produces new procurement cases in the same YAML format as the
existing 12, so compilation, linting, the hidden ledger, the matched request pairs, and the
rendering all work unchanged. The generator picks the sequence of authorization events (grant,
amend, revoke, replace) and the filler around them from the categories the repo's
`benchmark_blueprint.yaml` already lists, and lets us set the five properties above directly.
Event turns come from templates so the ledger is exact; filler turns come from templates and can
be paraphrased by Opus 4.8, the model already used for authoring and absent from evaluation.
Cybersecurity and finance cases are already built this way in code (`corpus_v3.py` through
`corpus_v12.py`), so this is formalizing what the repo half-does by hand. Minimal version for
Sept 25: procurement, vary "blocks between grant and revocation" and "how often the old
permission is repeated afterwards" at three levels each, eight cases per cell, 72 cases, three
writers, typed incremental, one seed, GPT-OSS. Human review of a 10% sample in the appendix.

**Ties in.** The mechanism report says revocation is where errors enter (50% of the time in
procurement, 100% in cybersecurity, on 14 and 13 examples), that repeated stale statements are
what the writer most often mistakes for authority, and that mixing records happens only when
several permissions coexist. Those are guesses with wide intervals; the generator turns them
into curves with tight ones and gives Section 4 a "what makes histories hazardous" subsection.
It also answers "8 to 16 hand-written cases" and, with the sliding-window and retrieval systems
of Section 1, shows exactly when reading the raw history misses the revocation.

**Proposed text.** "We add a generator that samples histories from the blueprint's grammar over
authorization events under controlled parameters and emits cases in the benchmark schema, so
that compilation, the canonical ledger, matched probe pairs, and presentation are unchanged. We
vary (i) the number of blocks between a grant and its revocation, (ii) how often the revoked
permission is restated afterwards, (iii) history length, (iv) the number of concurrent grants,
and (v) whether the revocation is explicit or implicit, and report P(F) and final-state error as
functions of each."

---

## 4. Mitigations (Section 3.2 "Mitigations")

**Already in the paper.** The source-authority gate and bounded event sourcing on the shared
three-seed typed-incremental population (Section 4.4, Appendices A.10 and A.11): unauthorized
submission 25.3% to 7.3% or 9.0%, authorized use 93.3% to 53.8% or 64.7%. Event sourcing loses
mainly because the writer misses 2,211 authorization-changing events.

**Status.** Not built in this pass. Majority voting over extractions targets those missed events
directly but needs the event-sourcing code, which is not in the public repo. The
check-content-against-source idea is parked (Mika: possibly trivial; not in Tommaso's list).
Writer-flagged uncertainty is out (poor calibration). Revisit once the event-sourcing code is
available.

---

## 5. Writers (small addition to Section 3.3 "Models and inference")

**Research question.** Does laundering shrink with writer capability, or is it capability-gated
in the direction The Memory Trust Gap reports (larger models over-trust stale state more)?

**How.** Not a matrix. Procurement, one seed, typed incremental, 12 chains per model: GLM 5.3,
Kimi K3, DeepSeek V4 Flash on Baseten (all pass `check_target --live`; Kimi K3 also passes the
LangMem writer check), and Fable 5.1 through the `anthropic` provider on the work account, as
writer and as executor. A few dollars per model.

**Ties in.** Table 3 already shows five writers moving together on AU and US. Adding points on
the same slice extends that plot along a capability axis and answers "your models are weak."
Running Fable as executor tests P(G|F) at the frontier: whether a strong executor still acts on
false authority when memory is its only evidence, which Section 4.3 says the artifact carries
regardless of executor.

---

## 6. No new calls

Promote the mechanism report into Section 4: per-transition introduction hazards, the category
ranking (scope broadening creates apparent authority in 74% of affected states, revoked-record
retention 54%, boundary loss 48%), Kaplan-Meier persistence, and the domain contrast in
self-repair (cybersecurity 45% because portfolio replacement rewrites the state; procurement 0%
because it retains history). This is what makes "absorbing state" a structured claim.

---

## 7. Suggested order

- To Sept 11: Section 6 into the draft; summary and atomic-store systems in procurement;
  generator emitting valid YAML through compile and lint; closed-loop route scaffolded.
- To Sept 18 (abstract): closed-loop main run and controls; temporal-graph and retrieval systems;
  generator minimal grid; mitigation 1.
- To Sept 25: remaining systems in cybersecurity; mitigation 2; writer slice; figures; related
  work.
- Rebuttal or v2: closed-loop ablations 1 to 5, full generator grid, mitigations 3 and 4.

---

## 8. Related work since the draft (June to September 2026)

- [Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents](https://arxiv.org/abs/2606.22528) (ConstraintRot). Compaction drops in-context safety policies and violations rise from 0% to 30%; the constraints are static, so EAL's contribution is the lifecycle case in which the pinned object itself must change.
- [Lost in Compaction: Evaluating Side-Constraint Loss under Context Compaction](https://arxiv.org/abs/2608.11242) (COMPINT). Compactors keep 17% of user side-constraints and an extraction module restores over 90%, which is structurally the event-sourcing writer applied to static rules.
- [AI Guardrail Survival under Single-Cycle Agentic Self-Summarization](https://arxiv.org/abs/2608.11392). Rules that textually survive summarization often stop functioning, supporting EAL's choice to score behavior and deterministic state rather than text presence.
- [The Compaction Cliff in Long-Running AI Agent Memory](https://arxiv.org/html/2608.22752v1). Memory quality degrades sharply under repeated compaction; cite alongside the compaction papers above.
- [The Memory Trust Gap: Capability-Dependent Failures in Persistent-Memory Agents](https://arxiv.org/html/2609.01852). Over-trust of stale memory grows with model size on the Qwen3 series, which predicts that stronger writers will not remove laundering.
- [Can Agent Memory Systems Track Evolving State?](https://arxiv.org/html/2608.19652) (StateMemBench). 234 multi-session scenarios where current-state accuracy is 0.15 to 0.21 across six backends; the closest evolving-state benchmark, but QA accuracy with no authorization, action, or formation-propagation split.
- [STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?](https://arxiv.org/abs/2605.06527). Implicit conflicts invalidate memories without explicit negation and the best model reaches 55%; already cited, and its implicit-revocation idea is a generator parameter in Section 3.
- [TrustMem: Learning Trustworthy Memory Consolidation for LLM Agents with Long-Term Memory](https://arxiv.org/html/2606.25161v1). An RL-trained memory-transition verifier cuts corruption by 79%, the learned counterpart of the write-time checks in Section 4.
- [Mitigating Provenance-Role Collapse in Long-Term Agents via Typed Memory Representation](https://arxiv.org/pdf/2605.25869) (MemIR). Separating evidence, cues, and claims in a typed intermediate representation prevents source-monitoring errors, convergent with the hybrid typed-provenance system in Section 1.
- [MemDelta: Controlled Baselines and Hidden Confounds in Agent Memory Evaluation](https://arxiv.org/pdf/2606.29914). Memory evaluations need full-context and retrieval baselines and embedding choice alone moves accuracy by 6 points, which is why Section 1 includes the retrieval control with a fixed embedding model.
- [Control-Plane Placement Shapes Forgetting: An Architectural Study of Agent Memory Across Thirteen System Configurations](https://arxiv.org/pdf/2606.15903) (ForgetEval). Production memory failures are forgetting failures rather than recall failures, and where the LLM sits in the mutation path determines them, which frames revocation as forgetting under mutation.
- [When Memory Becomes Authority: Benchmarking Authority Collapse at the Memory Consolidation Boundary](https://arxiv.org/abs/2608.01679) (AuthMem-Bench). Already cited; consolidation preserves a claim while erasing its source constraints in 48 of 49 configurations, with a fixed claim rather than an evolving lifecycle.
- [Honest Lying: Understanding Memory Confabulation in Reflexive Agents](https://arxiv.org/html/2605.29463v1). Reflexion-style agents store confident wrong reflections that entrench across trials, the closest precedent for the closed-loop intervention in Section 2.
- [Zombie Agents: Persistent Control of Self-Evolving LLM Agents via Self-Reinforcing Injections](https://arxiv.org/pdf/2602.15654). Injected content persists through self-updates in self-evolving agents, the adversarial counterpart of endogenous closed-loop laundering.
- [MemSyco-Bench: Benchmarking Sycophancy in Agent Memory](https://arxiv.org/html/2607.01071v2). Memory absorbs user-pleasing distortions; relevant to the recording-source ablation where the agent's own note is the source.
- [Governing Evolving Memory in LLM Agents: Risks, Mechanisms, and the SSGM Framework](https://arxiv.org/pdf/2603.11768). A governance framework for evolving memory that names error accumulation across updates as a risk without measuring it; EAL supplies the measurement.

---

## 9. Repo notes

- Only `main` exists on origin (fetched today, no new commits since `24bb9ee`). The gate and
  event-sourcing code are not in the public repo; ask Tommaso where they live.
- Windows: `--validate-only --all-domains` fails for cybersecurity and finance because hash
  manifests record backslash paths (`corpus_v3\calibration_v3.yaml`); procurement validates.
  Fix with `PurePosixPath(...).as_posix()` where source paths enter a hash. Clone with
  `core.autocrlf=false`.
- Local uncommitted changes in this checkout: three targets appended to `config.yaml`
  (`glm_5_3_baseten`, `kimi_k3_baseten`, `deepseek_v4_flash_baseten`); `.env` with the DEPLOYED2
  key as `BASETEN_API_KEY` (git-ignored). Total live usage so far: seven smoke-test requests.

---

## 10. Other ideas (not scheduled)

Kept from the first pass. Each fits the same protocol; none is on the three-week path.

- **Executor evidence budget.** Give the executor a `fetch_source(turn_id)` tool with a budget b
  in {0, 1, 3, unbounded} over the immutable history, holding the frozen memory fixed. Tests
  whether provenance links are actionable rather than only auditable, and whether the paper's
  claim that executor-side alignment cannot close the gap survives when the executor has any
  evidence beyond memory. A variant returns a stale restatement instead of the true turn to
  check whether fetched evidence is used. Gives an executor-side compute-safety curve mirroring
  the writer-side inference-scaling curve in Section 4.5.
- **Free-text formation labels.** The draft concedes formation is measurable only for typed
  memory. A blinded extraction by the leave-one-out writer trio converts each frozen free-text
  memory into the typed schema; a stratified 10% sample is human-validated
  (`studies/annotation_agreement.py` exists for this); the deterministic `A_M` then yields P(F)
  for free text. Reported as a validated instrument with agreement statistics, not as a judge.
  Would let Table 2 cover all four memory conditions.
- **Pressure as dose-response.** Replace the single treatment with factored manipulations
  (urgency, stakes, authority-claiming rhetoric) at three intensities, on one domain's frozen
  memories, three seeds, both executors. Fixes the single-seed, single-executor caveat the draft
  flags and connects to the Okamoto et al. compliance framing. Executor-only calls.
- **Verifier as selector.** Rerun the k = 8 inference-scaling pools with the write-time
  source-support check (Section 4, item 2) as the selector in place of an LLM reviewer, to test
  whether a deterministic-leaning verifier closes the 28-point gap between exact-memory
  availability and selection.
- **Frontier-model matrix.** Only if a reviewer demands it: the full 2x2 by three domains by
  three seeds for one or two frontier writers. Expensive and not the point; the cheap slice in
  Section 5 answers the objection first.

**Framing notes.** The reviewer objections to plan around, most likely first: "this is LangMem"
(Section 1); "why not just retrieve" (Section 1, retrieval control); "8 to 16 hand-written cases"
(Section 3); "compaction erasing constraints is known" (Section 8, first four entries); "weak
writers" (Section 5); "benchmark paper" (framing below).

Thesis to lead with: false authority in memory is an absorbing state. Once written it persists
and propagates at about 99%, nothing downstream recovers it, and only write-time verification or
a different maintenance mechanism helps. Contribution list to aim for: (1) phenomenon and
decomposition, kept; (2) absorbing dynamics and system generality (Sections 1, 2, 6); (3)
verification bottleneck and an expanded mitigation frontier (Section 4); (4) EAL-Bench plus a
procedural generator with dose-response curves (Section 3). Title candidates: "False Authority
Is an Absorbing State: Endogenous Authorization Laundering in Agent Memory"; "Agent Memory
Launders Authority, and Nothing Downstream Recovers It"; or keep the current title and move the
absorbing-state and verification results into the abstract.
