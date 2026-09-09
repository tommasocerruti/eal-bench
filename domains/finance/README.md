# Finance domain

Finance studies authorization-memory failures in portfolio-order execution. A mandate must
jointly cover the trader, account, strategy, instrument, side, order type, quantity, price,
settlement currency, and half-open validity window.

The paper uses **`finance_redesign_v1`**, frozen after development iteration 14 and evaluated
on 22 August 2026. Its release declaration is [`release.json`](release.json).

| Component | Identity |
|---|---|
| Held-out corpus | `benchmark_v1`: 8 families, 32 authorized and 32 unauthorized requests |
| Calibration corpus | `calibration_v1` |
| Presentation | `naturalistic_v1` |
| Pressure profile | `loss_containment_v1` |
| Memory implementation | `langmem_profile` |
| Evaluation seeds | `20260816`, `20260821`, `20260822` |
| Corpus provenance SHA-256 | `e16f7342262b32188cff39e315c6041505195aceffea500d56a6a3e99a551966` |

The histories place an authoritative mandate contraction or revoke-and-replace before a later
operational OMS handoff from a non-issuer. The canonical ledger follows authoritative events;
operational records cannot restore the obsolete authority. Matched requests differ in one field.
Development families and the development seed are excluded from the final evaluation.

## Paper results

The [standard result package](../../results/finance/README.md) selects the paper's three-seed,
five-writer × two-executor experiment. It uses the shared manifest, count schema, and export
command available for all core domains:

```bash
python3 -m analysis.paper_results --domain finance --output-dir /tmp/eal-paper-tables
```

See that guide for published counts, provenance, and current raw-artifact availability.
The seed selection is `20260816`, `20260821`, `20260822`.

## Validate the dataset and planned routes

After installing the repository dependencies and caching the tokenizer data:

```bash
uv run python -m domains.finance.compile_corpus --check
uv run python -m experiments.run --validate-only --all-domains
```

Use the [shared writer command](../../results/README.md#run-a-new-experiment) with
`--domain finance` and each seed in the paper manifest to validate the full target matrix.
The frozen [final precommit](redesign_final_precommit.json) records all 33 routes, parameters,
and historical commands. Its old absolute worktree paths record provenance. New runs use the
current checkout and create new stochastic samples.

## Earlier Finance results

The older `finance_v1` release also used the corpus name `benchmark_v1`, but it has a different
source hash (`ac495b4d26bf81240935ffabbfe68b25121a901414701fb53c2ba5bd04f2de42`). Its
`finance_v1__*` and `phase2_finance_replacement*` reports under `results/finance/` describe
superseded experiments, including the older 5.9% baseline unsafe-action figure. They are not the
paper's redesigned Finance results. Match release and source hashes, not just corpus names.

The [legacy archive declaration](archive/legacy_finance_v1/archive_manifest.json) preserves the
earlier construction's identity. Development corpora and reports are retained for provenance;
only `calibration_v1` and `benchmark_v1` are exposed by the active domain registry.
