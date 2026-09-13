# Using EAL in your research

Choose the evaluation track that matches your research question:

| Track | What it measures | Available interface |
|---|---|---|
| [Executor controls](#1-executor-controls) | Whether a model follows correct authorization memory | Python API and Inspect task |
| [Memory preservation](#2-memory-preservation) | Whether a memory retains the authorization boundaries in the history | Python scoring API |
| [Error propagation](#3-error-propagation) | Whether an authorization error in memory changes the executor's actions | Experiment runner |
| [End-to-end EAL](#4-end-to-end-eal) | Whether a writer introduces an error that a downstream executor acts on | Experiment runner |

## Install and verify

Install EAL with Python 3.10 or newer and cache its tokenizer:

```bash
pip install "eal-bench[inspect] @ git+https://github.com/tommasocerruti/eal-bench.git@1dfffc574fe5db4203aa934c6214b9117bd61ea9"
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
[full API reference](https://github.com/tommasocerruti/eal-bench/blob/1dfffc574fe5db4203aa934c6214b9117bd61ea9/docs/reusable_api.md#track-executor-controls).
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
[memory-preservation API](https://github.com/tommasocerruti/eal-bench/blob/1dfffc574fe5db4203aa934c6214b9117bd61ea9/docs/reusable_api.md#track-memory-preservation)
for text annotations, writer setup, and update handling.

## 3. Error propagation

Test whether an authorization error in memory causes an unauthorized action. Compare the
executor's responses to erroneous and repaired memories while keeping the case, request, and
model fixed.

Use the experiment runner's `controls` study for controlled memory changes or its `writer`
study for naturally generated errors and repairs. See the
[domain guide](domains/README.md#behavioral-routes).

After the [full benchmark setup](README.md#run-the-full-benchmark), validate a Procurement
control study from the repository root:

```bash
uv run python -m experiments.run \
  --domain procurement \
  --corpus-version benchmark_v1 \
  --presentation-version naturalistic_v1 \
  --study controls \
  --executor-targets gptoss_baseten \
  --validate-only
```

Choose your configured executor model, review the call plan, and follow the
[live-run instructions](README.md#run). Report the paired outcomes for each memory change.

## 4. End-to-end EAL

Measure whether a writer introduces an authorization error that a downstream executor treats
as permission to act. This evaluates the complete sequence:

organizational history → writer → persistent memory → executor → tool decision.

The benchmark varies free-text versus typed memory and one-shot versus incremental writing.
Memories are frozen before executor evaluation, and decisions are scored against the hidden
authorization ledger.

Use the repository's `writer` study. For example, validate a run with the configured routes:

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

See [Run the full benchmark](README.md#run-the-full-benchmark) for setup and live execution.
The `pressure` study can subsequently replay a completed writer run under operational pressure
while reusing its frozen memories and requests.

Report memory errors alongside authorized use and unauthorized submission. Compare against
faithful memories and repairs to identify the source of failures.

## Reporting results

Report scores for each evaluation track separately, state the models and EAL version used,
and cite the [paper](README.md#citation).
