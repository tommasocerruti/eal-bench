# Reusable evaluation interface

`eal_bench.eval` lets another project run EAL evaluations without the experiment runner and
without EAL's provider configuration. Install the package, build trials, call your own model,
and score the replies with the official scorer.

EAL keeps four tracks and reports them separately:

| Track | Question | Module |
|---|---|---|
| Executor controls | Does the executor respect faithful authorization memory? | `eal_bench.eval.controls` |
| Memory preservation | Does writing or updating memory change authorization? | `eal_bench.eval.preservation` |
| Error propagation | Do authorization errors in memory cause unauthorized actions? | not yet available |
| End-to-end EAL | Does a writer introduce an error that an executor acts on? | not yet available |

There is no combined EAL score. A single number would hide which stage failed.

## Install

```bash
pip install eal-bench                # core interface
pip install "eal-bench[inspect]"     # adds the Inspect adapter
```

The interface loads trials and scores replies with no credentials. Credentials belong to
whatever calls the model, which is your own code or your framework.

## Resource identity

Two results are comparable only when their resource versions match.

```python
from eal_bench.eval import describe, list_domains, load_domain

list_domains()                       # ('cybersecurity', 'finance', 'procurement')
describe(load_domain("procurement")).to_dict()
```

`ResourceVersions` pins the domain adapter, corpus version, presentation and its hash, the
memory implementation and its hash, the scorer, and the protocol. Record it next to any
result you publish.

## Score a reply

`Trial` holds model-visible data only. `TrialTruth` holds the oracle state. Send the first to
your model. Never send the second.

```python
from eal_bench.eval import ModelResponse, aggregate, score_response

response = ModelResponse.from_tool_calls(
    [("submit_order", '{"vendor": "NimbusSoft", "amount": 4500}')]
)
outcome = score_response(truth, response)
metrics = aggregate([outcome], track="controls")
```

If you already call an OpenAI-compatible endpoint, hand the reply over directly. The same
call also absorbs an exception raised in place of a reply, so a failed call is reported rather
than dropped.

```python
ModelResponse.from_openai(completion)
ModelResponse.provider_error("timeout after 60s")
```

## Denominators

Counting follows [the shared result guide](../results/README.md).

- Authorized use counts the exact requested action over authorized requests.
- Unauthorized submission counts that action over unauthorized requests.
- Each has its own authorization denominator.
- Invalid, no-action and provider-error trials stay in those denominators.
- Provider errors are also counted in their own column.

## Pooling guards

Aggregation refuses to mix resource versions, and refuses to mix memory conditions. Faithful
text and faithful typed share a resource version but are different treatments, so the resource
guard alone does not keep them apart.

```python
aggregate(outcomes, track="controls")                  # MixedResourcesError or MixedConditionsError
aggregate_by(outcomes, ("condition_id",), track="controls")   # one row per condition
```

Aggregation also refuses to mix request surfaces, because the Inspect adapter does not send
byte-identical tools. Pass `allow_mixed_resources=True`, `allow_mixed_conditions=True` or
`allow_mixed_surfaces=True` to opt in deliberately.
`TrackMetrics` records `resource_key`, `condition_id`, `executors` and `surfaces`, so a number
always says which identity it belongs to.

## Attribution

`TrialOutcome` carries `executor_target`, `executor_provider`, `executor_model`,
`response_model` and `surface`. Pass the route you used so an exported result stays
attributable; without it two checkpoints serialize identically.

```python
from experiments.authorization_memory.schemas import ModelProvenance

score_response(truth, reply, executor=ModelProvenance(
    target_id="gptoss_baseten", provider="baseten",
    requested_model="gptoss", resolved_model="openai/gpt-oss-120b",
))
```

`surface` names the path that built the request, `"native"` by default and `"inspect"` through
the adapter. Results from different surfaces should not be pooled.

## Offline tokenizer

The reference token counter is `cl100k_base`, which tiktoken downloads on first use. An
installation with a cold cache and no network falls back to a regex counter, which produces
different counts. `verify()` reports `reference_tokenizer` so the two are never confused. Warm
the tiktoken cache if you need counts identical to the published runs.

## Use from another language

```bash
python -m eal_bench.eval domains
python -m eal_bench.eval export --track controls --domain procurement --out trials.jsonl
```

`trials.jsonl` holds one trial per line with its messages, tools and resource versions. It
never contains oracle state. Send each trial to your model, then score in Python with
`score_response`, or write outcomes back with `write_outcomes` and read them with
`read_outcomes`. Both files carry a `schema_version`, and reading rejects a version it does not
know rather than silently constructing a wrong row.

## Offline verification

```bash
python -m eal_bench.eval.reference --verify
```

This runs from an installed wheel with no repository and no credentials. It re-derives every
recorded fixture value and fails on any drift. The repository gate
`python -m experiments.run --validate-only --all-domains` runs the same check.

## Scoring is not reimplemented

`eal_bench.eval.scoring` delegates to the runner's own `_score_executor_response`. A track and
the internal runner therefore cannot produce different outcomes for the same reply.
