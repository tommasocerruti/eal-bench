# Authorization-failure mechanism analysis

## Saved data flow

The analysis follows the repository's existing deterministic path:

1. Procurement canonical state is compiled from the benchmark YAML and replayed by
   `domains.procurement.cases.replay_case`. Cybersecurity canonical state is loaded from the
   frozen benchmark corpus and replayed by `domains.cybersecurity.corpus.replay_case`.
2. `memory_states.jsonl` contains one observation for every logical writer update. Its
   `current_memory_id` points to the accepted payload in `memories.jsonl`, or to the older payload
   retained after a failed update. `profile_id`, `writer_run_id`, `case_id`, `condition_id`, and
   `block_index` identify a trajectory.
3. Typed payloads are compared with the corresponding canonical checkpoint through the domain's
   registered `FidelityAdapter`. Saved `fidelity.jsonl` rows are treated as an integrity check,
   not as a second definition of correctness.
4. The domain oracle and the memory adapter's `authorizes` method compare canonical and apparent
   authorization for matched requests. Final `trials.jsonl` rows and preselected natural-error
   witness rows supply downstream executor outcomes. Replays of one memory are kept distinct from
   independently generated memories.
5. Error-introduction hazards use only event exposures whose preceding typed state was correct.
   Confidence intervals resample domain case families. Persistence uses a Kaplan–Meier estimator:
   spontaneous repair is the event and the end of a saved trajectory is right-censoring.
6. Exact-repair outcomes retain both benchmark endpoints. `requested_action_taken` is the targeted
   submitted-request endpoint used by the frozen transfer summaries; `unauthorized_action_taken`
   also counts an unauthorized operational alternative.

Every intermediate incremental state is preserved for the five clean writers in both release
matrices. Typed states can therefore be scored at every update, including non-authorization
updates and retained-state failures. No `memory_annotations.jsonl` artifact exists for these
runs. Free-text content cannot be deterministically converted to authorization records under the
frozen protocol, so it is retained in coverage and behavioral tables but excluded from semantic
taxonomy and trajectory estimates. Producing those labels requires the existing blinded
extraction and human-validation protocol; a heuristic parser or unapproved LLM judge is not used.

## Reproduction

From the repository root:

```bash
UV_CACHE_DIR=/tmp/eal-bench-uv-cache \
  uv run --extra analysis python -m analysis.failure_mechanisms \
  --output results/mechanism_analysis/20260814__failure-mechanisms-v2
```

Use `--validate-only` to verify source hashes, lineage, and equivalence with saved fidelity rows
without writing derived files. The command makes no model calls and never modifies source runs.
