# Finance natural-error → oracle-exact-memory replay

## Selected witnesses

| Seed | Writer | Memory condition | Selected witnesses |
|---:|---|---|---:|
| 20260821 | Qwen Plus 2025-07-28 | incremental_typed | 6 |
| 20260822 | GLM 5.2 | one_shot_typed | 4 |
| 20260822 | Qwen Plus 2025-07-28 | incremental_typed | 2 |

## Outcomes

| Scope | Generated-memory unauthorized actions | Oracle-exact unauthorized actions |
|---|---:|---:|
| Overall | 24/24 | 0/24 |
| Seed 20260821 | 12/12 | 0/12 |
| Seed 20260822 | 12/12 | 0/12 |

## Executor-specific outcomes

| Executor | Generated-memory unauthorized actions | Oracle-exact unauthorized actions | Provider failures | Retries |
|---|---:|---:|---:|---:|
| GPT-OSS-120B | 12/12 | 0/12 | 0 | 3 |
| DeepSeek V4 Pro | 12/12 | 0/12 | 0 | 0 |

## Cost and audit

- Replay-call cost: $0.194016260
- Incremental cost: $0.00
- Routes audited: 10
- Authoritative artifacts: 170
- Authoritative rows: 41832
- Bytes: 715677534
- Provider-visible context hashes verified: 48
- Strict causal pairs verified: 24
- Oracle-exact witness variants verified: 12
- Unique oracle-exact memory artifacts verified: 6
- Provider failures: 0
- Retries: 3
- Manifest hashes, row counts, JSONL parsing, checkpoint hashes, frozen witness sets, call IDs, and provider-visible contexts: passed
- New provider calls: 0
- Paper edits: 0
