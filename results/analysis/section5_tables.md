**Paper writer route.** Three seeds per domain, both executors, the paper's four conditions; AU and US with the Wilson interval on US and the number of unauthorized requests. GLM 5.3 ran procurement and cybersecurity only; the paper's own numbers for its three writers on this route are in the paper.

| Domain | Condition | Inkling | DeepSeek V4.1 Flash | GLM 5.3 |
|---|---|---|---|---|
| procurement | one-shot, typed | AU 97.2%, US 2.8% (1.3–5.9), n=216 | AU 100.0%, US 0.0% (0.0–1.7), n=216 | AU 97.2%, US 0.0% (0.0–1.7), n=216 |
| procurement | one-shot, free text | AU 92.1%, US 2.3% (1.0–5.3), n=216 | AU 99.5%, US 0.5% (0.1–2.6), n=216 | AU 99.5%, US 0.0% (0.0–1.7), n=216 |
| procurement | incremental, typed | AU 89.8%, US 32.4% (26.5–38.9), n=216 | AU 100.0%, US 9.3% (6.1–13.9), n=216 | AU 98.1%, US 20.4% (15.5–26.2), n=216 |
| procurement | incremental, free text | AU 61.1%, US 13.9% (9.9–19.1), n=216 | AU 87.5%, US 10.2% (6.8–14.9), n=216 | AU 96.8%, US 2.8% (1.3–5.9), n=216 |
| cybersecurity | one-shot, typed | AU 89.6%, US 0.0% (0.0–1.0), n=384 | AU 91.7%, US 0.0% (0.0–1.0), n=384 | AU 97.9%, US 0.0% (0.0–1.0), n=384 |
| cybersecurity | one-shot, free text | AU 95.1%, US 0.5% (0.1–1.9), n=384 | AU 99.0%, US 0.0% (0.0–1.0), n=384 | AU 100.0%, US 0.0% (0.0–1.0), n=384 |
| cybersecurity | incremental, typed | AU 87.5%, US 10.9% (8.2–14.5), n=384 | AU 87.5%, US 10.4% (7.7–13.9), n=384 | AU 99.7%, US 0.0% (0.0–1.0), n=384 |
| cybersecurity | incremental, free text | AU 87.2%, US 10.4% (7.7–13.9), n=384 | AU 96.9%, US 2.6% (1.4–4.7), n=384 | AU 97.9%, US 2.6% (1.4–4.7), n=384 |
| finance | one-shot, typed | AU 100.0%, US 0.0% (0.0–2.0), n=192 | AU 100.0%, US 0.0% (0.0–2.0), n=192 | n/a |
| finance | one-shot, free text | AU 93.2%, US 3.6% (1.8–7.3), n=192 | AU 100.0%, US 0.0% (0.0–2.0), n=192 | n/a |
| finance | incremental, typed | AU 100.0%, US 29.2% (23.2–36.0), n=192 | AU 100.0%, US 37.0% (30.5–44.0), n=192 | n/a |
| finance | incremental, free text | AU 95.8%, US 0.0% (0.0–2.0), n=192 | AU 97.9%, US 0.0% (0.0–2.0), n=192 | n/a |

Run sizes: Inkling procurement: 3 seeds, 1728 trials; DeepSeek V4.1 Flash procurement: 3 seeds, 1728 trials; GLM 5.3 procurement: 3 seeds, 1728 trials; Inkling cybersecurity: 3 seeds, 3072 trials; DeepSeek V4.1 Flash cybersecurity: 3 seeds, 3072 trials; GLM 5.3 cybersecurity: 3 seeds, 3072 trials; Inkling finance: 3 seeds, 1536 trials; DeepSeek V4.1 Flash finance: 3 seeds, 1536 trials.

**Memory type × writing method** (Section 1 design), both executors. Procurement at the paper's three seeds; cybersecurity and finance at the canonical seed. US per cell; the paper's three writers pooled from the same runs as Section 1.

*procurement*

| Memory, writing method | Inkling | DeepSeek V4.1 Flash | Paper's three writers |
|---|---|---|---|
| typed, incremental | AU 86.1%, US 37.0% (30.9–43.7), n=216 | AU 96.3%, US 14.4% (10.3–19.7), n=216 | AU 90.1%, US 25.2% (22.0–28.6), n=648 |
| typed, rebuild every 3 | AU 93.5%, US 9.3% (6.1–13.9), n=216 | AU 97.2%, US 0.9% (0.3–3.3), n=216 | AU 95.7%, US 6.6% (5.0–8.8), n=648 |
| hybrid, incremental | AU 97.7%, US 17.6% (13.1–23.2), n=216 | AU 99.5%, US 0.0% (0.0–1.7), n=216 | AU 96.8%, US 15.4% (12.9–18.4), n=648 |
| hybrid, rebuild every 3 | AU 97.2%, US 4.2% (2.2–7.7), n=216 | AU 99.5%, US 0.0% (0.0–1.7), n=216 | AU 98.8%, US 2.6% (1.6–4.2), n=648 |
| free text, incremental | AU 60.2%, US 12.5% (8.7–17.6), n=216 | AU 89.4%, US 12.0% (8.3–17.1), n=216 | n/a |
| free text, rebuild every 3 | AU 96.3%, US 3.2% (1.6–6.5), n=216 | AU 96.8%, US 1.9% (0.7–4.7), n=216 | n/a |

*cybersecurity*

| Memory, writing method | Inkling | DeepSeek V4.1 Flash | Paper's three writers |
|---|---|---|---|
| typed, incremental | AU 81.2%, US 18.8% (12.9–26.4), n=128 | AU 68.8%, US 31.2% (23.9–39.7), n=128 | AU 93.8%, US 6.2% (4.2–9.1), n=384 |
| typed, rebuild every 3 | AU 100.0%, US 0.0% (0.0–2.9), n=128 | AU 81.2%, US 15.6% (10.3–22.9), n=128 | AU 100.0%, US 0.0% (0.0–1.0), n=384 |
| hybrid, incremental | AU 37.5%, US 62.5% (53.9–70.4), n=128 | AU 93.8%, US 6.2% (3.2–11.8), n=128 | AU 98.4%, US 1.6% (0.7–3.4), n=384 |
| hybrid, rebuild every 3 | AU 62.5%, US 31.2% (23.9–39.7), n=128 | AU 87.5%, US 12.5% (7.8–19.3), n=128 | AU 95.8%, US 4.2% (2.6–6.7), n=384 |
| free text, incremental | AU 85.2%, US 10.9% (6.6–17.5), n=128 | AU 100.0%, US 0.0% (0.0–2.9), n=128 | AU 89.6%, US 8.9% (6.4–12.1), n=384 |
| free text, rebuild every 3 | AU 93.0%, US 7.8% (4.3–13.8), n=128 | AU 96.9%, US 0.0% (0.0–2.9), n=128 | AU 99.7%, US 0.0% (0.0–1.0), n=384 |

*finance*

| Memory, writing method | Inkling | DeepSeek V4.1 Flash | Paper's three writers |
|---|---|---|---|
| typed, incremental | AU 100.0%, US 37.5% (26.7–49.7), n=64 | AU 100.0%, US 50.0% (38.1–61.9), n=64 | AU 99.5%, US 33.3% (27.0–40.3), n=192 |
| typed, rebuild every 3 | AU 100.0%, US 0.0% (0.0–5.7), n=64 | AU 100.0%, US 0.0% (0.0–5.7), n=64 | AU 100.0%, US 0.0% (0.0–2.0), n=192 |
| hybrid, incremental | AU 100.0%, US 0.0% (0.0–5.7), n=64 | AU 100.0%, US 0.0% (0.0–5.7), n=64 | AU 100.0%, US 16.7% (12.1–22.6), n=192 |
| hybrid, rebuild every 3 | AU 100.0%, US 1.6% (0.3–8.3), n=64 | AU 100.0%, US 0.0% (0.0–5.7), n=64 | AU 100.0%, US 0.0% (0.0–2.0), n=192 |
| free text, incremental | AU 100.0%, US 25.0% (16.0–36.8), n=64 | AU 100.0%, US 0.0% (0.0–5.7), n=64 | AU 95.8%, US 9.4% (6.0–14.3), n=192 |
| free text, rebuild every 3 | AU 100.0%, US 0.0% (0.0–5.7), n=64 | AU 100.0%, US 0.0% (0.0–5.7), n=64 | AU 100.0%, US 5.2% (2.9–9.3), n=192 |

**Closed loop** (Section 3 design), all domains and both executors pooled, paired action minus neutral at round 3, from the same runs and script as Section 3.

| Writer | chains | US action | US neutral | paired diff | AU action | AU neutral | paired diff | born from write-backs, action / neutral |
|---|---|---|---|---|---|---|---|---|
| Inkling | 72 | 14.8% | 16.3% | -1.6 [-6.1, +2.5] p=0.514 | 78.8% | 87.9% | -10.9 [-18.5, -3.9] p=0.006 | 14 / 3 |
| DeepSeek V4.1 Flash | 72 | 16.3% | 12.5% | +3.9 [+1.6, +6.6] p=0.006 | 86.7% | 92.0% | -5.7 [-10.6, -1.0] p=0.032 | 20 / 0 |
| Paper's three writers | 216 | 22.2% | 19.6% | +2.9 [-0.1, +6.0] p=0.061 | 61.6% | 87.0% | -23.9 [-30.5, -17.5] p=0.000 | 93 / 1 |

**One-line mandate, open loop** (Section 7 design), typed incremental, both executors, per domain: US without → with the line.

| Writer | procurement | cybersecurity | finance |
|---|---|---|---|
| Inkling | 37.0% → 0.0% | 18.8% → 42.2% | 37.5% → 0.0% |
| DeepSeek V4.1 Flash | 14.4% → 0.0% | 31.2% → 17.2% | 50.0% → 0.0% |
| GLM 5.2 | 26.9% → 0.0% | 6.2% → 15.6% | 37.5% → 0.0% |
| Kimi K2.6 | 20.4% → 19.4% | 0.0% → 0.0% | 50.0% → 0.0% |
| Nemotron 3 Ultra | 28.2% → 13.9% | 12.5% → 25.0% | 12.5% → 0.0% |

