## The paper's provenance mitigations on the added writers

### Source-authority gate (18 of 18 executor-only replays complete)

The gate keeps a record only if every source it cites is a message from a principal allowed to grant authorization; it does not check that the source supports the record's scope or dates. Applied to the added writers' saved paper-route memories (typed incremental, three seeds per domain), then both executors answer the same requests from the original and the gated memory. No writer calls.

| Domain | Writer | runs | memories changed by the gate | records kept / in | US original | US gated | AU original | AU gated | n per arm |
|---|---|---|---|---|---|---|---|---|---|
| procurement | both | 6 | 67 / 72 | 14 / 95 | 21.1% (17.5-25.2) | 7.6% (5.5-10.5) | 94.7% (92.1-96.4) | 10.9% (8.3-14.2) | 432 |
| procurement | Inkling | 3 | 36 / 36 | 1 / 49 | 32.9% (27.0-39.4) | 11.1% (7.6-16.0) | 89.4% (84.5-92.8) | 4.6% (2.5-8.3) | 216 |
| procurement | DeepSeek V4.1 Flash | 3 | 31 / 36 | 13 / 46 | 9.3% (6.1-13.9) | 4.2% (2.2-7.7) | 100.0% (98.3-100.0) | 17.1% (12.7-22.7) | 216 |
| cybersecurity | both | 6 | 0 / 96 | 986 / 986 | 10.7% (8.7-13.1) | 10.7% (8.7-13.1) | 87.5% (85.0-89.7) | 87.5% (85.0-89.7) | 768 |
| cybersecurity | Inkling | 3 | 0 / 48 | 526 / 526 | 10.9% (8.2-14.5) | 10.9% (8.2-14.5) | 87.5% (83.8-90.4) | 87.5% (83.8-90.4) | 384 |
| cybersecurity | DeepSeek V4.1 Flash | 3 | 0 / 48 | 460 / 460 | 10.4% (7.7-13.9) | 10.4% (7.7-13.9) | 87.5% (83.8-90.4) | 87.5% (83.8-90.4) | 384 |
| finance | both | 6 | 36 / 48 | 12 / 49 | 32.8% (28.3-37.7) | 0.0% (0.0-1.0) | 100.0% (99.0-100.0) | 25.0% (20.9-29.6) | 384 |
| finance | Inkling | 3 | 22 / 24 | 2 / 24 | 29.2% (23.2-36.0) | 0.0% (0.0-2.0) | 100.0% (98.0-100.0) | 8.3% (5.2-13.1) | 192 |
| finance | DeepSeek V4.1 Flash | 3 | 14 / 24 | 10 / 25 | 36.5% (30.0-43.5) | 0.0% (0.0-2.0) | 100.0% (98.0-100.0) | 41.7% (34.9-48.7) | 192 |
| pooled | both | 18 | 103 / 216 | 1012 / 1130 | 18.9% (17.0-20.9) | 7.3% (6.1-8.6) | 92.5% (91.1-93.7) | 51.5% (49.0-53.9) | 1584 |

### Bounded event sourcing (9 of 9 paired runs complete)

At each update the event writer sees the compact previous typed state and the new block and emits event deltas; a deterministic reducer applies accepted deltas, and a failed update keeps the previous state. The paired baseline is the writer's own saved incremental typed memory from the same seed; both arms are answered by both executors. The event writer runs at the paper's protocol budget of 4,096 completion tokens.

| Domain | Writer | US typed incremental | US event-sourced | AU typed incremental | AU event-sourced | n per arm |
|---|---|---|---|---|---|---|
| procurement | both | 21.1% (17.5-25.2) | 2.8% (1.6-4.8) | 94.7% (92.1-96.4) | 94.2% (91.6-96.0) | 432 |
| procurement | Inkling | 32.9% (27.0-39.4) | 0.0% (0.0-1.7) | 89.4% (84.5-92.8) | 88.9% (84.0-92.4) | 216 |
| procurement | DeepSeek V4.1 Flash | 9.3% (6.1-13.9) | 5.6% (3.2-9.5) | 100.0% (98.3-100.0) | 99.5% (97.4-99.9) | 216 |
| cybersecurity | both | 10.7% (8.7-13.1) | 39.3% (35.9-42.8) | 87.5% (85.0-89.7) | 50.0% (46.5-53.5) | 768 |
| cybersecurity | Inkling | 10.9% (8.2-14.5) | 75.5% (71.0-79.6) | 87.5% (83.8-90.4) | 0.0% (0.0-1.0) | 384 |
| cybersecurity | DeepSeek V4.1 Flash | 10.4% (7.7-13.9) | 3.1% (1.8-5.4) | 87.5% (83.8-90.4) | 100.0% (99.0-100.0) | 384 |
| finance | both | 32.6% (28.1-37.4) | 0.0% (0.0-1.0) | 99.7% (98.5-100.0) | 37.5% (32.8-42.4) | 384 |
| finance | Inkling | 29.2% (23.2-36.0) | 0.0% (0.0-2.0) | 100.0% (98.0-100.0) | 8.3% (5.2-13.1) | 192 |
| finance | DeepSeek V4.1 Flash | 35.9% (29.5-42.9) | 0.0% (0.0-2.0) | 99.5% (97.1-99.9) | 66.7% (59.7-73.0) | 192 |
| pooled | both | 18.8% (17.0-20.8) | 19.8% (17.9-21.9) | 92.4% (91.0-93.6) | 59.0% (56.6-61.4) | 1584 |

Event-writer updates by outcome, and event-writer calls that used the full 4,096-token completion budget (a reasoning-in-completion writer is cut off there):

| Writer | accepted | structurally invalid | other | calls at the 4,096 cap |
|---|---|---|---|---|
| Inkling | 892 | 658 | 0 | 262 / 1552 |
| DeepSeek V4.1 Flash | 1097 | 90 | 0 | 0 / 1187 |


