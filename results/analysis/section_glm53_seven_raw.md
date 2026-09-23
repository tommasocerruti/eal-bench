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

**Memory type × writing method** (Section 1 design; seven writers; procurement at three seeds, cybersecurity and finance at the canonical seed).

| Domain | Memory, writing method | GPT-OSS-120B | DeepSeek V4 Pro | GLM 5.3 | n per executor |
|---|---|---|---|---|---|
| Procurement | typed, incremental | US 25.8% (22.8–29.0), AU 93.1% | US 25.5% (22.6–28.8), AU 91.9% | US 25.7% (22.7–28.9), AU 80.6% | 756 |
| Procurement | typed, rebuild every 3 | US 5.6% (4.1–7.4), AU 96.6% | US 5.7% (4.2–7.6), AU 96.6% | US 6.0% (4.5–7.9), AU 92.9% | 756 |
| Procurement | free text, incremental | US 12.0% (8.3–17.1), AU 72.7% | US 12.5% (8.7–17.6), AU 76.9% | US 10.6% (7.2–15.5), AU 70.8% | 216 |
| Procurement | free text, rebuild every 3 | US 1.4% (0.5–4.0), AU 95.4% | US 3.7% (1.9–7.1), AU 97.7% | US 2.3% (1.0–5.3), AU 94.4% | 216 |
| Procurement | hybrid, incremental | US 14.0% (11.7–16.7), AU 97.5% | US 13.9% (11.6–16.5), AU 97.1% | US 13.4% (11.1–16.0), AU 90.1% | 756 |
| Procurement | hybrid, rebuild every 3 | US 3.0% (2.0–4.5), AU 98.5% | US 2.9% (1.9–4.4), AU 98.3% | US 2.8% (1.8–4.2), AU 97.1% | 756 |
| Cybersecurity | typed, incremental | US 12.5% (9.8–15.9), AU 86.6% | US 12.5% (9.8–15.9), AU 86.6% | US 12.5% (9.8–15.9), AU 86.6% | 448 |
| Cybersecurity | typed, rebuild every 3 | US 5.1% (3.4–7.6), AU 94.6% | US 5.1% (3.4–7.6), AU 94.6% | US 5.1% (3.4–7.6), AU 94.6% | 448 |
| Cybersecurity | free text, incremental | US 7.8% (5.3–11.3), AU 90.3% | US 7.2% (4.8–10.6), AU 91.2% | US 7.5% (5.1–10.9), AU 91.2% | 320 |
| Cybersecurity | free text, rebuild every 3 | US 1.9% (0.9–4.0), AU 97.5% | US 1.2% (0.5–3.2), AU 98.1% | US 1.2% (0.5–3.2), AU 98.1% | 320 |
| Cybersecurity | hybrid, incremental | US 15.8% (12.8–19.5), AU 83.5% | US 15.4% (12.4–19.0), AU 83.0% | US 15.8% (12.8–19.5), AU 83.3% | 448 |
| Cybersecurity | hybrid, rebuild every 3 | US 12.5% (9.8–15.9), AU 86.6% | US 12.5% (9.8–15.9), AU 86.6% | US 12.5% (9.8–15.9), AU 86.6% | 448 |
| Finance | typed, incremental | US 44.6% (38.3–51.2), AU 100.0% | US 44.6% (38.3–51.2), AU 99.6% | US 44.6% (38.3–51.2), AU 100.0% | 224 |
| Finance | typed, rebuild every 3 | US 0.0% (0.0–1.7), AU 100.0% | US 0.0% (0.0–1.7), AU 100.0% | US 0.0% (0.0–1.7), AU 100.0% | 224 |
| Finance | free text, incremental | US 10.6% (6.7–16.4), AU 97.5% | US 10.6% (6.7–16.4), AU 97.5% | US 10.6% (6.7–16.4), AU 97.5% | 160 |
| Finance | free text, rebuild every 3 | US 3.1% (1.3–7.1), AU 100.0% | US 3.1% (1.3–7.1), AU 100.0% | US 2.5% (1.0–6.3), AU 100.0% | 160 |
| Finance | hybrid, incremental | US 13.8% (9.9–19.0), AU 97.3% | US 13.8% (9.9–19.0), AU 96.9% | US 13.4% (9.5–18.5), AU 96.9% | 224 |
| Finance | hybrid, rebuild every 3 | US 1.3% (0.5–3.9), AU 98.2% | US 0.9% (0.2–3.2), AU 98.2% | US 0.9% (0.2–3.2), AU 98.2% | 224 |

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
| stale = 0 | US 0.8% (0.4–1.7), AU 99.2% | n/a | US 0.8% (0.4–1.7), AU 99.2% | 756 |
| stale = 2 | US 18.8% (16.2–21.7), AU 97.6% | n/a | US 19.7% (17.0–22.7), AU 97.6% | 756 |
| stale = 4 | US 14.7% (12.3–17.4), AU 98.0% | n/a | US 15.2% (12.8–17.9), AU 98.4% | 756 |
| lifecycle = amendment | US 19.3% (16.7–22.3), AU 98.8% | n/a | US 20.8% (18.0–23.8), AU 98.8% | 756 |
| lifecycle = revoke-and-replace | US 7.5% (6.3–8.9), AU 98.0% | n/a | US 7.5% (6.3–8.9), AU 98.2% | 1512 |

**Generated corpus, with the mandate** (Section 4; typed incremental; the writers with a replay).

| Level | GPT-OSS-120B | DeepSeek V4 Pro | GLM 5.3 | n per executor |
|---|---|---|---|---|
| stale = 0 | US 0.4% (0.1–1.2), AU 98.4% | n/a | US 0.4% (0.1–1.2), AU 98.4% | 756 |
| stale = 2 | US 4.2% (3.0–5.9), AU 98.1% | n/a | US 5.2% (3.8–7.0), AU 98.4% | 756 |
| stale = 4 | US 4.6% (3.3–6.4), AU 98.4% | n/a | US 4.8% (3.5–6.5), AU 98.4% | 756 |
| lifecycle = amendment | US 7.0% (5.4–9.1), AU 100.0% | n/a | US 8.1% (6.3–10.2), AU 100.0% | 756 |
| lifecycle = revoke-and-replace | US 1.1% (0.7–1.8), AU 97.5% | n/a | US 1.1% (0.7–1.8), AU 97.6% | 1512 |

**One-line mandate, open loop, three seeds** (Section 7; seven writers). Paired change is the mean over writer × seed pairs of the mandate rate minus the baseline rate, in points, with a bootstrap 95% interval and a sign-flip p-value.

| Domain | Memory | Executor | Without the line | With the line | Paired change in US | Paired change in AU |
|---|---|---|---|---|---|---|
| Procurement | typed incremental | GPT-OSS-120B | US 25.8% (22.8–29.0), AU 93.1% | US 8.5% (6.7–10.7), AU 98.7% | -17.3 (-21.8 to -12.8), p=0.000, 21 pairs | +5.6 (+1.7 to +9.4), p=0.014, 21 pairs |
| Procurement | typed incremental | DeepSeek V4 Pro | US 25.5% (22.6–28.8), AU 91.9% | US 8.5% (6.7–10.7), AU 98.4% | -17.1 (-21.4 to -12.6), p=0.000, 21 pairs | +6.5 (+2.5 to +10.8), p=0.007, 21 pairs |
| Procurement | typed incremental | GLM 5.3 | US 25.7% (22.7–28.9), AU 80.6% | US 8.7% (6.9–11.0), AU 95.0% | -16.9 (-21.4 to -12.3), p=0.000, 21 pairs | +14.4 (+9.3 to +19.7), p=0.000, 21 pairs |
| Procurement | hybrid incremental | GPT-OSS-120B | US 14.0% (11.7–16.7), AU 97.5% | US 5.4% (4.0–7.3), AU 99.5% | -8.6 (-12.4 to -4.8), p=0.001, 21 pairs | +2.0 (+0.3 to +3.8), p=0.065, 21 pairs |
| Procurement | hybrid incremental | DeepSeek V4 Pro | US 13.9% (11.6–16.5), AU 97.1% | US 5.0% (3.7–6.8), AU 99.2% | -8.9 (-12.4 to -5.3), p=0.001, 21 pairs | +2.1 (+0.7 to +3.8), p=0.028, 21 pairs |
| Procurement | hybrid incremental | GLM 5.3 | US 13.4% (11.1–16.0), AU 90.1% | US 5.0% (3.7–6.8), AU 96.7% | -8.3 (-11.9 to -4.8), p=0.001, 21 pairs | +6.6 (+4.2 to +9.3), p=0.000, 21 pairs |
| Cybersecurity | typed incremental | GPT-OSS-120B | US 12.3% (10.6–14.1), AU 86.8% | US 20.4% (18.3–22.6), AU 78.7% | +8.1 (+1.8 to +14.1), p=0.026, 21 pairs | -8.0 (-14.0 to -1.9), p=0.021, 21 pairs |
| Cybersecurity | typed incremental | DeepSeek V4 Pro | US 12.2% (10.6–14.1), AU 86.8% | US 20.4% (18.3–22.6), AU 78.7% | +8.2 (+2.0 to +14.1), p=0.021, 21 pairs | -8.0 (-14.1 to -1.9), p=0.028, 21 pairs |
| Cybersecurity | typed incremental | GLM 5.3 | US 12.2% (10.6–14.1), AU 86.8% | US 20.4% (18.3–22.6), AU 78.7% | +8.2 (+2.1 to +14.4), p=0.017, 21 pairs | -8.0 (-14.1 to -1.9), p=0.024, 21 pairs |
| Cybersecurity | hybrid incremental | GPT-OSS-120B | US 14.2% (12.4–16.2), AU 85.0% | US 22.3% (20.2–24.6), AU 77.6% | +8.1 (+3.4 to +13.5), p=0.005, 21 pairs | -7.4 (-12.9 to -2.4), p=0.008, 21 pairs |
| Cybersecurity | hybrid incremental | DeepSeek V4 Pro | US 13.8% (12.1–15.8), AU 84.7% | US 22.0% (19.9–24.3), AU 77.6% | +8.2 (+3.2 to +13.4), p=0.004, 21 pairs | -7.1 (-12.6 to -2.4), p=0.014, 21 pairs |
| Cybersecurity | hybrid incremental | GLM 5.3 | US 13.9% (12.2–15.9), AU 84.7% | US 22.0% (19.9–24.3), AU 77.5% | +8.1 (+3.3 to +13.5), p=0.005, 21 pairs | -7.2 (-12.6 to -2.4), p=0.010, 21 pairs |
| Finance | typed incremental | GPT-OSS-120B | US 42.9% (39.2–46.6), AU 100.0% | US 11.8% (9.5–14.4), AU 99.4% | -31.1 (-38.7 to -24.0), p=0.000, 21 pairs | -0.6 (-1.8 to +0.0), p=1.000, 21 pairs |
| Finance | typed incremental | DeepSeek V4 Pro | US 42.7% (39.0–46.5), AU 99.9% | US 11.8% (9.5–14.4), AU 99.4% | -31.0 (-38.4 to -23.5), p=0.000, 21 pairs | -0.4 (-1.8 to +0.4), p=1.000, 21 pairs |
| Finance | typed incremental | GLM 5.3 | US 43.0% (39.3–46.8), AU 100.0% | US 11.8% (9.5–14.4), AU 99.4% | -31.2 (-38.7 to -23.5), p=0.000, 21 pairs | -0.6 (-1.8 to +0.0), p=1.000, 21 pairs |
| Finance | hybrid incremental | GPT-OSS-120B | US 16.2% (13.6–19.2), AU 98.1% | US 11.3% (9.1–13.9), AU 97.6% | -4.9 (-11.8 to +2.7), p=0.209, 21 pairs | -0.4 (-3.1 to +2.5), p=0.816, 21 pairs |
| Finance | hybrid incremental | DeepSeek V4 Pro | US 16.2% (13.6–19.2), AU 97.8% | US 11.5% (9.3–14.1), AU 97.6% | -4.8 (-11.3 to +2.5), p=0.228, 21 pairs | -0.1 (-3.1 to +3.1), p=1.000, 21 pairs |
| Finance | hybrid incremental | GLM 5.3 | US 15.9% (13.4–18.9), AU 97.8% | US 11.5% (9.3–14.1), AU 97.6% | -4.5 (-11.6 to +3.3), p=0.282, 21 pairs | -0.1 (-3.0 to +3.1), p=1.000, 21 pairs |

**Reading.** On unauthorized submission the three executors are interchangeable: on every replayed table GLM 5.3 is within about a point of GPT-OSS-120B and DeepSeek V4 Pro (procurement grid, typed incremental: 25.4% against 25.6% and 25.2%; cybersecurity and finance cells identical to the decimal; the generated corpus within a point at every restatement level), and the mandate's paired change in unauthorized submission is the same to the first decimal for all three (procurement typed −19.3 to −19.8, cybersecurity typed +11.4 to +11.5, finance typed −30.0 to −30.2). The executor acts on whatever permission the memory holds; which model acts does not change how often a false permission is used. Authorized use is where the executors differ, and only on procurement memories: GLM 5.3 executes about 10 points fewer legitimate requests there (typed incremental 79.3% against 90.7% and 90.4%; Inkling's paper-route memories 75.9% against 90.7%) and the same number elsewhere. This is a property of the executor reading procurement memories, not of the memories, and it interacts with the mandate: cleaner memories raise GLM 5.3's procurement authorized use by 16.7 points against 7.6 and 7.8 for the other two. The one place the doc's two-executor numbers should be read as executor-specific is therefore authorized use in procurement; every unauthorized-submission number generalizes to the third executor.

<!-- glm53-end -->
