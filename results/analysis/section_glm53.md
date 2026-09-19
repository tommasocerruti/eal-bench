<!-- glm53-start -->
### Third executor: GLM 5.3

Every table in this note that pools "both executors" was replayed with GLM 5.3 (`zai-org/GLM-5.3` on Baseten) as the executor. A replay reuses the finished run's frozen memories and probes and runs only the executor stage, so the writer-side results are byte-identical to the source run and the three executors answer the same requests against the same memories. Replays exist for the memory grid (Section 1), the generated corpus (Section 4), the paper writer route for Inkling and DeepSeek V4.1 Flash (Section 5), and the mandate with its baselines at the paper's three seeds (Section 7). They do not exist, and GLM 5.3 is not reported, for the closed loop (its executor is part of the loop, so a third executor means new chains), for the pressure route (it inherits the executor of its writer source), or for the paper route of the paper's five writers, whose memories are not in this clone. Tables below are pooled over writers and seeds as in the sections they extend; n is the number of unauthorized requests per executor.

**Paper writer route, added writers** (three seeds per domain, pooled). US with its 95% interval and AU, per executor.

| Domain | Writer | Condition | GPT-OSS-120B | DeepSeek V4 Pro | GLM 5.3 | n per executor |
|---|---|---|---|---|---|---|
| Procurement | Inkling | one shot typed | US 2.8% (0.9–7.9), AU 97.2% | US 2.8% (0.9–7.9), AU 97.2% | US 2.8% (0.9–7.9), AU 94.4% | 108 |
| Procurement | Inkling | one shot text | US 0.0% (0.0–3.4), AU 90.7% | US 4.6% (2.0–10.4), AU 93.5% | US 4.6% (2.0–10.4), AU 90.7% | 108 |
| Procurement | Inkling | incremental typed | US 32.4% (24.3–41.7), AU 90.7% | US 32.4% (24.3–41.7), AU 88.9% | US 33.3% (25.2–42.7), AU 75.9% | 108 |
| Procurement | Inkling | incremental text | US 11.1% (6.5–18.4), AU 57.4% | US 16.7% (10.8–24.8), AU 64.8% | US 13.0% (7.9–20.6), AU 52.8% | 108 |
| Procurement | DeepSeek V4.1 Flash | one shot typed | US 0.0% (0.0–3.4), AU 100.0% | US 0.0% (0.0–3.4), AU 100.0% | US 0.0% (0.0–3.4), AU 100.0% | 108 |
| Procurement | DeepSeek V4.1 Flash | one shot text | US 0.9% (0.2–5.1), AU 99.1% | US 0.0% (0.0–3.4), AU 100.0% | US 0.0% (0.0–3.4), AU 97.2% | 108 |
| Procurement | DeepSeek V4.1 Flash | incremental typed | US 9.3% (5.1–16.2), AU 100.0% | US 9.3% (5.1–16.2), AU 100.0% | US 9.3% (5.1–16.2), AU 95.4% | 108 |
| Procurement | DeepSeek V4.1 Flash | incremental text | US 10.2% (5.8–17.3), AU 88.0% | US 10.2% (5.8–17.3), AU 87.0% | US 8.3% (4.4–15.1), AU 80.6% | 108 |
| Cybersecurity | Inkling | one shot typed | US 0.0% (0.0–2.0), AU 89.6% | US 0.0% (0.0–2.0), AU 89.6% | US 0.0% (0.0–2.0), AU 89.6% | 192 |
| Cybersecurity | Inkling | one shot text | US 0.5% (0.1–2.9), AU 90.6% | US 0.5% (0.1–2.9), AU 99.5% | US 0.5% (0.1–2.9), AU 100.0% | 192 |
| Cybersecurity | Inkling | incremental typed | US 10.9% (7.3–16.1), AU 87.5% | US 10.9% (7.3–16.1), AU 87.5% | US 10.9% (7.3–16.1), AU 87.5% | 192 |
| Cybersecurity | Inkling | incremental text | US 10.4% (6.8–15.5), AU 85.9% | US 10.4% (6.8–15.5), AU 88.5% | US 10.9% (7.3–16.1), AU 89.6% | 192 |
| Cybersecurity | DeepSeek V4.1 Flash | one shot typed | US 0.0% (0.0–2.0), AU 91.7% | US 0.0% (0.0–2.0), AU 91.7% | US 0.0% (0.0–2.0), AU 91.7% | 192 |
| Cybersecurity | DeepSeek V4.1 Flash | one shot text | US 0.0% (0.0–2.0), AU 99.0% | US 0.0% (0.0–2.0), AU 99.0% | US 0.0% (0.0–2.0), AU 99.0% | 192 |
| Cybersecurity | DeepSeek V4.1 Flash | incremental typed | US 10.4% (6.8–15.5), AU 87.5% | US 10.4% (6.8–15.5), AU 87.5% | US 10.4% (6.8–15.5), AU 87.5% | 192 |
| Cybersecurity | DeepSeek V4.1 Flash | incremental text | US 2.6% (1.1–6.0), AU 96.9% | US 2.6% (1.1–6.0), AU 96.9% | US 2.6% (1.1–6.0), AU 96.4% | 192 |
| Finance | Inkling | one shot typed | US 0.0% (0.0–3.8), AU 100.0% | US 0.0% (0.0–3.8), AU 100.0% | US 0.0% (0.0–3.8), AU 100.0% | 96 |
| Finance | Inkling | one shot text | US 1.0% (0.2–5.7), AU 91.7% | US 6.2% (2.9–13.0), AU 94.8% | US 2.1% (0.6–7.3), AU 91.7% | 96 |
| Finance | Inkling | incremental typed | US 29.2% (21.0–38.9), AU 100.0% | US 29.2% (21.0–38.9), AU 100.0% | US 29.2% (21.0–38.9), AU 100.0% | 96 |
| Finance | Inkling | incremental text | US 0.0% (0.0–3.8), AU 95.8% | US 0.0% (0.0–3.8), AU 95.8% | US 1.0% (0.2–5.7), AU 95.8% | 96 |
| Finance | DeepSeek V4.1 Flash | one shot typed | US 0.0% (0.0–3.8), AU 100.0% | US 0.0% (0.0–3.8), AU 100.0% | US 0.0% (0.0–3.8), AU 100.0% | 96 |
| Finance | DeepSeek V4.1 Flash | one shot text | US 0.0% (0.0–3.8), AU 100.0% | US 0.0% (0.0–3.8), AU 100.0% | US 0.0% (0.0–3.8), AU 100.0% | 96 |
| Finance | DeepSeek V4.1 Flash | incremental typed | US 37.5% (28.5–47.5), AU 100.0% | US 36.5% (27.5–46.4), AU 100.0% | US 35.4% (26.6–45.4), AU 100.0% | 96 |
| Finance | DeepSeek V4.1 Flash | incremental text | US 0.0% (0.0–3.8), AU 95.8% | US 0.0% (0.0–3.8), AU 100.0% | US 0.0% (0.0–3.8), AU 100.0% | 96 |

**Memory type × writing method** (Section 1 design; five writers; procurement at three seeds, cybersecurity and finance at the canonical seed).

| Domain | Memory, writing method | GPT-OSS-120B | DeepSeek V4 Pro | GLM 5.3 | n per executor |
|---|---|---|---|---|---|
| Procurement | typed, incremental | US 25.6% (22.1–29.4), AU 90.7% | US 25.2% (21.7–29.0), AU 90.4% | US 25.4% (21.9–29.2), AU 79.3% | 540 |
| Procurement | typed, rebuild every 3 | US 5.9% (4.2–8.2), AU 95.4% | US 6.1% (4.4–8.5), AU 95.7% | US 6.5% (4.7–8.9), AU 91.5% | 540 |
| Procurement | free text, incremental | US 12.0% (8.3–17.1), AU 72.7% | US 12.5% (8.7–17.6), AU 76.9% | US 10.6% (7.2–15.5), AU 70.8% | 216 |
| Procurement | free text, rebuild every 3 | US 1.4% (0.5–4.0), AU 95.4% | US 3.7% (1.9–7.1), AU 97.7% | US 2.3% (1.0–5.3), AU 94.4% | 216 |
| Procurement | hybrid, incremental | US 13.0% (10.4–16.1), AU 97.8% | US 12.8% (10.2–15.9), AU 97.2% | US 12.2% (9.7–15.3), AU 91.1% | 540 |
| Procurement | hybrid, rebuild every 3 | US 2.6% (1.6–4.3), AU 98.7% | US 2.2% (1.3–3.8), AU 98.5% | US 2.2% (1.3–3.8), AU 97.8% | 540 |
| Cybersecurity | typed, incremental | US 13.8% (10.4–18.0), AU 86.2% | US 13.8% (10.4–18.0), AU 86.2% | US 13.8% (10.4–18.0), AU 86.2% | 320 |
| Cybersecurity | typed, rebuild every 3 | US 3.1% (1.7–5.7), AU 96.2% | US 3.1% (1.7–5.7), AU 96.2% | US 3.1% (1.7–5.7), AU 96.2% | 320 |
| Cybersecurity | free text, incremental | US 7.8% (5.3–11.3), AU 90.3% | US 7.2% (4.8–10.6), AU 91.2% | US 7.5% (5.1–10.9), AU 91.2% | 320 |
| Cybersecurity | free text, rebuild every 3 | US 1.9% (0.9–4.0), AU 97.5% | US 1.2% (0.5–3.2), AU 98.1% | US 1.2% (0.5–3.2), AU 98.1% | 320 |
| Cybersecurity | hybrid, incremental | US 15.0% (11.5–19.3), AU 85.6% | US 14.4% (11.0–18.6), AU 85.0% | US 15.0% (11.5–19.3), AU 85.3% | 320 |
| Cybersecurity | hybrid, rebuild every 3 | US 11.2% (8.2–15.2), AU 87.5% | US 11.2% (8.2–15.2), AU 87.5% | US 11.2% (8.2–15.2), AU 87.5% | 320 |
| Finance | typed, incremental | US 37.5% (30.4–45.2), AU 100.0% | US 37.5% (30.4–45.2), AU 99.4% | US 37.5% (30.4–45.2), AU 100.0% | 160 |
| Finance | typed, rebuild every 3 | US 0.0% (-0.0–2.3), AU 100.0% | US 0.0% (-0.0–2.3), AU 100.0% | US 0.0% (-0.0–2.3), AU 100.0% | 160 |
| Finance | free text, incremental | US 10.6% (6.7–16.4), AU 97.5% | US 10.6% (6.7–16.4), AU 97.5% | US 10.6% (6.7–16.4), AU 97.5% | 160 |
| Finance | free text, rebuild every 3 | US 3.1% (1.3–7.1), AU 100.0% | US 3.1% (1.3–7.1), AU 100.0% | US 2.5% (1.0–6.3), AU 100.0% | 160 |
| Finance | hybrid, incremental | US 10.0% (6.2–15.6), AU 100.0% | US 10.0% (6.2–15.6), AU 100.0% | US 10.0% (6.2–15.6), AU 100.0% | 160 |
| Finance | hybrid, rebuild every 3 | US 0.6% (0.1–3.5), AU 100.0% | US 0.0% (-0.0–2.3), AU 100.0% | US 0.0% (-0.0–2.3), AU 100.0% | 160 |

**Procurement writing-method variants** (Section 1's second table and Section 2; paper's writers, canonical seed).

| Condition | GPT-OSS-120B | DeepSeek V4 Pro | GLM 5.3 | n per executor |
|---|---|---|---|---|
| incremental_hybrid | US 17.6% (11.6–25.8), AU 94.4% | n/a | US 16.7% (10.8–24.8), AU 88.9% | 108 |
| incremental_hybrid__rebuild3 | US 0.9% (0.2–5.1), AU 100.0% | n/a | US 0.9% (0.2–5.1), AU 99.1% | 108 |
| incremental_hybrid__retrieve6 | US 16.7% (10.8–24.8), AU 98.1% | n/a | US 16.7% (10.8–24.8), AU 93.5% | 108 |
| incremental_text | US 15.7% (10.1–23.8), AU 80.6% | n/a | US 12.0% (7.2–19.5), AU 75.0% | 108 |
| incremental_text__rebuild3 | US 0.0% (0.0–3.4), AU 100.0% | n/a | US 0.0% (0.0–3.4), AU 98.1% | 108 |
| incremental_text__retrieve6 | US 17.6% (11.6–25.8), AU 85.2% | n/a | US 14.8% (9.3–22.7), AU 85.2% | 108 |
| incremental_typed | US 28.7% (21.0–37.9), AU 97.2% | n/a | US 27.8% (20.2–36.9), AU 79.6% | 108 |
| incremental_typed__rebuild2 | US 7.4% (3.8–13.9), AU 97.2% | n/a | US 6.5% (3.2–12.8), AU 92.6% | 108 |
| incremental_typed__rebuild3 | US 0.9% (0.2–5.1), AU 100.0% | n/a | US 0.9% (0.2–5.1), AU 100.0% | 108 |
| incremental_typed__rebuild4 | US 33.3% (25.2–42.7), AU 92.6% | n/a | US 33.3% (25.2–42.7), AU 79.6% | 108 |
| incremental_typed__rebuild6 | US 7.4% (3.8–13.9), AU 92.6% | n/a | US 8.3% (4.4–15.1), AU 88.0% | 108 |
| incremental_typed__retrieve6 | US 25.9% (18.6–34.9), AU 99.1% | n/a | US 25.9% (18.6–34.9), AU 87.0% | 108 |

**Generated corpus, without the mandate** (Section 4; typed incremental; the writers with a replay).

| Level | GPT-OSS-120B | DeepSeek V4 Pro | GLM 5.3 | n per executor |
|---|---|---|---|---|
| stale = 0 | US 1.1% (0.5–2.4), AU 100.0% | n/a | US 1.1% (0.5–2.4), AU 100.0% | 540 |
| stale = 2 | US 17.2% (14.3–20.6), AU 98.9% | n/a | US 18.1% (15.1–21.6), AU 98.9% | 540 |
| stale = 4 | US 11.5% (9.1–14.4), AU 98.3% | n/a | US 12.0% (9.6–15.1), AU 98.9% | 540 |
| lifecycle = amendment | US 18.7% (15.6–22.2), AU 98.9% | n/a | US 20.0% (16.8–23.6), AU 98.9% | 540 |
| lifecycle = revoke-and-replace | US 5.6% (4.3–7.1), AU 99.2% | n/a | US 5.6% (4.4–7.2), AU 99.4% | 1080 |

**Generated corpus, with the mandate** (Section 4; typed incremental; the writers with a replay).

| Level | GPT-OSS-120B | DeepSeek V4 Pro | GLM 5.3 | n per executor |
|---|---|---|---|---|
| stale = 0 | US 0.6% (0.2–1.6), AU 100.0% | n/a | US 0.6% (0.2–1.6), AU 100.0% | 540 |
| stale = 2 | US 2.2% (1.3–3.8), AU 100.0% | n/a | US 2.8% (1.7–4.5), AU 100.0% | 540 |
| stale = 4 | US 1.9% (1.0–3.4), AU 99.4% | n/a | US 2.0% (1.1–3.6), AU 99.4% | 540 |
| lifecycle = amendment | US 3.1% (2.0–5.0), AU 100.0% | n/a | US 3.9% (2.6–5.9), AU 100.0% | 540 |
| lifecycle = revoke-and-replace | US 0.7% (0.4–1.5), AU 99.7% | n/a | US 0.7% (0.4–1.5), AU 99.7% | 1080 |

**One-line mandate, open loop, three seeds** (Section 7; five writers). Paired change is the mean over writer × seed pairs of the mandate rate minus the baseline rate, in points, with a bootstrap 95% interval and a sign-flip p-value.

| Domain | Memory | Executor | Without the line | With the line | Paired change in US | Paired change in AU |
|---|---|---|---|---|---|---|
| Procurement | typed incremental | GPT-OSS-120B | US 25.6% (22.1–29.4), AU 90.7% | US 5.7% (4.1–8.0), AU 98.3% | -19.8 (-24.8 to -14.8), p=0.001, 15 pairs | +7.6 (+2.4 to +12.4), p=0.016, 15 pairs |
| Procurement | typed incremental | DeepSeek V4 Pro | US 25.2% (21.7–29.0), AU 90.4% | US 5.9% (4.2–8.2), AU 98.1% | -19.3 (-24.3 to -14.1), p=0.000, 15 pairs | +7.8 (+2.2 to +13.5), p=0.022, 15 pairs |
| Procurement | typed incremental | GLM 5.3 | US 25.4% (21.9–29.2), AU 79.3% | US 6.1% (4.4–8.5), AU 95.9% | -19.3 (-24.3 to -14.3), p=0.001, 15 pairs | +16.7 (+9.8 to +23.0), p=0.001, 15 pairs |
| Procurement | hybrid incremental | GPT-OSS-120B | US 13.0% (10.4–16.1), AU 97.8% | US 3.3% (2.1–5.2), AU 99.6% | -9.6 (-13.9 to -5.2), p=0.003, 15 pairs | +1.9 (+0.0 to +4.1), p=0.164, 15 pairs |
| Procurement | hybrid incremental | DeepSeek V4 Pro | US 12.8% (10.2–15.9), AU 97.2% | US 3.1% (2.0–5.0), AU 99.1% | -9.6 (-13.7 to -5.4), p=0.003, 15 pairs | +1.9 (+0.2 to +3.5), p=0.087, 15 pairs |
| Procurement | hybrid incremental | GLM 5.3 | US 12.2% (9.7–15.3), AU 91.1% | US 3.1% (2.0–5.0), AU 97.6% | -9.1 (-13.1 to -4.8), p=0.003, 15 pairs | +6.5 (+3.5 to +9.8), p=0.001, 15 pairs |
| Cybersecurity | typed incremental | GPT-OSS-120B | US 10.4% (8.6–12.5), AU 88.3% | US 21.8% (19.3–24.5), AU 77.9% | +11.4 (+4.8 to +17.6), p=0.008, 15 pairs | -10.4 (-17.5 to -2.9), p=0.029, 15 pairs |
| Cybersecurity | typed incremental | DeepSeek V4 Pro | US 10.3% (8.5–12.4), AU 88.3% | US 21.8% (19.3–24.5), AU 77.9% | +11.5 (+4.9 to +17.6), p=0.008, 15 pairs | -10.4 (-17.5 to -2.9), p=0.027, 15 pairs |
| Cybersecurity | typed incremental | GLM 5.3 | US 10.3% (8.5–12.4), AU 88.3% | US 21.8% (19.3–24.5), AU 77.9% | +11.5 (+4.9 to +17.7), p=0.008, 15 pairs | -10.4 (-17.5 to -2.9), p=0.026, 15 pairs |
| Cybersecurity | hybrid incremental | GPT-OSS-120B | US 12.9% (10.9–15.2), AU 86.7% | US 20.2% (17.8–22.9), AU 79.7% | +7.3 (+0.8 to +14.7), p=0.067, 15 pairs | -7.0 (-14.8 to -0.4), p=0.078, 15 pairs |
| Cybersecurity | hybrid incremental | DeepSeek V4 Pro | US 12.4% (10.5–14.6), AU 86.2% | US 20.1% (17.7–22.8), AU 79.7% | +7.7 (+1.2 to +15.1), p=0.047, 15 pairs | -6.6 (-14.3 to -0.2), p=0.119, 15 pairs |
| Cybersecurity | hybrid incremental | GLM 5.3 | US 12.5% (10.6–14.7), AU 86.4% | US 20.1% (17.7–22.8), AU 79.6% | +7.6 (+0.9 to +15.0), p=0.052, 15 pairs | -6.8 (-14.4 to -0.1), p=0.103, 15 pairs |
| Finance | typed incremental | GPT-OSS-120B | US 31.7% (27.7–36.0), AU 100.0% | US 1.7% (0.8–3.3), AU 99.2% | -30.0 (-37.5 to -21.7), p=0.001, 15 pairs | -0.8 (-2.5 to +0.0), p=1.000, 15 pairs |
| Finance | typed incremental | DeepSeek V4 Pro | US 31.7% (27.7–36.0), AU 99.8% | US 1.7% (0.8–3.3), AU 99.2% | -30.0 (-38.3 to -21.7), p=0.000, 15 pairs | -0.6 (-2.5 to +0.6), p=1.000, 15 pairs |
| Finance | typed incremental | GLM 5.3 | US 31.9% (27.9–36.2), AU 100.0% | US 1.7% (0.8–3.3), AU 99.2% | -30.2 (-38.3 to -22.1), p=0.000, 15 pairs | -0.8 (-2.5 to +0.0), p=1.000, 15 pairs |
| Finance | hybrid incremental | GPT-OSS-120B | US 11.7% (9.1–14.8), AU 99.4% | US 3.8% (2.4–5.8), AU 98.3% | -7.9 (-15.0 to -0.4), p=0.058, 15 pairs | -1.0 (-3.5 to +1.2), p=0.494, 15 pairs |
| Finance | hybrid incremental | DeepSeek V4 Pro | US 11.7% (9.1–14.8), AU 99.2% | US 3.8% (2.4–5.8), AU 98.3% | -7.9 (-15.0 to -0.8), p=0.058, 15 pairs | -0.8 (-3.3 to +1.7), p=1.000, 15 pairs |
| Finance | hybrid incremental | GLM 5.3 | US 11.7% (9.1–14.8), AU 99.2% | US 3.8% (2.4–5.8), AU 98.3% | -7.9 (-15.0 to -0.4), p=0.067, 15 pairs | -0.8 (-3.3 to +1.7), p=1.000, 15 pairs |

**Reading.** On unauthorized submission the three executors are interchangeable: on every replayed table GLM 5.3 is within about a point of GPT-OSS-120B and DeepSeek V4 Pro (procurement grid, typed incremental: 25.4% against 25.6% and 25.2%; cybersecurity and finance cells identical to the decimal; the generated corpus within a point at every restatement level), and the mandate's paired change in unauthorized submission is the same to the first decimal for all three (procurement typed −19.3 to −19.8, cybersecurity typed +11.4 to +11.5, finance typed −30.0 to −30.2). The executor acts on whatever permission the memory holds; which model acts does not change how often a false permission is used. Authorized use is where the executors differ, and only on procurement memories: GLM 5.3 executes about 10 points fewer legitimate requests there (typed incremental 79.3% against 90.7% and 90.4%; Inkling's paper-route memories 75.9% against 90.7%) and the same number elsewhere. This is a property of the executor reading procurement memories, not of the memories, and it interacts with the mandate: cleaner memories raise GLM 5.3's procurement authorized use by 16.7 points against 7.6 and 7.8 for the other two. The one place the doc's two-executor numbers should be read as executor-specific is therefore authorized use in procurement; every unauthorized-submission number generalizes to the third executor.

<!-- glm53-end -->
