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

## Results used in the paper

The complete design contains five writers, two executors, four memory conditions, and three
seeds. Each condition below pools 960 authorized and 960 unauthorized requests. The target-level
breakdown remains available in the frozen report; pooling here follows the paper's stated design.

| Memory condition | Authorized use | Unauthorized submission |
|---|---:|---:|
| Text, one-shot | 954/960 (99.4%) | 26/960 (2.7%) |
| Text, incremental | 908/960 (94.6%) | 296/960 (30.8%) |
| Typed, one-shot | 880/960 (91.7%) | 4/960 (0.4%) |
| Typed, incremental | 944/960 (98.3%) | 490/960 (51.0%) |

Unauthorized submission means the executor takes the **exact requested action** when the final
canonical state denies that request. It is different from the older broad `unsafe_action` metric.
Model-invalid and no-action outcomes remain in the denominators; provider failures are separate.

The overall unauthorized-submission rate is 816/3,840 (21.25%). GPT-OSS contributes 398/1,920 and
DeepSeek 418/1,920, with requested-action agreement on 3,802/3,840 paired replays. The primary
matrix contains no terminal provider-error trials.

Sources:

- [Final scientific report](../../results/finance_redesign/final_held_out_evaluation.md):
  120 ordinary cells, pressure cells, development history, controls, and causal analysis.
- [Frozen JSON report](../../results/finance_redesign/final_held_out_evaluation.json):
  machine-readable counts and provenance.
- [Paper Appendix B.2](https://arxiv.org/html/2609.01836v1#A2.SS2): Tables 11–13.
- [Reproduction and artifact guide](../../results/finance_redesign/README.md).

## Reproduce the saved tables offline

This command uses Python's standard library and makes no provider calls:

```bash
python3 -m analysis.finance_paper_results --output-dir /tmp/finance-paper-tables
```

It verifies the frozen sources, reports, and run manifests, sums the saved aggregate cells,
exports seed/condition/executor CSVs, and lists every expected raw artifact with its hash.
It does not reconstruct individual trials or independently repeat scoring from raw memory.

The 33 final run manifests survive, but their 378 referenced raw JSONL files were unavailable
when this correction was prepared. The original completion audit records their integrity at
execution time; it is not a claim that those files are currently distributed. Restoring those
exact files is necessary for trial-level reanalysis and independent scoring verification.

## Validate the dataset and planned routes

After installing the repository dependencies and caching the tokenizer data:

```bash
uv run python -m domains.finance.compile_corpus --check
uv run python -m experiments.run --validate-only --all-domains
uv run python -m experiments.run \
  --domain finance \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study writer \
  --writer-targets nemotron_3_ultra_baseten,kimi_baseten,glm_5_2_baseten,grok_4_3_openrouter,qwen_plus_0728_openrouter \
  --executor-targets gptoss_baseten,deepseek_baseten \
  --writer-architecture all --writer-strategy all \
  --seed 20260816 --validate-only
```

Repeat route validation with seeds `20260821` and `20260822` to inspect the complete design.
The frozen [final precommit](redesign_final_precommit.json) records all 33 routes, parameters,
and historical commands. Its old absolute worktree paths are provenance, not required locations.
New live runs require credentials and an explicit cost ceiling and create new stochastic samples;
they cannot replace the original raw artifacts or be expected to match published counts exactly.

## Earlier Finance results

The older `finance_v1` release also used the corpus name `benchmark_v1`, but it has a different
source hash (`ac495b4d26bf81240935ffabbfe68b25121a901414701fb53c2ba5bd04f2de42`). Its
`finance_v1__*` and `phase2_finance_replacement*` reports under `results/finance/` describe
superseded experiments, including the older 5.9% baseline unsafe-action figure. They are not the
paper's redesigned Finance results. Match release and source hashes, not just corpus names.

The [legacy archive declaration](archive/legacy_finance_v1/archive_manifest.json) preserves the
earlier construction's identity. Development corpora and reports are retained for provenance;
only `calibration_v1` and `benchmark_v1` are exposed by the active domain registry.
