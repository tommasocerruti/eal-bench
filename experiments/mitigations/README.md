# Authorization-memory mitigations

Mitigations share the benchmark's domain adapters, native executor tools, deterministic scorer,
and artifact conventions. Their implementations and execution helpers live in this package;
result analysis lives in `analysis/`, and authority and lifecycle rules live in `domains/`.

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

## Bounded event sourcing

`event_sourcing/` implements the paper's bounded event extractor and deterministic reducer.
At each update the writer sees the compact previous typed state and the new raw block. The
cumulative event log stays outside the writer's context. Accepted event deltas append to that log;
the reducer applies them atomically, with the same primary memory capacity and at most two
structural attempts. Failed updates retain the previous state.

This mitigation requires new event-writer calls. Its paired baseline reuses original saved
incremental typed memories and makes no baseline-writer calls. Both arms execute on the selected
current targets, so a new executor does not need to appear in the source run. Residual oracle
replays are selected and frozen before executor calls.

For each domain and seed, provide one completed writer source for each selected writer target:

```bash
uv run python -m experiments.run \
  --domain procurement \
  --study event_sourcing \
  --writer-targets nemotron_3_ultra_baseten \
  --executor-targets gptoss_baseten \
  --source-run results/procurement/NEMOTRON_WRITER_RUN \
  --validate-only
```

Corpus, presentation, cases and seed default to the first source manifest. All sources must match
those factors and their original writer routes. Use comma-separated writer and executor targets,
and repeat `--source-run` once per writer. This protocol uses one writer and executor repetition
per seed, incremental typed memory, primary capacity, and two structural attempts.

The validation output includes `study_validation.run_plan`: writer-call bounds, paired executor
counts, and the maximum residual replay count. To run it, replace `--validate-only` with
`--estimated-cost-usd AMOUNT`. An interrupted run resumes with the same options and
`--resume-run results/<domain>/EVENT_RUN`; completed calls and accepted writer updates are retained.
The portable manifest checks source artifacts, routes, implementation hashes and checkpoints
before constructing the live client.

Run the zero-cost domain fixtures without source runs, or analyze completed paired runs:

```bash
uv run python -m experiments.run --study event_sourcing --validate-only --all-domains
uv run python -m analysis.event_sourcing \
  --event-run results/procurement/EVENT_RUN \
  --baseline-run results/procurement/NEMOTRON_WRITER_RUN \
  --output results/event_sourcing/ANALYSIS
```

Without source runs, validation checks the mechanism and recovery fixtures only; a live paired run
still requires its complete baseline sources. Repeat both analysis input options for a matrix.
Analysis keeps routes, presentations and implementation identities separate and uses the fresh
baseline replay when the event-run manifest declares it.

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
domains/                      authorization semantics, source authority and event lifecycle rules
results/<domain>/             new run manifests and raw artifacts
```

The source-authority gate was ported from local research commit
`af789e6a2055c01f8764299a191cde4aa80d22a5`. Its deterministic gate semantics are preserved;
the common study interface replaces the historical fixed matrix and machine-specific paths.
Bounded event sourcing was ported from local research commit
`e40f74c273f8b2f866b64fe60053880216518014`, preserving its extraction and reducer semantics while
replacing the historical machine-specific launch and precommit workflow.
