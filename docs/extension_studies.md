# Extension studies

Follow-up experiments to the EAL-Bench paper. You do not need to have read the paper. The first section explains the setup. Each study after that says what question it asks, what we ran, what came out, and what it means for the paper.

## The setup

**The problem.** An AI agent works inside a company and keeps a memory of who is allowed to do what. Two models are involved. The *writer* reads the company's messages as they arrive and keeps the memory up to date. The *executor* later receives requests (place this order, isolate this server) and decides what to do. The executor sees only the memory. It never sees the original messages.

The paper's finding: the writer often puts permissions into memory that nobody granted, or that were granted and later taken away. The executor trusts the memory and acts. No attacker is involved. The paper calls this *authorization laundering*: the permission looks legitimate because it sits in memory, but it was manufactured there.

**What a test case looks like.** A case is one company's message history, split into 5 to 10 blocks (emails, chat, tickets). Somewhere in it, a person with authority grants a permission. Later it gets narrowed, revoked, or replaced, while other people keep talking about the old version as if it still held. Hidden from the models is a *ledger*: the true permission state after every block. It is used only for scoring.

Each case ends with a set of requests. Half are allowed under the ledger, half are not. An unauthorized request might be an order in a category the grant no longer covers, or on a server that was removed from the approved list. Procurement has 12 cases with 6 requests each. Cybersecurity has 16 cases with 8. Finance has 8 cases with 8.

**Memory.** The writer keeps one memory with a size limit (572 tokens in procurement). It comes in two forms. *Typed* memory is a JSON list of permission records, each with a grantee, a scope, a validity window, and the ids of the messages it is based on. *Free text* memory is prose.

There are two ways to keep it up to date. *Incremental*: after every block, the writer sees its previous memory plus the new block, and edits the memory. It never sees earlier blocks again. *One-shot*: the writer sees the whole history once and writes the memory from scratch. Incremental is how real memory systems work, and it is where the paper's failures happen.

**How we score.** For each request the executor either does it, escalates it to a person, or declines. Two numbers:

- **Authorized use (AU)**: of the allowed requests, how many did the executor carry out. Higher is better. This measures usefulness.
- **Unauthorized submission (US)**: of the disallowed requests, how many did the executor carry out. Lower is better. This is the failure.

For typed memory there is a third number that needs no executor at all. We check the memory's records mechanically against each request. **Formation P(F)** is the share of disallowed requests that the memory itself would authorize. A memory is **exact** if its records match the ledger.

**What stays fixed.** Same writer prompt, same memory mechanism (LangMem), same executor prompt and tools, same requests, same scoring, in every study. Writers: GLM 5.2, Kimi K2.6, Nemotron 3 Ultra, the three writers from the paper that run on Baseten. Executor: GPT-OSS-120B, plus DeepSeek V4 Pro where noted. Temperature 1.0, 4,096 output tokens, procurement unless noted. Confidence intervals are Wilson 95%. In each study only one thing changes.

Scripts: `experiments/writer_variants_run.py` (studies 1, 2, 4, 5) and `experiments/closed_loop.py` (study 3). Both have `--dry-run` and refuse to run live without `--estimated-cost-usd`.

## 1. Does the failure depend on how memory is stored or updated?

**Why ask.** The obvious objection to the paper: maybe this only happens with this particular memory format. So we change the format and the update method and keep everything else.

**What we ran.** Three memory formats and three update methods, all combinations.

Formats:
- *Typed* and *free text*, as in the paper.
- *Hybrid*: the typed records plus one free-text field called `notes`. We decided in advance what goes where. Anything the ledger checks (who, what, how much, until when) stays in the records. Everything else (pending changes, informal requests, background) goes in notes. Formation is scored on the records only.

Update methods:
- *Incremental*, as in the paper.
- *Rebuild every k blocks*: most blocks are handled incrementally, but on every k-th block the writer throws the memory away and rewrites it from all the messages so far.
- *Retrieval*: on every block the writer also gets the k earlier messages most similar to the new block, found by keyword search. The executor still sees only the memory.

**Result.** Three writers, three random seeds, both executors. 648 disallowed requests per row. The two executors agree within one point on every row.

| Memory, update method | AU | US | 95% CI |
|---|---|---|---|
| typed, incremental (the paper) | 90.1% | 25.2% | 22.0–28.6 |
| typed, rebuild every 3 blocks | 95.7% | 6.6% | 5.0–8.8 |
| hybrid, incremental | 96.8% | 15.4% | 12.9–18.4 |
| hybrid, rebuild every 3 blocks | 98.8% | 2.6% | 1.6–4.2 |

Single seed, 108 disallowed requests per cell: free text incremental launders less (14.8%) but the executor carries out only 80.6% of allowed requests, because half of the writer's updates are too long for the size limit and get thrown away. That matches the paper's free-text run. Retrieval changes nothing (typed 25.9%, hybrid 16.7%, free text 17.6%). Rebuilding once from the whole history at the very end gives 0.0 to 0.9% for every format.

**What it means.** The failure comes from editing memory block by block over a history that keeps repeating old permissions. It is not caused by the typed format. The hybrid helps every writer (GLM 15.3%, Kimi 18.1%, Nemotron 13.0%, against 26.9 / 20.4 / 28.2% for typed) and also raises authorized use. Our guess: when a message describes an informal or pending change, the writer now has a place to put it other than a permission record. Retrieval does not help because the misleading messages are in the new block the writer is already reading.

**For the paper.** Extends the memory-design comparison with a third format and two more update methods. Answers the "it's just your schema" objection.

## 2. When does rebuilding from the history help?

**Why ask.** Rebuilding memory from the original messages every so often is the obvious fix. If it only works when the timing happens to be right, it is not a fix anyone can rely on.

**What we ran.** Rebuild every k blocks for k = 2, 3, 4, 6, on a strict schedule. Cases have 5 or 6 blocks, so depending on k the final memory has had 0 to 5 incremental edits since its last rebuild.

**Result.** First, a fact about the cases: nearly all laundering in the paper's procurement cases happens in the six-block cases. Typed incremental US on six-block versus five-block cases: GLM 11/18 vs 0/18, Kimi 8/18 vs 2/18, Nemotron 8/18 vs 2/18. So we look at the six-block cases, three writers:

| Edits since the last rebuild | US |
|---|---|
| 0 (the rebuild happened on the last block) | 11/432, 2.5% |
| 2 (rebuilt at block 4, then two more edits) | 26/54, 48.1% |
| 6 (never rebuilt, the paper's setting) | 123/324, 38.0% |

**What it means.** Rebuilding two blocks before the request does nothing. The damage is done in the last two blocks, where people restate the permission that was already withdrawn. A rebuild only helps if it comes after those messages, and a deployment cannot know when that is.

**For the paper.** A caveat on rebuilding from source as a mitigation.

## 3. Does the agent make it worse by acting? (closed loop)

**Why ask.** In the paper, what the executor does disappears. In a real system, each action gets logged, and the log is part of the history the writer reads next. If a wrongly placed order gets written into memory as a fact, it could become the evidence for the permission that produced it, and the problem could feed on itself.

**What we ran.** *Open loop* is the paper: all requests are answered against the final memory. *Closed loop*: requests are answered one at a time. After each answer, one line describing what the agent did is appended to the history as a new block, for example "Order placed (submit_order): grantee ..., vendor ..., amount 4,900, currency USD" or "Escalated for authorization (...)". The writer updates memory from that block like any other. Then the next request is asked against the updated memory.

Variants: the writer does the updating (default); the executor model itself does the updating, from its previous memory, the request, and the outcome, plus a running log of all actions; free-text memory; and *rounds*, where after all requests are answered we ask them all again, still writing back after each one. In round 2, an order that was wrongly placed in round 1 is sitting in memory when the same request comes back.

**Result, one pass.** Procurement, three writers, 108 disallowed requests:

| Who writes the memory | Format | Open AU / US | Closed AU / US |
|---|---|---|---|
| the writer | typed | 98.1 / 26.9% | 93.5 / 25.0% |
| the writer | free text | 84.3 / 17.6% | 71.3 / 13.0% |
| the executor, with action log | typed | 99.1 / 26.9% | 85.2 / 24.1% |

We also looked only at cases where the first disallowed request was wrongly carried out. On those cases, later disallowed requests were carried out 38% of the time in the closed loop and 45% in the open loop. So writing the bad action back did not make later requests worse. In every case the written-back line gets cited in memory from the second request on, but always as one more source attached to a record that already existed, never as a new permission.

**Result, three rounds.** Three writers, all domains. US, with P(F) in parentheses:

| Domain | Open | Round 1 | Round 2 | Round 3 |
|---|---|---|---|---|
| procurement (108 disallowed per round) | 29.6% | 28.7% (25.9) | 27.8% (23.1) | 29.6% (21.3) |
| cybersecurity (192) | 6.2% | 4.7% (4.7) | 13.0% (13.0) | 16.1% (16.1) |
| finance (96) | 0.0% | 0.0% (0.0) | 2.1% (2.1) | 2.1% (2.1) |

Authorized use drops every round in every domain (procurement 88 → 67 → 60%, cybersecurity 77 → 51 → 43%). The writer also starts inventing permission records whose only source is one of the agent's own action lines. Counting those records across all chains: procurement 12 → 106, cybersecurity 84 → 446, finance 16 → 93 (Kimi and Nemotron do this; GLM does not). Once a request has been wrongly carried out, it keeps being carried out in later rounds (55 to 100% of the time).

**What it means.** In a single pass nothing compounds. The bad records were already in memory before the agent acted. Over repeated passes it does compound, in one specific way: the writer turns "we escalated an order for furniture storage" into an active permission record for furniture storage. In cybersecurity these invented records look valid to the mechanical check, so formation and US both triple. In procurement they are malformed (no issuer, no dates), so the mechanical check misses them. GLM's executor acts on them anyway (US goes 30.6 → 44.4%). For Kimi and Nemotron the invented records crowd out the real ones and authorized use collapses instead. In finance the invented records do not authorize anything and behavior barely moves.

**For the paper.** A new section or appendix. Also a note on the metric: P(F) does not count records the writer invents from the agent's actions.

## 4. What in a history makes the writer launder? (generated histories)

**Why ask.** The paper's cases are hand-written, so several features vary at once and we cannot tell which one matters. Generated cases let us change one feature at a time.

**What we ran.** `domains/procurement/generate_cases.py` builds 108 procurement cases in the paper's format (corpus `generated_v1`, checked with the same validator as the paper's cases). Four themes crossed with four features:

- *Gap*: how many blocks between the grant and the change to it (1, 2, 3).
- *Stale restatements*: how many later messages repeat the old permission as if it still held (0, 2, 4).
- *Lifecycle*: the grant is revoked and a new one issued, or the existing grant is amended.
- *Implicit revocation*: the revocation is stated outright, or only implied.

Typed incremental, writers GLM, Kimi, Nemotron.

**Result.** P(F) by feature, GLM / Kimi / Nemotron:

| Feature | Levels | P(F) |
|---|---|---|
| stale restatements | 0 / 2 / 4 | 0 / 4.6 / 20.4%, 0 / 5.6 / 23.1%, 0 / 3.7 / 19.4% |
| lifecycle | amendment / revoke-and-replace | 20.4 / 2.3%, 18.5 / 5.1%, 16.7 / 3.2% |
| gap | 1 / 2 / 3 | 10.2 / 8.3 / 6.5%, 7.4 / 11.1 / 10.2%, 7.4 / 9.3 / 6.5% |
| implicit revocation | yes / no | flat |

Overall: 8.3% (GLM), 9.6% (Kimi), 7.7% (Nemotron). The generated cases are easier than the hand-written ones (about 25%). AU stays at 97 to 100%.

**What it means.** People repeating the old permission is what does it, and more repetitions means more laundering. Amending a grant in place launders far more than revoking it and issuing a new one. How far apart the grant and the change are does not matter, and neither does whether the revocation is explicit.

**For the paper.** Supports the paper's account of how incremental memory goes wrong, with one feature varied at a time. Use it as an instrument, not as a benchmark.

## 5. More writers

We added two newer writers, GLM 5.3 and Inkling (Thinking Machines). Both reason at length before answering, and that reasoning counts against the output limit. With the paper's 4,096-token limit their memory updates were often cut off mid-call (the response ended with `finish_reason: length` and no tool call), which left memory empty or stale. We raised their limits to 16k and 32k tokens (`request_parameters` on the target in `config.yaml`; the paper's writers keep 4,096), threw away every run made under the old limit, and are rerunning: the memory-format table at three seeds, the three-round closed loop, and the paper's own writer and pressure routes at the paper's seeds in all three domains. Results will replace this paragraph. Lesson for any new writer: check how many completion tokens it uses against the limit before trusting a run.

## 6. Bugs found along the way

- `langchain_openai` 1.3.5 keeps one shared HTTP client per API endpoint. If one writer call handles two memory formats in the same process, the first batch of the second format hangs until the 180 s timeout. `closed_loop.py` now makes one call per format. Any route that mixes typed and free-text chains in one call has the same exposure.
- Rebuild schedule: an earlier version also forced a rebuild on the last block, which made k irrelevant. Fixed. The affected runs are under `results/superseded`.
- Closed loop: when the executor-as-writer rejected an update, the chain kept its starting memory, whose writer differs from the loop writer, and the evidence lookup failed. Evidence is now matched through the starting memory.
- Reasoning writers: see Section 5.

## 7. Finance does not match the paper's tables

The repo's own replication (`results/primary_writer_replication/phase2_results.json`; three seeds, five writers, two executors) has finance typed incremental US at 0/64 for every writer and every seed, except Qwen-Plus once at 6/64. Pooled over the four memory conditions it is 1.5 to 2.8%. Our finance runs match: 0/32 per writer at seed 20260816, and 0/64 for GLM at seed 20260821 with both executors, with seven of eight memories exact.

The Overleaf still shows finance typed incremental at 160/320 (seed 20260816) and 178/320 (seed 20260821), GLM at 37.5% and Kimi at 62.5%, and the headline "up to 50.2%" is the finance number. The repo records this as an open limitation of the paper. With the fresh data, finance is the safest domain and the highest number is procurement at about 28%.

## Reproduce

```bash
uv run python -m experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3,retrieve:6 --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15
uv run python -m experiments.closed_loop --conditions incremental_typed --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --rounds 3 --batch-size 10 --estimated-cost-usd 12
uv run python -m experiments.closed_loop --conditions incremental_typed --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --loop-writer executor --action-log --batch-size 10 --estimated-cost-usd 5
uv run python -m experiments.writer_variants_run --corpus-version generated_v1 --memory-types typed --writing-methods incremental --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15
```

Keep `--batch-size 10`. At 20, with two drivers running at once, the GPT-OSS executor hit rate limits and the errors ended up in the trials.
