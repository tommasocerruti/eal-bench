# Using EAL in your research

Choose the evaluation track that matches your research question:

| Track | What it measures | Available interface |
|---|---|---|
| [Executor controls](#1-executor-controls) | Whether a model follows correct authorization memory | Python API and Inspect task |
| [Memory preservation](#2-memory-preservation) | Whether a memory retains the authorization boundaries in the history | Python scoring API |
| [Error propagation](#3-error-propagation) | Whether an authorization error in memory changes the executor's actions | Python API and Inspect task |
| [End-to-end EAL](#4-end-to-end-eal) | Whether a writer introduces an error that a downstream executor acts on | Python API and Inspect task |

## Install and verify

Install EAL with Python 3.10 or newer and cache its tokenizer:

```bash
pip install "eal-bench[inspect] @ git+https://github.com/tommasocerruti/eal-bench.git@c98cd7eed6ab17ab960b113f48ef6bc479f806a5"
python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"
```

Check the reference scores without model API credentials:

```bash
python -m eal_bench.eval.reference --verify
```

The examples use `procurement`; you can also evaluate `cybersecurity` and `finance`.

## 1. Executor controls

Evaluate whether your model follows correct authorization memory. It receives a fixed faithful
memory, as free text or a typed profile, and matched authorized and unauthorized requests.
Use this track to compare models or checkpoints before testing them on generated memories.

### Run through Inspect

Save this as `eal_tasks.py`:

```python
from inspect_ai import task
from eal_bench.eval.inspect_adapter import control_task


@task
def procurement_controls():
    return control_task("procurement")
```

Set `EAL_MODEL` to your model's Inspect route and configure its provider credentials. The model
must support native tool calls.

```bash
inspect eval eal_tasks.py --model "$EAL_MODEL" --temperature 1.0
```

The task includes both `faithful_text` and `faithful_typed`. Pass
`conditions=("faithful_typed",)` to select one.

To try the task without API credentials, use Inspect's mock model:

```bash
inspect eval eal_tasks.py --model mockllm/model --limit 2
```

Re-score a saved log without generating new responses:

```bash
inspect score logs/run.eval --scorer eal_bench/eal_controls --model mockllm/model
```

### Read the results

Report authorized use and unauthorized submission separately for each memory condition,
including the denominator for each rate. A model that always declines may avoid unauthorized
actions while failing to use legitimate permissions.

Invalid and missing tool calls count toward the rates. Provider failures are reported separately;
a rate with no eligible cases is undefined.

For direct Python integration, use `build_control_trials()` and `score_response()` as described
in the
[full API reference](docs/reusable_api.md#track-executor-controls).
Keep the ground truth used for scoring out of the model's input.

## 2. Memory preservation

Compare a written or updated memory with the authorization state in the source history. The
scorer identifies omissions, broadened or narrowed scope, contradictions, stale permissions,
and missing or extra records. Use this track to compare writers, memory formats, or update
strategies.

### Score a typed memory

This offline example loads one case and verifies its faithful typed memory:

```python
from eal_bench.eval import load_domain
from eal_bench.eval.preservation import apparent_authority, score_memory

domain = load_domain("procurement")
case = domain.corpus.load_cases(domain.corpus.default_version)[0]
case_id = domain.corpus.case_id(case)
payload = domain.memory.serialize_typed(domain.memory.faithful_typed(case))

preservation = score_memory("procurement", case_id, payload)
authority = apparent_authority("procurement", case_id, payload)

assert preservation.exact is True
assert authority.formed is False
```

To evaluate your writer, replace `payload` with its memory for the same case, using that
domain's typed schema. Keep the canonical ledger hidden from the writer. For intermediate
updates, pass `block_index` to score against the authorization state at that point in the history.

`score_memory()` reports fidelity errors. `apparent_authority()` checks whether the memory
incorrectly grants permission for a request.

Free-text memories require accepted structured annotations of the same memory. Without valid
annotations, the result remains unscored.

See the
[memory-preservation API](docs/reusable_api.md#track-memory-preservation)
for text annotations, writer setup, and update handling.

## 3. Error propagation

Test whether an authorization error in memory changes what the executor does. Each case gives a
matched pair: the same request, policy, tools, presentation and model, with only the memory
swapped between an erroneous variant and its oracle-exact counterpart. No writer runs.

Memories a real writer produced ship with the package, so this works after a plain install:

```python
from eal_bench.eval import score_many
from eal_bench.eval.propagation import (
    build_propagation_trials, propagation_summary, writer_memories,
)
from experiments.authorization_memory.schemas import ModelProvenance

route = ModelProvenance(
    target_id="my_executor", provider="my_provider",
    requested_model="my-model", resolved_model="my-model-2026-01",
)

writer_memories("procurement")                  # what a writer actually wrote
pairs = build_propagation_trials("procurement") # both arms, both request classes
replies = [my_model(trial) for trial, _ in pairs]
outcomes = score_many(pairs, replies, executor=route)

for report in propagation_summary(outcomes, expected=pairs):
    report.origin                            # 'altered' or 'writer'
    report.erroneous_rate                    # unauthorized submission, over denied requests
    report.exact_rate                        # the same, behind oracle-exact memory
    report.erroneous_authorized_use_rate     # legitimate action, over authorized requests
    report.demonstrates_writing_failure      # only ever True for a writer memory
```

Pass `executor=`. Without it the outcomes record an empty route and cannot be attributed to the
model that produced them. Pass `expected=pairs` so a reply that never came back is reported as
a missing comparison rather than quietly leaving the population.

**Two origins, never merged.** `altered` memories are produced by the package on purpose, by
widening an authorization field or taking an intermediate state. They diagnose sensitivity:
they show what an executor does when memory is wrong, not that a writer would write it.
`writer` memories are ones a writer actually produced, and only those carry
`demonstrates_writing_failure`.

**Two denominators, never pooled.** An authorized request cannot be an unauthorized submission,
and a denied request cannot be legitimate use, so `authorized_pairs` and `unauthorized_pairs`
are counted separately. A rate with no denominator is `None`: not measured, not zero.

To replay your own archive, pass `variants=`. Give separate writer runs distinct
`writer_run_id` values. Duplicate detection also includes the writer target, so different
writers can use the same run number.

### Run through Inspect

```python
from inspect_ai import task
from eal_bench.eval.inspect_adapter import propagation_task

@task
def procurement_propagation():
    return propagation_task("procurement")
```

## 4. End-to-end EAL

Measure whether a writer introduces an authorization error that a downstream executor treats as
permission to act. This evaluates the complete sequence:

organizational history → writer → persistent memory → executor → tool decision.

```python
from domains import get_domain
from eal_bench.eval import score_many
from eal_bench.eval.end_to_end import (
    attribution_rows, end_to_end_report, executor_trials_for_memories,
    link_written_memories, plan_end_to_end,
)
from experiments.authorization_memory.langmem_writer import run_writer_chains

plan = plan_end_to_end("procurement", writer_target="my_writer")
artifacts = run_writer_chains(my_llm, get_domain("procurement"), plan.writer_chains, ...)
memories = link_written_memories("procurement", artifacts, annotations=my_annotations)

baseline = score_many(plan.baseline_trials, my_baseline_replies, executor=route)
trials = executor_trials_for_memories("procurement", memories)
outcomes = score_many(trials, [my_model(t) for t, _ in trials], executor=route)

report = end_to_end_report(
    "procurement", memories, outcomes, baseline, expected=trials
)
```

The plan carries a faithful-memory baseline beside the writer chains, and it is not optional:
without it an unauthorized action cannot be told apart from an executor that would have acted
anyway. `end_to_end_report` refuses a baseline measured on a different corpus, request surface
or executor route.

**Attribution is bounded.** An unauthorized action alone is never reported as a memory-induced
failure. A request is attributed only when the memory grants what the ledger denies, the
executor acts behind it, and the same executor does not act behind oracle-exact memory.
`attribution_rows` gives the chain per request with a reason whenever attribution is withheld.

**Free text.** Typed and free-text memories both replay. Free text needs accepted annotations
for a formation label; without them the behavioral scores are still reported and attribution
says `formation_not_estimable` rather than claiming the memory did not form.

**Separate counts.** `written_authorized_use` and `written_unauthorized_submission` carry their
own denominators, with `exact_*` counterparts for the repair arm, and `by_condition` is keyed by
writer and condition together so two writers running one condition are two treatments.

Report memory preservation, executor behavior and propagation separately. There is no combined
score.

### Run through Inspect

Inspect drives the executor replay; the writer stays on `run_writer_chains`.

```python
from inspect_ai import task
from eal_bench.eval.inspect_adapter import end_to_end_executor_task

@task
def procurement_end_to_end():
    return end_to_end_executor_task("procurement", memories)
```

### Using the experiment runner instead

To reproduce the published runs rather than evaluate your own models, use the repository's
`writer` study after the [full benchmark setup](README.md#run-the-full-benchmark):

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

The `pressure` study can then replay a completed writer run under operational pressure, reusing
its frozen memories and requests.

## Reporting results

Report scores for each evaluation track separately, state the models and EAL version used,
and cite the [paper](README.md#citation).
