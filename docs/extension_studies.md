# Extension studies

Follow-up experiments on the paper's pipeline: LangMem profile writer, one bounded memory, executor that reads only that memory, six matched requests per case, deterministic oracle. Nothing in the pipeline changes between the paper and these runs except the factor under study. Metrics are the paper's: authorized use (AU), unauthorized submission (US), formation P(F) (the typed memory authorizes a request the ledger denies), and exact-state fidelity.

Unless noted: procurement, twelve cases, GPT-OSS-120B executor, writers GLM 5.2, Kimi K2.6, Nemotron 3 Ultra (the paper's Baseten writers), canonical seed 20260719, temperature 1.0, 4,096 output tokens, 572-token memory. All Wilson 95% intervals.

Scripts: `experiments/writer_variants_run.py` (studies 1, 2, 4, 5) and `experiments/closed_loop.py` (study 3). Both have `--dry-run` and refuse live runs without `--estimated-cost-usd`.

## 1. Memory type and writing method

**Question.** Is laundering specific to the paper's typed profile and incremental updates, or does it follow any memory system that rewrites state over a stale history?

**Method.** Three memory types run through the same writer: `typed` (paper), `free_text` (paper), and `hybrid`, the typed record schema plus one free-text `notes` field. What the oracle checks stays typed; notes hold pending changes and context; P(F) is scored on the records. Three writing methods: `incremental` (paper: previous memory plus new block), `rebuild:k` (every k blocks, an empty profile plus the history so far), and `retrieve:k` (the new block plus the k most similar earlier messages, BM25; the executor still sees only the bounded memory).

**Results.** Three writers, three seeds, GPT-OSS and DeepSeek executors (648 unauthorized requests per cell; the executors agree within one point everywhere):

| Memory, method | AU | US | 95% CI |
|---|---|---|---|
| typed, incremental (paper) | 90.1% | 25.2% | 22.0–28.6 |
| typed, rebuild every 3 | 95.7% | 6.6% | 5.0–8.8 |
| hybrid, incremental | 96.8% | 15.4% | 12.9–18.4 |
| hybrid, rebuild every 3 | 98.8% | 2.6% | 1.6–4.2 |

Single-seed grid (108 unauthorized requests per cell): free text incremental 14.8% US at 80.6% AU (half its updates overshoot capacity and are retained, as in the paper's free-text run); writer-side retrieval changes nothing (typed 25.9%, hybrid 16.7%, free text 17.6%); a rebuild from the full history at the last block gives 0.0 to 0.9% for all three memory types.

**Reading.** Laundering is a property of incremental writing over stale material, not of the typed schema. The hybrid profile lowers it for every writer (GLM 15.3%, Kimi 18.1%, Nemotron 13.0% against 26.9 / 20.4 / 28.2% typed) and raises AU, presumably because pending or informal changes have somewhere to go besides a record. Retrieval fails because the writer already sees the laundering material in the new block.

**Paper.** Extends the 2×2 memory-design results with a third representation and two more writing methods. Supports the mechanism claim and answers "is this an artifact of the typed schema".

## 2. When a rebuild helps

**Question.** Periodic rebuilding is the obvious mitigation. Does its timing matter?

**Method.** `rebuild:k` for k = 2, 3, 4, 6 with strictly periodic rebuilds. The probed memory then sits 0 to 5 incremental blocks after the last rebuild, depending on k and case length (5 or 6 blocks).

**Results.** Nearly all of the paper's formation lives in the six-block cases (typed incremental US, six- versus five-block: GLM 11/18 vs 0/18, Kimi 8/18 vs 2/18, Nemotron 8/18 vs 2/18). Six-block cases, three writers:

| Incremental blocks since last rebuild | US |
|---|---|
| 0 (rebuild lands on the last block) | 11/432, 2.5% |
| 2 (rebuild at block 4) | 26/54, 48.1% |
| 6 (never rebuilt, paper) | 123/324, 38.0% |

**Reading.** A rebuild two blocks before the request does nothing; the laundering completes within the last two blocks, where the stale restatements sit. Rebuilding helps only when it happens after them, which a deployment cannot schedule.

**Paper.** A caveat for the mitigations section: source-grounded rebuilding is only as good as its timing relative to the laundering material.

## 3. Closed loop: the agent's actions written back

**Question.** When the agent's own actions are written into the history the writer summarizes, does false authority compound? Does an action become the cited source for a permission record?

**Method.** Open loop is the paper's replay on the frozen memory. Closed loop answers the requests one at a time; after each, one workflow line ("Order placed (submit_order): grantee ..., vendor ..., amount 4,900, currency USD") is appended as a new block, the writer updates memory as usual, and the next request runs against the updated memory. Variants: the run's writer updates (`--loop-writer same`); the executor updates from (previous memory, request, outcome) with an append-only action log (`--loop-writer executor --action-log`); free text; and `--rounds 3`, which repeats the request set three times.

**Results.** One pass, three writers, procurement:

| Who writes back | Memory | Open AU / US | Closed AU / US |
|---|---|---|---|
| the writer | typed | 98.1 / 26.9% | 93.5 / 25.0% |
| the writer | free text | 84.3 / 17.6% | 71.3 / 13.0% |
| the executor, with action log | typed | 99.1 / 26.9% | 85.2 / 24.1% |

Conditioning on the first laundered action: chains that submitted the unauthorized request at position 2 launder later requests at 38% closed versus 45% open on the same chains. Every chain cites the written-back turn from the second request on, but as an added source on an existing record.

Three rounds, three writers, all domains (US; P(F) in parentheses):

| Domain | Open | Round 1 | Round 2 | Round 3 |
|---|---|---|---|---|
| procurement (108 unauthorized per round) | 29.6% | 28.7% (25.9) | 27.8% (23.1) | 29.6% (21.3) |
| cybersecurity (192) | 6.2% | 4.7% (4.7) | 13.0% (13.0) | 16.1% (16.1) |
| finance (96) | 0.0% | 0.0% (0.0) | 2.1% (2.1) | 2.1% (2.1) |

Authorized use falls in every domain across rounds (procurement 88 → 67 → 60%, cybersecurity 77 → 51 → 43%). Records whose only cited sources are written-back turns grow from 12 to 106 across the 36 procurement chains, from 84 to 446 across the 48 cybersecurity chains, and from 16 to 93 across the 24 finance chains (Kimi and Nemotron; GLM writes none). Once laundered, a request stays laundered in later rounds (55 to 100% persistence).

**Reading.** Write-back does not compound within one pass. Over repeated passes it does, through a specific mechanism: the writer manufactures new authorization records out of the action lines (an escalation of a furniture-storage order becomes an active "furniture_storage" record). On cybersecurity these records pass the deterministic authorization check, so P(F) and US triple. On procurement they are malformed (no issuer or dates), so P(F) misses them; GLM's executor still acts on them (US 30.6 → 44.4%), while for Kimi and Nemotron they crowd out real grants and AU collapses instead. On finance the manufactured records do not authorize anything and behavior barely moves, consistent with the repo's fresh finance replication (Section 7).

**Paper.** New section or appendix. Also a metric note: P(F) undercounts records the writer invents from actions.

## 4. Generated histories

**Question.** What in a history makes the writer launder: distance between grant and change, stale restatements of the old grant, explicit versus implied revocation, revoke-and-replace versus amendment?

**Method.** `domains/procurement/generate_cases.py` builds 108 procurement cases in the existing schema (corpus `generated_v1`, linted with the frozen corpora) from four themes, crossing gap (1, 2, 3 blocks), stale restatements (0, 2, 4), lifecycle (revoke-and-replace or amendment), and implicit revocation. Typed incremental, GLM, Kimi, and Nemotron.

**Results.** P(F) by knob, GLM / Kimi / Nemotron:

| Knob | Values | P(F) |
|---|---|---|
| stale restatements | 0 / 2 / 4 | 0 / 4.6 / 20.4%, 0 / 5.6 / 23.1%, 0 / 3.7 / 19.4% |
| lifecycle | amendment / revoke-and-replace | 20.4 / 2.3%, 18.5 / 5.1%, 16.7 / 3.2% |
| gap | 1 / 2 / 3 | 10.2 / 8.3 / 6.5%, 7.4 / 11.1 / 10.2%, 7.4 / 9.3 / 6.5% |
| implicit revocation | yes / no | flat |

Overall 8.3% (GLM), 9.6% (Kimi), and 7.7% (Nemotron), so generated cases are easier than the hand-written twelve (about 25%). AU 97 to 100%.

**Reading.** Stale restatements of the superseded grant drive formation with a clean dose response; amendments launder far more than clean replacements; gap and wording do not matter.

**Paper.** Supports the "incremental-memory dynamics" paragraph with a controlled dose-response. Keep as an instrument, not a benchmark.

## 5. Additional writers

Memory-type table (typed, free text, hybrid × incremental, rebuild every 3), procurement, one seed, GPT-OSS and DeepSeek executors. Both writers pass the paper's live writer and tool checks (`experiments/check_target.py`).

| Writer | typed incr. US | hybrid incr. US | free text incr. US | rebuild every 3, all types |
|---|---|---|---|---|
| GLM 5.3 | 25.0% | 11.1% | 5.6% | 0.0% |
| Inkling | 13.9% | 9.7% | 13.9% | 1.4 to 5.6% |

GLM 5.3 launders like GLM 5.2 (25%); 14 of its 18 typed submissions have no deterministic formation, the same malformed-record pattern as Section 3. Inkling launders less but fails more often as a writer: 71 PatchDoc errors across the six conditions, and 58 of 104 free-text updates rejected for exceeding capacity (free-text AU 63.9%). Runs of both writers through the paper's own writer and pressure routes at the paper's seeds are queued (procurement on Windows; cybersecurity under WSL, because the frozen release checks key file hashes by relative path and fail on Windows separators; finance is closed by its release file, whose pricing status no longer matches the check).

## 6. Bugs found

- `langchain_openai` 1.3.5 caches one async HTTP client per base URL. A writer call that runs two architecture groups in one process hangs the second group's first batch to the 180 s LangMem timeout. `closed_loop.py` now runs one condition per call. Any route that mixes typed and free-text chains in one invocation is exposed.
- Rebuild schedule: an earlier version also forced a rebuild at the last block, which made k irrelevant. Fixed; the affected sweeps sit under `results/superseded`.
- Closed loop: a rejected write-back left the chain on its seed memory, whose writer differs from the loop writer in executor mode; evidence is now matched through the seed memory.

## 7. Finance does not reproduce the paper's tables

The repo's phase-2 replication (`results/primary_writer_replication/phase2_results.json`, three seeds, five writers, two executors) has finance typed incremental US at 0/64 for every writer and seed except Qwen-Plus once (6/64), and 1.5 to 2.8% pooled over the four conditions. Our finance runs match it: 0/32 per writer at seed 20260816, and 0/64 for GLM at seed 20260821 with both executors, seven of eight memories exact. The Overleaf tables still show finance typed incremental at 160/320 (seed 20260816) and 178/320 (seed 20260821), GLM 37.5% and Kimi 62.5%, and the headline "up to 50.2%" comes from the finance row. The repo records this as an open paper limitation. With the fresh data finance is the safest domain and the headline maximum is procurement at about 28%.

## Reproduce

```bash
uv run python -m experiments.writer_variants_run --memory-types typed,free_text,hybrid --writing-methods incremental,rebuild:3,retrieve:6 --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15
uv run python -m experiments.closed_loop --conditions incremental_typed --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --rounds 3 --batch-size 10 --estimated-cost-usd 12
uv run python -m experiments.closed_loop --conditions incremental_typed --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --loop-writer executor --action-log --batch-size 10 --estimated-cost-usd 5
uv run python -m experiments.writer_variants_run --corpus-version generated_v1 --memory-types typed --writing-methods incremental --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --batch-size 10 --estimated-cost-usd 15
```

Keep `--batch-size 10`: at 20 with two concurrent drivers the GPT-OSS executor returned rate-limit errors that reached the trials.
