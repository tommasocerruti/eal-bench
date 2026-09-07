# Extension studies

Follow-up experiments to the EAL-Bench paper. This note is self-contained: it explains the setup, then for each study the question, what was run, the result, and how it bears on the paper.

## The setup in one page

**The problem.** An agent that works for an organization keeps a persistent memory of who is allowed to do what. That memory is written by a model (the *writer*) that reads the organization's message history as it arrives. A second model (the *executor*) later handles requests, seeing only the memory, never the history. The paper's finding is that the writer routinely produces memory that grants permissions the history never granted or has since revoked, and the executor then acts on them. The paper calls this *endogenous authorization laundering*: the false authority is manufactured inside the agent's own memory, with no attacker.

**A case.** One case is one organization's history: five to ten *blocks* of messages (emails, chat, tickets) in which someone with authority grants a permission, later narrows, revokes, or replaces it, while other people keep referring to the old version. Alongside the text is a hidden *ledger*, the true permission state after each block, used only for scoring. Each case ends with matched *requests*, half authorized under the ledger, half not (for example, an order in a category the grant no longer covers). Procurement has 12 cases and 6 requests each; cybersecurity 16 and 8; finance 8 and 8.

**Memory.** The writer maintains one memory of fixed size (572 tokens in procurement). Two representations: *typed*, a JSON list of permission records with fields such as grantee, scope, validity window, and the message ids that support the record; and *free text*, prose. Two writing methods: *incremental*, where after each block the writer sees only its previous memory and the new block and patches the memory; and *one-shot*, where it sees the whole history once. Incremental is the realistic setting and the paper's main one, because it is how memory systems work in practice.

**Scoring.** The executor answers each request with one of three actions: do it, escalate to a human, or decline. Two behavioral metrics: **authorized use (AU)**, the share of authorized requests the executor carried out (utility), and **unauthorized submission (US)**, the share of unauthorized requests it carried out (the failure). For typed memory a third metric applies without any executor: **formation P(F)**, the share of unauthorized requests that the memory itself, checked mechanically against its records, would authorize. A memory is **exact** if its records match the ledger. Per-request oracles are deterministic, so P(F) and exactness need no model.

**Fixed across every study.** Same writer prompt, same LangMem profile mechanism, same executor prompt and tools, same requests, same scoring. Writers are the paper's three that run on Baseten: GLM 5.2, Kimi K2.6, Nemotron 3 Ultra. Executor is GPT-OSS-120B, with DeepSeek V4 Pro added where noted. Temperature 1.0, 4,096 output tokens for these writers, procurement unless noted. Intervals are Wilson 95%. Only the factor under study changes.

Scripts: `experiments/writer_variants_run.py` (studies 1, 2, 4, 5) and `experiments/closed_loop.py` (study 3). Both have `--dry-run` and refuse live runs without `--estimated-cost-usd`.

## 1. Does the failure depend on how memory is represented or written?

**Why it matters.** A natural objection to the paper is that the failure is an artifact of one memory design. So we vary the design while keeping the writer, executor, and requests fixed.

**What we varied.**

- *Memory type.* The paper's typed and free-text memories, plus a new **hybrid**: the typed records plus one free-text `notes` field. The division is fixed in advance: everything the ledger checks stays in the records; notes hold anything else (pending changes, informal requests, context). P(F) is scored on the records only.
- *Writing method.* The paper's incremental method, plus **rebuild every k blocks** (every k-th block the writer starts from an empty memory and rewrites it from the history so far, instead of patching) and **writer-side retrieval** (the writer sees the new block plus the k earlier messages most similar to it, found by BM25 keyword search; the executor still sees only the memory).

**Result.** Three writers, three seeds, both executors; 648 unauthorized requests per row. The two executors agree within one point on every row.

| Memory, writing method | AU | US | 95% CI |
|---|---|---|---|
| typed, incremental (the paper's setting) | 90.1% | 25.2% | 22.0–28.6 |
| typed, rebuild every 3 | 95.7% | 6.6% | 5.0–8.8 |
| hybrid, incremental | 96.8% | 15.4% | 12.9–18.4 |
| hybrid, rebuild every 3 | 98.8% | 2.6% | 1.6–4.2 |

Single seed, 108 unauthorized requests per cell: free text incremental launders less (14.8%) but loses a fifth of authorized use (80.6%), because half its updates exceed the size limit and are discarded, the same behavior as in the paper's own free-text run. Retrieval changes nothing (typed 25.9%, hybrid 16.7%, free text 17.6%). A single rebuild from the whole history at the last block gives 0.0 to 0.9% for every memory type.

**Reading.** The failure follows incremental writing over a stale history, not the typed schema. The hybrid lowers it for every writer (GLM 15.3%, Kimi 18.1%, Nemotron 13.0% against 26.9 / 20.4 / 28.2% typed) and raises AU, plausibly because informal or pending changes now have a place other than a permission record. Retrieval does not help because the misleading material is already in the new block the writer is reading.

**For the paper.** Extends the memory-design comparison with a third representation and two more writing methods, and answers the schema-artifact objection.

## 2. When does rebuilding from the history help?

**Why it matters.** Periodically rebuilding memory from the source history is the obvious fix. If its benefit depends on timing, it is not a fix a deployment can rely on.

**What we ran.** Rebuild every k blocks for k = 2, 3, 4, 6, strictly periodic. Depending on k and case length (5 or 6 blocks), the memory the executor sees is 0 to 5 incremental patches past the last rebuild.

**Result.** First, nearly all formation in the paper's procurement cases comes from the six-block cases (typed incremental US on six-block versus five-block cases: GLM 11/18 vs 0/18, Kimi 8/18 vs 2/18, Nemotron 8/18 vs 2/18). Six-block cases, three writers:

| Incremental patches since the last rebuild | US |
|---|---|
| 0 (the rebuild lands on the last block) | 11/432, 2.5% |
| 2 (rebuild at block 4, then two patches) | 26/54, 48.1% |
| 6 (never rebuilt, the paper's setting) | 123/324, 38.0% |

**Reading.** A rebuild two blocks before the request does nothing. The laundering happens in the last two blocks, where people restate the superseded permission. Rebuilding helps only when it comes after those messages, which a deployment cannot know in advance.

**For the paper.** A caveat on source-grounded rebuilding as a mitigation.

## 3. Does the agent's own behavior make it worse? (closed loop)

**Why it matters.** In the paper the executor's actions vanish. In a real deployment they are logged and the log becomes part of the history the writer reads. If a wrongly executed order is written back into memory as a fact, it might become evidence for the permission that produced it, and false authority could compound.

**What we ran.** *Open loop* is the paper's design: all requests answered against the frozen final memory. *Closed loop* answers requests one at a time; after each answer one workflow line describing what the agent did ("Order placed (submit_order): grantee ..., vendor ..., amount 4,900, currency USD" or "Escalated for authorization (...)") is appended as a new block, the writer updates memory from it exactly as it would from any block, and the next request runs on the updated memory. Variants: the same writer updates (default); the executor model itself updates from (previous memory, request, outcome) plus an append-only action log; free-text memory; and **rounds**, where the whole request set is asked again, with write-back between every request, so a laundered order from round 1 is in memory when the same request returns in round 2.

**Result, one pass.** Procurement, three writers, 108 unauthorized requests:

| Who writes back | Memory | Open AU / US | Closed AU / US |
|---|---|---|---|
| the writer | typed | 98.1 / 26.9% | 93.5 / 25.0% |
| the writer | free text | 84.3 / 17.6% | 71.3 / 13.0% |
| the executor, with action log | typed | 99.1 / 26.9% | 85.2 / 24.1% |

Conditioning on chains where the first unauthorized request was wrongly executed: later unauthorized requests were executed 38% of the time closed versus 45% open on the same chains. Every chain cites the written-back line from the second request on, but as an added source on an existing record, never as a new permission.

**Result, three rounds.** Three writers, all domains; unauthorized submission with P(F) in parentheses:

| Domain | Open | Round 1 | Round 2 | Round 3 |
|---|---|---|---|---|
| procurement (108 unauthorized per round) | 29.6% | 28.7% (25.9) | 27.8% (23.1) | 29.6% (21.3) |
| cybersecurity (192) | 6.2% | 4.7% (4.7) | 13.0% (13.0) | 16.1% (16.1) |
| finance (96) | 0.0% | 0.0% (0.0) | 2.1% (2.1) | 2.1% (2.1) |

Authorized use falls in every domain across rounds (procurement 88 → 67 → 60%, cybersecurity 77 → 51 → 43%). Permission records whose only cited sources are the agent's own written-back actions grow from 12 to 106 across the 36 procurement chains, from 84 to 446 across the 48 cybersecurity chains, and from 16 to 93 across the 24 finance chains (Kimi and Nemotron; GLM writes none). Once a request is laundered it stays laundered in later rounds (55 to 100% persistence).

**Reading.** Within one pass nothing compounds; the false records were already there before any write-back. Over repeated passes it does compound, and the mechanism is specific: the writer turns action lines into new permission records (an escalated furniture-storage order becomes an active "furniture_storage" record). On cybersecurity those records pass the mechanical check, so P(F) and US triple. On procurement they are malformed (no issuer, no dates), so P(F) misses them; GLM's executor still acts on them (US 30.6 → 44.4%), while for Kimi and Nemotron they crowd out real grants and AU collapses instead. On finance the records authorize nothing and behavior barely moves.

**For the paper.** A new section or appendix, plus a metric note: P(F) undercounts records the writer invents from actions.

## 4. What in a history makes the writer launder? (generated histories)

**Why it matters.** The paper's cases are hand-written, so the features that drive the failure are confounded. Generated cases let one feature vary at a time.

**What we ran.** `domains/procurement/generate_cases.py` builds 108 procurement cases in the existing format (corpus `generated_v1`, validated with the same linter as the paper's corpora) from four themes, crossing: **gap** (blocks between the grant and its change: 1, 2, 3), **stale restatements** (later messages that repeat the superseded grant as if current: 0, 2, 4), **lifecycle** (the grant is revoked and replaced, or amended in place), and **implicit revocation** (stated outright, or only implied). Typed incremental, GLM, Kimi, Nemotron.

**Result.** P(F) by feature, GLM / Kimi / Nemotron:

| Feature | Levels | P(F) |
|---|---|---|
| stale restatements | 0 / 2 / 4 | 0 / 4.6 / 20.4%, 0 / 5.6 / 23.1%, 0 / 3.7 / 19.4% |
| lifecycle | amendment / revoke-and-replace | 20.4 / 2.3%, 18.5 / 5.1%, 16.7 / 3.2% |
| gap | 1 / 2 / 3 | 10.2 / 8.3 / 6.5%, 7.4 / 11.1 / 10.2%, 7.4 / 9.3 / 6.5% |
| implicit revocation | yes / no | flat |

Overall 8.3% (GLM), 9.6% (Kimi), 7.7% (Nemotron), so generated cases are easier than the hand-written ones (about 25%). AU 97 to 100%.

**Reading.** Stale restatements drive the failure with a clean dose response; amendments launder far more than clean replacements; how far apart the grant and its change are, and whether the revocation is explicit, do not matter.

**For the paper.** A controlled dose-response supporting the paper's account of incremental-memory dynamics. Use as an instrument, not a benchmark.

## 5. Additional writers

Two newer models were added as writers: GLM 5.3 and Inkling (Thinking Machines). Both reason at length inside their completions, and the paper's 4,096-token output limit truncated their memory-update calls (the call ended with `finish_reason: length` and no tool call), which produced empty or stale memories. Their output limits were raised to 16k and 32k tokens respectively (`request_parameters` on the target in `config.yaml`; the paper's writers are unchanged), all runs made under the old limit were discarded, and the runs are being redone: the memory-type table at three seeds, the three-round closed loop, and the paper's own writer and pressure routes at the paper's seeds in all three domains. Results will replace this paragraph. Lesson for any new writer: check completion tokens against the output limit before trusting a run.

## 6. Bugs found

- `langchain_openai` 1.3.5 caches one async HTTP client per base URL. A writer call that runs two memory types in one process hangs the second group's first batch to the 180 s LangMem timeout. `closed_loop.py` now runs one condition per call. Any route that mixes typed and free-text chains in one invocation is exposed.
- Rebuild schedule: an earlier version also forced a rebuild at the last block, which made k irrelevant. Fixed; the affected sweeps sit under `results/superseded`.
- Closed loop: a rejected write-back left the chain on its seed memory, whose writer differs from the loop writer in executor mode; evidence is now matched through the seed memory.
- Reasoning writers: see Section 5.

## 7. Finance does not reproduce the paper's tables

The repo's own phase-2 replication (`results/primary_writer_replication/phase2_results.json`; three seeds, five writers, two executors) has finance typed incremental US at 0/64 for every writer and seed except Qwen-Plus once (6/64), and 1.5 to 2.8% pooled over the four conditions. Our finance runs match it: 0/32 per writer at seed 20260816, and 0/64 for GLM at seed 20260821 with both executors, seven of eight memories exact. The Overleaf tables still show finance typed incremental at 160/320 (seed 20260816) and 178/320 (seed 20260821), GLM 37.5% and Kimi 62.5%, and the headline "up to 50.2%" comes from the finance row. The repo records this as an open paper limitation. With the fresh data finance is the safest domain and the headline maximum is procurement at about 28%.

## Reproduce

```bash
uv run python -m experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3,retrieve:6 --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15
uv run python -m experiments.closed_loop --conditions incremental_typed --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --rounds 3 --batch-size 10 --estimated-cost-usd 12
uv run python -m experiments.closed_loop --conditions incremental_typed --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --loop-writer executor --action-log --batch-size 10 --estimated-cost-usd 5
uv run python -m experiments.writer_variants_run --corpus-version generated_v1 --memory-types typed --writing-methods incremental --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15
```

Keep `--batch-size 10`: at 20 with two concurrent drivers the GPT-OSS executor returned rate-limit errors that reached the trials.
