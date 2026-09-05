# Extension studies

Branch `mika/experiments`. All three keep the paper's pipeline: a LangMem
writer turns the history into one bounded memory, the executor reads only that memory, and
the shared executor path scores the same six requests per case. Both study scripts have
`--dry-run` and refuse a live run without `--estimated-cost-usd`. The DEPLOYED2 key is in `.env` as
`BASETEN_API_KEY`.

## Writer variants: memory type x writing method

```
uv run python -m experiments.writer_variants_run --memory-types typed,free_text,hybrid \
    --writing-methods incremental,rebuild:3,retrieve:6 \
    --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten --dry-run
```

Memory types: `typed` and `free_text` are the paper's; `hybrid` is the typed record schema
plus one free-text `notes` field, run through the same LangMem writer
(`experiments/authorization_memory/hybrid_memory.py`). Everything the oracle checks stays typed;
notes holds pending changes, informal requests, context. P(F) is scored on the records.

Writing methods (`experiments/authorization_memory/writing_methods.py`): `incremental` is the
paper's; `rebuild:k` rebuilds memory from the raw history every k blocks and at the last block
(LangMem gets an empty existing profile plus the history so far); `retrieve:k` also shows the
writer the k earlier messages most similar to the new block. Condition IDs encode both, e.g.
`incremental_hybrid__rebuild3`.

Outputs: the usual `memories`, `memory_attempts`, `memory_states`, `evidence`, `trials`,
`model_contexts` JSONL plus `formation.jsonl`; `manifest.json` `summary` has AU/US and
formation by condition. Full procurement grid, one writer, one executor: 792 writer updates
and 864 executor calls. Use a subset.

## Closed loop

```
uv run python -m experiments.closed_loop --writer-targets glm_5_2_baseten \
    --executor-targets gptoss_baseten --dry-run
```

Runs the paper's incremental chains, replays the six requests on the frozen memory (open
loop), then answers them one at a time from the same memory, writing back what the agent did
before each next request (closed loop). `--loop-writer same`: one workflow line is appended
as a new block and the run's writer updates memory as for any block. `--loop-writer executor`:
the executor model updates memory from (previous memory, request, outcome). `--action-log`:
the writer also sees the append-only log of all (request, action, outcome) lines so far.

Outputs add `written_back.jsonl` and `formation.jsonl` (P(F) by position; records that cite a
written-back turn). Twelve cases, one writer: 132 base updates, 120 loop updates, 288 executor
calls.

## Generated histories

```
uv run python -m domains.procurement.generate_cases --gap 1,2,3 --stale 0,2,4 \
    --cases-per-cell 4 --lifecycle both --implicit --version generated_v1 --write --lint
```

Writes and compiles `generated_v1` (108 cases) and lints it with the frozen corpora. The
version registers itself when its JSONL exists, with the same 572-token budget. Case IDs
encode the cell (`procurement_v1_gen_rr_g2_s4_imp_hardware_01`). The official `writer` route
refuses corpora other than `benchmark_v1` (the pre-registration guard in
`domains/procurement/studies/routes.py`); `writer_variants_run --memory-types typed
--writing-methods incremental --corpus-version generated_v1` is the same protocol on the
generated cases. Whitelisting the version there is a one-line change to decide on.

## Changes to existing code

`WriterChainSpec.initial_memory` (continue a LangMem chain from an accepted memory) and
`WriterUpdateSpec.rebuild_from_history` (start one update from an empty profile), both
default off. `generated_v1` registration in `domains/procurement/adapter.py`. Three extra
targets in `config.yaml`.

Not built: extraction majority voting (the event-sourcing code is not in the public repo),
writer-flagged uncertainty, the source-content check (parked outside the repo; Mika flagged
it as possibly trivial and Tommaso did not pick it up).
