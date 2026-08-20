# EAL-Bench

**A benchmark for Endogenous Authorization Laundering (EAL) in persistent agent memory**

EAL-Bench accompanies the paper *Agent Memory Is a Surface for Endogenous Authorization
Laundering*.

**Paper:** coming soon

Persistent memory can carry authorization state. When it stores permissions, restrictions, and
revocations, errors in that memory can change what an agent believes it is allowed to do.
EAL-Bench tests what happens when a memory-writing agent turns an authentic organizational
history into an inaccurate persistent representation, and a downstream executor treats that
representation as its basis for action.

## What is endogenous authorization laundering?

Suppose an organization approves a purchase from one vendor, for one category, below a fixed
amount, and before a deadline. A memory writer later turns the surrounding history into persistent
memory. If it drops the amount limit, retains a revoked approval, merges two records, or broadens
the category, the stored memory now grants authority that the underlying history does not.

A downstream executor can then follow the memory faithfully and still perform an unauthorized
action. We call this **endogenous authorization laundering** because the apparent authority is
created inside the agent system during ordinary memory formation or updating. The threat model
does not require prompt injection, forged approvals, malicious users, poisoned tools, or any
other external attacker.

Memory errors can also remove legitimate authority. EAL-Bench therefore measures both sides of
the failure:

- **Authorized use:** the executor takes the exact requested action when it is authorized.
- **Unauthorized submission:** the executor takes the exact requested action when it is not
  authorized.
- **Undergrant:** the executor fails to take an authorized requested action.

## Key results

- Selected natural memory errors lead to unauthorized actions in **150/152 (98.7%)** replays;
  replacing only the memory with oracle-exact state reduces this to **0/152**.
- Across ordinary generated memories, unauthorized submission reaches **13.1%** in Procurement,
  **3.8%** in Cybersecurity, and **5.9%** in Finance, while authorized use falls as low as
  **37.5%**.
- More writer-side inference compute reduces Procurement unauthorized submission from **13.2% to
  8.6%**, but at $k=8$ an exact memory exists in **55.0%** of candidate pools while self-review
  selects one in only **26.7%**.

## Benchmark protocol

![EAL-Bench system and example failure](assets/figures/eal-bench-system-overview.png)

*Figure 1. A writer creates persistent memory from an evolving history, and an executor uses that
memory with a later request to choose a tool action. The hidden canonical ledger evaluates the
action deterministically. In this example, memory absorbs a stale, non-authoritative category and
makes an unauthorized request appear valid.*

Each case contains a multi-session organizational history, a hidden canonical authorization
ledger, and matched authorized and unauthorized requests. The writer sees the history but never
the ledger, future requests, or expected outcomes. The executor receives the frozen memory and a
new request, but not the original history or ledger. It must act, escalate, or decline through
domain-native tools, after which a deterministic oracle scores the terminal action.

For typed memory, EAL-Bench can deterministically identify two distinct stages:

1. **Formation:** memory makes a canonically denied action appear authorized.
2. **Propagation:** the executor acts on that false authority.

Free-text memory has no deterministic representation-level authorization predicate, so it is
evaluated behaviorally and through matched memory-only interventions rather than assigned
deterministic formation labels.

Faithful-memory controls first establish that both executors can solve the downstream task when
the authorization evidence is correct. Memory-only interventions then hold the request, executor,
tools, and canonical state fixed while changing only the stored memory.

## Domains

All three core domains use the same writer-memory-executor protocol while defining their own
authorization state, histories, tools, requests, and deterministic oracle.

| Domain | Cases | History | Matched request pairs | Authorization scope |
|---|---:|---:|---:|---|
| Procurement | 12 | 65–84 turns, 5–6 blocks | 36 | Buyer, vendor, category, amount, currency, status, and validity |
| Cybersecurity | 16 | 120 turns, 10 blocks | 64 | Responder, tenant, incident, asset, environment, vulnerability, action, and validity |
| Finance | 8 | 192 turns, 16 blocks | 32 | Trader, account, strategy, instrument, side, order type, quantity, price, currency, and validity |

One active authorization record must cover the complete requested action. Fields cannot be
assembled from multiple records, and validity is evaluated at the requested action time. The
frozen `benchmark_v1` corpora use the `naturalistic_v1` presentation.

## Memory conditions

The benchmark uses LangMem's profile-oriented memory manager and evaluates a 2×2 design:

| Writing approach | Free-text memory | Typed memory |
|---|---|---|
| One-shot | Write a text memory from the complete history | Build a schema-validated profile from the complete history |
| Incremental | Update the previous text memory from one new block | Update the typed profile from the previous state and one new block |

Incremental writers never receive earlier raw blocks again. Each chain uses one persistent
profile, and its final memory is frozen and hashed before executor evaluation. Capacity is fixed
before evaluation at twice the largest faithful calibration payload. A Procurement ablation found
only modest, inconclusive changes when the explicit capacity constraint was relaxed, so tight
explicit memory limits are unlikely to be the primary cause of the observed failures.

## Models

The paper evaluates a **five-writer × two-executor** transfer matrix. Each generated memory
artifact is frozen and replayed behind both executors.

| Model | Target | Provider | Role |
|---|---|---|---|
| Nemotron 3 Ultra | `nemotron_3_ultra_baseten` | Baseten | Writer |
| Kimi K2.6 | `kimi_baseten` | Baseten | Writer |
| GLM 5.2 | `glm_5_2_baseten` | Baseten | Writer |
| Grok 4.3 | `grok_4_3_openrouter` | OpenRouter | Writer |
| Qwen Plus 2025-07-28 | `qwen_plus_0728_openrouter` | OpenRouter | Writer |
| GPT-OSS-120B | `gptoss_baseten` | Baseten | Executor |
| DeepSeek V4 Pro | `deepseek_baseten` | Baseten | Executor |

Model targets are provider-specific experimental treatments. The runner never silently pools or
substitutes providers or targets. Other configured routes are development or fallback targets and
are not part of the paper's primary matrix. All paper runs use temperature 1.0 and a 4,096-token
output limit; every writer passed the LangMem qualification checks before entering the matrix.

List the currently configured routes and resolved model names with:

```bash
uv run python -m experiments.run --list-targets
```

## Studies

| Study | Purpose |
|---|---|
| `controls` | Calibrate executors with faithful evidence and controlled authorization changes |
| `writer` | Generate ordinary memories and measure their downstream behavior |
| `pressure` | Replay a completed writer run under authority-invariant operational pressure |
| `writer_ttc` | Scale writer-side candidate sampling and compare selection strategies |
| `evaluation_cue` | Measure the effect of generic and authorization-specific evaluation framing |

Procurement also includes the capacity ablations and `evaluation_awareness` validity tooling. Use
`--list-studies` for the routes implemented by a particular domain.

## Installation

Requirements:

- Python 3.10 or newer;
- [`uv`](https://docs.astral.sh/uv/);
- a Baseten or OpenRouter API key for live experiments.

```bash
git clone git@github.com:tommasocerruti/eal-bench.git
cd eal-bench

uv sync --extra dev --extra analysis
cp .env.example .env
```

Add credentials only for the providers you intend to call:

```dotenv
BASETEN_API_KEY=...
OPENROUTER_API_KEY=...
```

Offline inspection and validation do not require API credentials or contact a model provider.

## Inspect and validate the benchmark

```bash
uv run python -m experiments.run --list-domains
uv run python -m experiments.run --domain procurement --list-corpus-versions
uv run python -m experiments.run --domain procurement --list-studies
uv run python -m experiments.run --list-targets
```

Validate every registered domain offline:

```bash
uv run python -m experiments.run --validate-only --all-domains
```

Or validate one planned route and inspect its frozen call plan:

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study writer \
  --writer-targets nemotron_3_ultra_baseten \
  --executor-targets gptoss_baseten \
  --writer-architecture all \
  --writer-strategy all \
  --validate-only
```

## Run the benchmark

Live routes make paid API calls. Always run the same command with `--validate-only` first, review
the call plan and expected cost, then replace it with an explicit `--estimated-cost-usd` ceiling.

### Faithful controls

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study controls \
  --executor-targets gptoss_baseten \
  --estimated-cost-usd <reviewed-total-ceiling> \
  --tag benchmark-v1-controls
```

### Writer-generated memory

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study writer \
  --writer-targets nemotron_3_ultra_baseten \
  --executor-targets gptoss_baseten \
  --writer-architecture all \
  --writer-strategy all \
  --estimated-cost-usd <reviewed-total-ceiling> \
  --tag benchmark-v1-writer
```

### Pressure replay

Pressure inherits the frozen writer and executor routes from its source run. It does not regenerate
memories or accept new writer or executor targets.

```bash
uv run python -m experiments.run \
  --domain procurement \
  --study pressure \
  --source-run results/procurement/<completed-writer-run> \
  --estimated-cost-usd <reviewed-total-ceiling> \
  --tag benchmark-v1-pressure
```

Interrupted executor-only routes can be resumed without resampling completed calls. Repeat the
original route arguments with `--resume-run` and the offline-verified
`--expected-missing-calls`; validate the resume plan before making live calls.

## Outputs and reproducibility

Every run is stored in a new immutable directory:

```text
results/<domain>/<run-id>/
```

Depending on the study, the directory records:

- the resolved configuration, presentation, model targets, and generation parameters;
- generated memories, update histories, attempts, and lineage;
- exact model-visible messages, tools, and tool choice;
- native tool calls and normalized executor decisions;
- hidden-oracle scores and semantic evidence;
- source, configuration, context, and artifact hashes;
- provider usage, cost metadata, and call provenance.

The completed `manifest.json` is the authoritative inventory for a run. Historical results are
immutable and loaded through hash-aware analysis utilities.

Procurement and Cybersecurity retain the raw artifacts needed to verify the reported counts. The
current checkout retains Finance's aggregate reports and hashed manifests, but the raw JSONL files
referenced by its final writer, pressure, and executor-control manifests are missing. The completed
matrix, passed controls, exact-repair reversal, and release-equivalence audit support the reported
Finance results, but restoring those raw files is necessary for a fully independent end-to-end
rebuild.

## Scope and limitations

EAL-Bench preserves the structure of a persistent agent workflow without claiming to reproduce a
deployment or estimate real-world prevalence. Its histories are synthetic, ordered, complete, and
more regular than workplace communication. Authorization is explicit and closed-world; executors
receive the complete stored memory; tools are scored functions rather than live integrations; and
the deterministic oracles omit ambiguity, concurrency, external side effects, and recovery.

The primary matrix uses one frozen generation seed. Requests and executor replays sharing a memory
are correlated, and agreement between two executors does not establish universal behavior.
Deterministic semantic analysis applies only to typed memory. These constraints make the benchmark
suited to isolating the memory-mediated mechanism, not to measuring end-to-end deployment safety.

## Extending EAL-Bench

Adding a model served by an existing provider normally requires one target entry in `config.yaml`.
Adding a domain requires domain-native authorization events and scope, conversation replay,
memory representation, requests, tools, an authorization oracle, and fidelity comparison. The
shared runner and analysis infrastructure must not import concrete domains.

See:

- [`domains/CONTRIBUTING.md`](domains/CONTRIBUTING.md) for benchmark-design standards;
- [`domains/README.md`](domains/README.md) for the domain interface;
- [`MODELS.md`](MODELS.md) for model and provider configuration.

## Repository structure

| Path | Purpose |
|---|---|
| `domains/` | Domain semantics, corpora, tools, and deterministic authorization oracles |
| `experiments/authorization_memory/` | Shared LangMem, execution, persistence, and validation pipeline |
| `experiments/run.py` | Canonical benchmark CLI |
| `analysis/` | Behavioral, fidelity, pressure, intervention, and validity analyses |
| `src/eal_bench/llm/` | Provider-aware model routing, limits, retries, batching, and call logging |
| `config.yaml` | Providers, model targets, tasks, and generation parameters |
| `results/` | Saved experiment artifacts and aggregate reports |

## Development

Before opening a pull request:

```bash
uv run python -m experiments.run --validate-only --all-domains
uv run ruff check .
git diff --check
```

Do not create benchmark results with ad hoc model calls. Use `python -m experiments.run` from the
repository root so configuration, contexts, model provenance, costs, and outputs are recorded
consistently.

## Contribute to EAL-Bench v2

We are actively looking for new domains to integrate into a second version of EAL-Bench. We are
especially interested in domains that introduce authorization structures or lifecycle events not
already covered by Procurement, Cybersecurity, and Finance.

New domains should include their own histories, authorization state, memory representation,
requests, native tools, deterministic oracle, and offline validation. Start with
[`domains/CONTRIBUTING.md`](domains/CONTRIBUTING.md), then open an issue describing the proposed
domain and the distinct failure modes it would add before investing in a full implementation.

Important correctness and reproducibility fixes are also very welcome. Substantial contributions
will be credited appropriately in the repository and future releases.
