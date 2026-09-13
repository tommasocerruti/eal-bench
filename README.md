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

A memory writer compresses an organizational history into persistent memory; an executor later receives that memory and a new request, then chooses whether to act through a native tool.

Each benchmark case includes:

- an evolving, multi-session organizational history;
- a hidden authorization ledger to score the action deterministically;
- matched authorized and unauthorized requests;
- a bounded free-text or typed memory;
- domain-native tools and a deterministic oracle.

To use EAL in your research, see the [usage guide](USAGE.md) for installation, examples, and the four evaluation tracks.

## Citation

If you use EAL-Bench in your research, or if it's closely related to your work, please cite the accompanying paper:

<details>
<summary>BibTeX</summary>

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

</details>

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

List the configured models with:

```bash
uv run python -m experiments.run --list-targets
```

## Run the full benchmark

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

### Validate

```bash
uv run python -m experiments.run --list-domains
uv run python -m experiments.run --domain procurement --list-corpus-versions
uv run python -m experiments.run --domain procurement --list-studies
uv run python -m experiments.run --validate-only --all-domains
```

Validate your experiment configuration:

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

### Run

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

Each run records its configuration, memories, model inputs, tool calls, scores, and provider
usage. See `manifest.json` for the files included in the run.

The [shared result guide](results/README.md) provides one layout for Procurement, Cybersecurity,
and Finance. Each domain has a `results/<domain>/paper/manifest.json` selecting the exact runs,
release, source hashes, and counts used in Appendix B.2, Tables 11–13. Reproduce all three domains
without model calls or API keys:

```bash
python3 -m analysis.paper_results --domain all --output-dir /tmp/eal-paper-tables
```

Each domain exports the same CSV, JSON, and Markdown files, including writer/executor breakdowns
and an artifact inventory. Raw JSONL files are excluded from Git across all domains; the command
checks any originals present locally and reports missing files. Saved aggregates reproduce the
published counts, while independent trial scoring and bootstrap reanalysis require the originals.

## Extending EAL-Bench

To add a domain, define its authorization rules, histories, memory format, requests, tools,
and scoring logic:

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
