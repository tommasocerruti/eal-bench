# Authorization-memory mitigations

Mitigations share the benchmark's domain adapters, native executor tools, deterministic scorer,
and artifact conventions. Their implementations and execution helpers live in this package;
result analysis lives in `analysis/`, and source-authority rules live in `domains/`.

## Source-authority gating

`source_authority/` applies the paper's gold cited-source authority gate to saved typed memories.
A record survives only if every cited source is nonempty, visible at the memory's checkpoint,
and attributed to a principal allowed to grant authorization. The gate does not check whether
the source's content supports the record, or whether its scope and lifecycle state are correct.
It assumes the domain provides the set of authorization-capable principals.

The study evaluates both the original and gated memory on the same requests and chosen executor
targets. It makes no writer calls. Original writer identities, seeds, memory hashes and source
manifests remain attached to the comparison, including when the saved writer used a different
provider from the new executor.

From the repository root, replace the source directory below with a completed writer run:

```bash
uv run python -m experiments.run \
  --domain procurement \
  --study source_authority \
  --source-run results/procurement/WRITER_RUN \
  --writer-strategy incremental \
  --executor-targets gptoss_baseten \
  --validate-only
```

Repeat `--source-run` to include more saved writer runs from the same domain, corpus and
presentation. Omit `--writer-strategy incremental` to include both one-shot and incremental
typed memories. Corpus, presentation and case selection default to the first source manifest;
every source must agree with the selected treatment.

After reviewing the validated call plan, replace `--validate-only` with
`--estimated-cost-usd AMOUNT`, using your reviewed estimate. New results are saved under
`results/<domain>/<timestamp>__authorization-memory-source_authority__<tag>/`.
The standard executor-only `--resume-run` workflow continues an interrupted run.

Check the deterministic gate without saved runs or credentials, then summarize a completed replay:

```bash
uv run python -m analysis.source_authority_gating --domain procurement
uv run python -m analysis.source_authority_results results/procurement/REPLAY_RUN
```

Use any executor target configured in `config.yaml`. For example, if your configuration defines
`glm_5_3_baseten`, pass that target to `--executor-targets`. No matching writer-provider credential
is needed to replay saved memories. The repository never substitutes providers silently.

## Sources and provenance

Source directories must contain the raw files declared by their manifests. A directory containing
only `manifest.json` is insufficient. Validation checks artifact hashes, memory/evidence identities
and domain, corpus and presentation compatibility before any live calls.

These entry points create new experiments with current implementation hashes and explicit source
paths. They do not resume the historical paper's machine-specific orchestration scripts or
reinterpret historical precommit files as permission for new calls. The original result manifests
and saved memories remain immutable.

Validation requires no API credentials. Writers and executors use temperature `1.0`; invalid
model outcomes remain in metric denominators, while provider failures are reported separately.

## Layout

```text
experiments/mitigations/       mitigation implementations and execution helpers
analysis/                     offline summaries and paired comparisons
domains/                      authorization semantics and source-authority adapters
results/<domain>/             new run manifests and raw artifacts
```

The source-authority gate was ported from local research commit
`af789e6a2055c01f8764299a191cde4aa80d22a5`. Its deterministic gate semantics are preserved;
the common study interface replaces the historical fixed matrix and machine-specific paths.
