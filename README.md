# EAL-Bench

**The Endogenous Authorization Laundering (EAL) Benchmark**

EAL-Bench evaluates whether errors introduced during agent-memory construction can broaden apparent authorization and cause unauthorized downstream tool actions. It is the benchmark accompanying the research project:

[**Agent Memory Is a Surface for Endogenous Authorization Laundering**](TODO:add_link)

## What is endogenous authorization laundering?

An organization may grant a limited permission (e.g., an approval to purchase from one vendor, within a spending limit, and before a particular date) within a longer organizational history corpus.

A memory-writer agent compresses the organizational history into persistent memory, and, during this process, it may omit a restriction, retain expired information, merge identities, or broaden the original scope. A downstream executor agent may then treat that inaccurate memory as legitimate authority and act on it, performing an unauthorized transaction.

We call this **endogenous authorization laundering** because the apparent authorization is produced inside the agent system, without external adversarial attacks like prompt injections.

## Benchmark workflow

EAL-Bench evaluates a sequential, memory-mediated and tool-augmented multi-agent system:

TODO: Draw diagram.
```text
organizational history
        │
        ▼
memory-writer agent ──> bounded persistent memory
                                  │
later request ────────────────────┤
                                  ▼
                         executor agent ──> tool action
                                  │
                                  ▼
                    deterministic authorization check
```

Each benchmark case contains:

- a long, synthetic organizational conversation;
- hidden ground-truth authorization state;
- authorization changes such as approvals, amendments, expiry, and revocation;
- matched authorized and unauthorized requests;
- native tools through which the executor must act.

The models never see the hidden authorization state or expected outcome.

## Research questions

EAL-Bench studies:

1. Which authorization boundaries and memory operations are most vulnerable to drift?
2. Which memory architectures preserve authorization without unnecessarily blocking legitimate work?
3. Do naturally occurring memory errors cause unauthorized tool actions?
4. How do failures transfer across writer-executor model pairs?
5. When authorization evidence is incomplete or conflicting, does the executor escalate or proceed?

## Experimental routes

The benchmark exposes three primary routes.

| Route | Question |
|---|---|
| `controls` | Does the executor behave correctly with faithful evidence, and respond predictably to controlled authorization broadening? |
| `writer` | Do errors produced naturally by the memory-writer agent propagate into downstream decisions? |
| `pressure` | Do operational incentives such as cost, delivery, and quality make the executor more likely to act on a writer-generated authorization error? |

The pressure route reuses the exact memories and requests frozen by a completed writer run, and changes only the executor’s operational context (i.e., it does not regenerate memories or select new examples after observing results).

An auxiliary `evaluation_awareness` study estimates whether model-visible contexts appear more like benchmark evaluations than deployment-like controls. This is treated as a validity analysis, not as the main research question.

## Models

The current transfer study uses a **5 writer × 2 executor** matrix. The five writers generate each
memory once, and the same memory is then evaluated by both executors.

| Model | Target | Provider | Transfer-matrix role |
|---|---|---|---|
| GPT-OSS-120B | `gptoss_baseten` | Baseten | Executor |
| DeepSeek V4 Pro | `deepseek_baseten` | Baseten | Executor |
| Nemotron 3 Ultra | `nemotron_3_ultra_baseten` | Baseten | Writer |
| Kimi K2.6 | `kimi_baseten` | Baseten | Writer |
| GLM 5.2 | `glm_5_2_baseten` | Baseten | Writer |
| Grok 4.3 | `grok_4_3_openrouter` | OpenRouter | Writer |
| Qwen Plus 2025-07-28 | `qwen_plus_0728_openrouter` | OpenRouter | Writer |

GPT-OSS and DeepSeek are executors only in this transfer matrix. The separate domain merge gate
uses the canonical GPT-OSS writer → GPT-OSS executor route to establish task difficulty.

Targets are provider-specific treatments and are never substituted or pooled silently.
`gptoss_openrouter` is an explicit fallback/test route, not a replacement for the canonical
Baseten target. Mistral Medium 3 remains configured but is excluded from pooled writer results
because of severe transport timeouts; the remaining configured legacy targets are not part of the
current paper roster.

List every configured target and its capabilities with:

```bash
uv run python -m experiments.run --list-targets
```

## Domains

Procurement is the validated frozen core domain. Cybersecurity remains frozen as a historical
release, but a corrected generated-profile viability audit found that its one-shot writer chains
did not all create usable profiles, so its behavioral rates are currently diagnostic rather than
claim-eligible. Procurement studies bounded
purchase approvals across vendor, category, amount, currency, validity, and supersession.
Cybersecurity studies incident-response grants across assets, tenants, environments, actions,
vulnerabilities, and response windows.

Finance is registered as a frozen core domain. Its `finance_v1` release studies portfolio-order
mandates across trader, account, strategy, instrument, side, order type, quantity, price,
settlement currency, and time. Its five-writer × two-executor transfer matrix is complete:
unauthorized submission rose from 5.9% at baseline to 10.1% under pressure, while exact repair
eliminated 24/24 selected natural-error failures. The completed matrix, passed isolation controls,
and release-equivalence audit are accepted as a claim-valid, merge-eligible Finance release.

The repository is designed so each domain defines its own authorization scope, events, requests,
tools, and oracle without modifying the shared experiment runner or analysis infrastructure.

Procurement's authorization scope includes:

- vendor identity;
- product category;
- spending limit and currency;
- validity interval;
- approval status and supersession.


## Memory conditions

EAL-Bench uses LangMem as the active memory implementation and evaluates a 2×2 design:

| Writing mode | Free-text memory | Typed memory |
|---|---:|---:|
| One shot | Full history compressed into bounded prose | Full history compressed into a structured profile |
| Incremental | Memory updated after each conversation block | Structured profile updated after each block |

Memory capacity is calibrated and frozen before evaluation. Incremental writers receive only the new conversation block and the previously accepted memory state.

## Setup

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

Add the providers you intend to use:

```dotenv
BASETEN_API_KEY=...
OPENROUTER_API_KEY=...
```

Baseten is the default experimental provider.

## Inspect the benchmark

```bash
uv run python -m experiments.run --list-domains
uv run python -m experiments.run \
  --domain procurement \
  --list-corpus-versions
uv run python -m experiments.run \
  --domain procurement \
  --list-studies
uv run python -m experiments.run --list-targets
```

## Offline validation

Validation does not contact a model provider:

```bash
uv run python -m experiments.run \
  --validate-only \
  --all-domains
```

Validate a particular route:

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study writer \
  --validate-only
```

## Run the benchmark

Live commands make paid API calls, and the runner displays the projected call count before execution.

### 1. Controls

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study controls \
  --executor-targets gptoss_baseten \
  --tag benchmark-v1-controls
```

### Resume an interrupted executor-only route

An interrupted executor-only route can be continued without resampling completed calls. Repeat
the original route arguments, add `--resume-run` and the offline-verified
`--expected-missing-calls`, and run `--validate-only` first. Resume rejects mismatched manifests,
routes, prompts, parameters, seeds, or call identities and sends only absent frozen call IDs.

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study controls \
  --executor-targets gptoss_baseten \
  --resume-run results/procurement/<interrupted-controls-run> \
  --expected-missing-calls <offline-verified-count> \
  --estimated-cost-usd <total-run-ceiling> \
  --validate-only
```

Remove `--validate-only` only after reviewing the resume plan and total-run cost ceiling.

### 2. Writer-generated memory

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study writer \
  --writer-targets gptoss_baseten \
  --executor-targets gptoss_baseten \
  --writer-architecture all \
  --writer-strategy all \
  --tag benchmark-v1-writer
```

### 3. Pressure on writer-generated memory

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study pressure \
  --source-run results/procurement/<completed-writer-run> \
  --tag benchmark-v1-pressure
```

## Outputs

Each run receives a new, immutable directory under:

```text
results/<domain>/<run-id>/
```

Depending on the route, it records:

- the resolved configuration and model targets;
- generated memories and their update history;
- exact model-visible writer and executor contexts;
- native tool calls and normalized decisions;
- hidden-oracle scores;
- source, configuration, and artifact hashes;
- provider usage and call provenance.

The completed `manifest.json` is the authoritative inventory for a run.

## Adding models and domains

Adding a model served by an existing provider normally requires only a new target entry in `config.yaml`.

Adding a domain requires implementing its:

- authorization events and scope;
- conversation corpus and replay semantics;
- memory representation;
- requests and native tools;
- deterministic authorization oracle;
- fidelity comparison.

The shared runner, persistence layer, and analyses must not import a concrete domain.

See:

- [`domains/CONTRIBUTING.md`](domains/CONTRIBUTING.md) for benchmark-design standards;
- [`domains/README.md`](domains/README.md) for the domain interface;
- [`MODELS.md`](MODELS.md) for model and provider configuration.

## Repository structure

| Path | Purpose |
|---|---|
| `domains/` | Domain semantics, corpora, tools, and authorization oracles |
| `experiments/authorization_memory/` | Shared LangMem and experiment pipeline |
| `experiments/run.py` | Canonical benchmark CLI |
| `analysis/` | Behavioral, fidelity, pressure, and validity analyses |
| `src/eal_bench/llm/` | Provider-aware model routing and call logging |
| `config.yaml` | Providers, model targets, and generation parameters |
| `results/` | Saved experiment artifacts |

## Development

Before opening a pull request:

```bash
uv run python -m experiments.run --validate-only --all-domains
uv run ruff check .
git diff --check
```

Do not create benchmark results with ad hoc model calls. Use `experiments.run` so that configuration, contexts, model provenance, and outputs are recorded consistently.

## Citation

TODO: Add future citation
