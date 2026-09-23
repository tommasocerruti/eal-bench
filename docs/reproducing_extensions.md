# Reproducing the extension studies

For a short introduction to the studies and folder layout, see the
[extensions overview](extensions.md).

The canonical runner now exposes `writer_variants` and `closed_loop`. These are aliases
for the original engines: prompts, update schedules, seeds, scoring and selection rules
are unchanged. The earlier module entry points remain available. Run from the repository
root after `uv sync --frozen --extra dev --extra analysis`.

## Offline validation and new runs

These commands only plan and validate; they make no model calls:

```bash
uv run python -m experiments.run --list-studies
uv run python -m experiments.run --study writer_variants \
  --domain procurement --corpus-version benchmark_v1 \
  --memory-types typed,free_text,hybrid \
  --writing-methods incremental,rebuild:3,retrieve:6 \
  --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten \
  --seed 20260719 --validate-only
uv run python -m experiments.run --study closed_loop \
  --domain procurement --conditions incremental_typed \
  --writer-targets glm_5_2_baseten --executor-targets gptoss_baseten \
  --rounds 3 --loop-content both --seed 20260719 --validate-only
```

Use `--study <route> --help` for the route's complete options. Extension routes validate
one domain per invocation; `--all-domains` remains the core validator's option.
For a paid run, remove `--validate-only`, provide credentials and an explicit
`--estimated-cost-usd`, and set a distinct `--tag`. The examples above demonstrate the
interface; they do not replace the original study-specific recipes.

The three-seed memory-design recipes use procurement seeds 20260719, 20260821, 20260822;
cybersecurity 20260812, 20260821, 20260822; finance 20260816, 20260821, 20260822. They cover
`glm_5_2_baseten`, `kimi_baseten`, `nemotron_3_ultra_baseten`, `inkling_baseten`,
`deepseek_v4_1_flash_baseten`, `grok_4_3_openrouter`, and `qwen_plus_0728_openrouter`,
with `gptoss_baseten` and `deepseek_baseten` executors. Other extensions have their own
populations: do not apply that matrix to every study or pool routes silently.

Generated procurement corpora remain YAML sources with compiled JSONL:

```bash
uv run python -m domains.procurement.compile_corpus --version generated_v1 --check
uv run python -m domains.procurement.compile_corpus --version generated_v2 --check
```

## Provenance and replay

New extension manifests record corpus sources, implementation/configuration hashes,
runtime versions, options, and a file map with SHA-256 hashes and row counts. Existing
manifests and artifacts are preserved byte-for-byte. The model context capture stays
with the original engines.

Executor-only replay verifies the source evidence, selection trials when applicable,
copied writer artifacts, and recorded corpus/domain implementation sources against the source manifest before planning or making calls:

```bash
uv run python -m experiments.run --study writer_variants \
  --domain procurement --source-run results/procurement/<completed-run> \
  --executor-targets gptoss_baseten --validate-only
```

Legacy extension runs may lack file hashes. Replaying them requires the explicit
`--allow-unverified-source` option. Their current input hashes are recorded in the new
manifest with `verification: unverified_legacy`; this cannot establish their historical
integrity. A mismatched recorded hash always fails, even with this option.

## Available results and final analyses

`results/extensions/manifest.json` pins the available snapshots and diagnostic/analysis
artifacts. Its observed-run references are evidence of source names, **not an exhaustive
run inventory**. The original raw extension runs and a verified archive location were
not supplied with this revision. A clean checkout can check and replot saved summaries,
but cannot independently recount all extension trials. The recorded diagnosis JSONL
files are also a subset; the full final attribution recount uses the committed
`results/diagnosis/failures.csv`.

```bash
uv run python -m analysis.extension_results
uv run python -m analysis.extension_results --diagnosis --out output/mechanism_counts.json
uv run python -m analysis.extension_results --figure frontier --out output/frontier
uv run python -m analysis.extension_results --figure memory_design --out output/memory_design
uv run python -m analysis.extension_results --figure mechanism --out output/mechanism
uv run python -m analysis.extension_results --figure restatements --out output/restatements
uv run python -m analysis.extension_results --figure writer_scaling --out output/writer_scaling
```

Each command verifies the archived inputs first. Figures produce PDF and PNG files.
The mechanism calculation retains the original rules: a final attempt other than
`accepted` or `no_change` supplies the rejected-update label; otherwise it uses the
non-rejection judge votes, with ties assigned to `other`. No judges are called.
`--require-raw` fails explicitly because this release has no verified raw-run archive.

The supported `--pool` command is blocked until a verified raw-run archive and exact
run inventory are supplied. The original seven-writer calculation is preserved in
`analysis/extensions/pool.py` for that integration. Its latest-completed selection rules
can recount a restored research tree, but cannot establish the historical run selection. The older
`analysis.plot_mitigation_frontier` represents a separate five-writer comparison and
now fails if its complete population is unavailable. Use the archived `frontier`
figure command above for the four-point typed-memory comparison.

Historical paper exports continue to verify their original release hashes; the older
Cybersecurity and Finance releases are stored under `results/<domain>/paper/releases/`,
and Finance's historical corpus generator under `results/finance/paper/sources/`.

```bash
uv run python -m analysis.paper_results --domain all --output-dir output/paper
```

## Original recipes and recovery

The original research revision is `9ada7784ba394dbf7340812d9667ab05c12c08b6`.
The extension index records original launcher and analysis paths and Git blob IDs,
including the launcher environment overrides. These references preserve the exact
settings and source code without keeping manuscript edits and launch diaries in the
supported repository interface. For example, inspect a recipe without executing it:

```bash
git show 9ada7784ba394dbf7340812d9667ab05c12c08b6:run_extensions_21a.sh
```

Use the matching original recipe for instruction strings, targets, seeds, batch sizes,
token limits, timeouts and tags. The cleanup is a separate commit: reverting it restores
the removed files while keeping the integration fixes. Restoring files does not restore
raw experiment data that was never committed.
