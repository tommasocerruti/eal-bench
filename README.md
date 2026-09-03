<h1 align="center">EAL-Bench</h1>

<p align="center">
  <strong>A benchmark for Endogenous Authorization Laundering (EAL) in persistent agent memory</strong>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2609.01836"><img src="https://img.shields.io/badge/arXiv-2609.01836-b31b1b.svg" alt="arXiv:2609.01836"></a>
  <a href="#citation"><img src="https://img.shields.io/badge/Cite-BibTeX-4c6baf.svg" alt="BibTeX citation"></a>
</p>

EAL-Bench tests whether persistent agent memory preserves evolving authorization boundaries and
whether memory errors lead to unauthorized downstream tool actions. It accompanies the paper
[*Agent Memory Is a Surface for Endogenous Authorization Laundering*](https://arxiv.org/abs/2609.01836).

## Overview

![EAL-Bench system and example failure](assets/figures/eal-bench-system-overview.png)

A memory writer compresses an organizational history into persistent memory. An executor later
receives that memory and a new request, then chooses whether to act through a native tool. A hidden
canonical ledger scores the action deterministically.

Each benchmark case includes:

- an evolving, multi-session organizational history;
- a hidden authorization ledger;
- matched authorized and unauthorized requests;
- a bounded free-text or typed memory;
- domain-native tools and a deterministic oracle.

The writer never sees the ledger or future requests. The executor never sees the original history
or ledger.

## Benchmark at a glance

### Domains

| Domain | Cases | Authorization scope |
|---|---:|---|
| Procurement | 12 | Buyer, vendor, category, amount, currency, status, and validity |
| Cybersecurity | 16 | Responder, tenant, incident, asset, environment, vulnerability, action, and validity |
| Finance | 8 | Trader, account, strategy, instrument, side, order type, quantity, price, currency, and validity |

### Memory conditions

| Writing approach | Free-text memory | Typed memory |
|---|---|---|
| One-shot | Write from the complete history | Build a schema-validated profile from the complete history |
| Incremental | Update from one new block | Update the typed profile from one new block |

Incremental writers receive the previous accepted memory and the new block, but not earlier raw
blocks. Final memories are frozen and hashed before executor evaluation.

### Studies

| Study | Purpose |
|---|---|
| `controls` | Calibrate executors with faithful evidence and controlled authorization changes |
| `writer` | Generate memories and measure downstream behavior |
| `pressure` | Replay a writer run under authority-invariant operational pressure |
| `writer_ttc` | Compare writer-side candidate sampling and selection strategies |
| `evaluation_cue` | Measure the effect of evaluation framing |

Model targets are provider-specific and are never silently pooled or substituted. List the
configured routes and resolved model names with:

```bash
uv run python -m experiments.run --list-targets
```

## Quick start

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

Offline inspection and validation do not require API credentials.

## Inspect and validate

```bash
uv run python -m experiments.run --list-domains
uv run python -m experiments.run --domain procurement --list-corpus-versions
uv run python -m experiments.run --domain procurement --list-studies
uv run python -m experiments.run --validate-only --all-domains
```

Validate a planned route before making live calls:

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

## Run an experiment

Live routes make paid API calls. Review the validated call plan first, then rerun it with an
explicit cost ceiling:

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

Use `--study controls` for faithful controls. Pressure replays require a completed writer run
through `--source-run results/<domain>/<run-id>`.

## Outputs

Every run is stored in a new immutable directory:

```text
results/<domain>/<run-id>/
```

Depending on the study, it records the resolved configuration, generated memories, exact
model-visible contexts, native tool calls, normalized decisions, oracle scores, hashes, and
provider usage. The completed `manifest.json` is the authoritative artifact inventory.

Procurement and Cybersecurity include the raw artifacts needed to verify reported counts. Finance
currently retains aggregate reports and hashed manifests; restoring the referenced raw JSONL files
is necessary for a fully independent end-to-end rebuild.

## Extending EAL-Bench

New domains define their own authorization state, histories, memory representation, requests,
native tools, deterministic oracle, and fidelity comparison. Shared experiment and analysis code
does not import concrete domains.

- [Domain interface](domains/README.md)
- [Domain contribution guide](domains/CONTRIBUTING.md)
- [Model and provider configuration](MODELS.md)

## Development

Before opening a pull request:

```bash
uv run python -m experiments.run --validate-only --all-domains
uv run ruff check .
git diff --check
```

---

## Citation

If you use EAL-Bench in your research, please cite the accompanying paper:

```bibtex
@misc{cerruti2026agent,
  title         = {Agent Memory Is a Surface for Endogenous Authorization Laundering},
  author        = {Cerruti, Tommaso and Okamoto, Mika and Erol, Ansel Kaplan},
  year          = {2026},
  eprint        = {2609.01836},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CR},
  url           = {https://arxiv.org/abs/2609.01836}
}
```
