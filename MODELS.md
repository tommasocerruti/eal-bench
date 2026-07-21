# Models and targets

A model target is a named provider/model route. It records the provider, model, capabilities,
rate limits, and concurrency separately from the task being performed.

```python
llm.complete("executor", messages, target="glm_baseten")
llm.complete("executor", messages, target="gptoss_openrouter")
```

Targets and tasks live in `config.yaml`:

```yaml
model_targets:
  gptoss_baseten:
    provider: baseten
    model: gptoss
    capabilities: [native_tools, forced_tool_choice, seed]
    max_concurrency: 20

tasks:
  writer:
    default_target: gptoss_baseten
    params: {temperature: 1.0, max_tokens: 4096}
```

A task defines a role, default target, and generation parameters. Pass `target=` to change the
route for one call. The optional `model=` override changes the model only within the selected
target's provider; do not combine it with `target=`.

`LLM.complete()` is the executor transport. Benchmark writers use the LangMem integration.
Use `LLM.preflight(...)` to check a target, its declared capabilities, and its credential without
sending a request:

```python
route = llm.preflight(
    "executor",
    target="gptoss_baseten",
    required_capabilities={"native_tools", "forced_tool_choice"},
)
print(route.provider, route.resolved_model)
```

The equivalent CLI check is:

```bash
uv run python -m experiments.check_target
```

Add `--skip-credential-check` when no key is available. Add `--live` only when you intend to make
a paid forced-tool request:

```bash
uv run python -m experiments.check_target --live
```

The offline check verifies configuration. Only the live check confirms that the current provider
route accepts native forced tools and `seed`.

For LangMem, select the writer component:

```bash
uv run python -m experiments.check_target \
  --component langmem-writer \
  --skip-credential-check

uv run python -m experiments.check_target \
  --component langmem-writer \
  --live
```

## Baseten short-name roster

Short names resolve to these Baseten slugs. Full slugs and unknown names pass through unchanged.

| Short name | Slug | Context (K) | Max output (K) |
|---|---|--:|--:|
| `deepseek` | `deepseek-ai/DeepSeek-V4-Pro` | 1048 | 1048 |
| `glm` | `zai-org/GLM-4.7` | 200 | 200 |
| `kimi` | `moonshotai/Kimi-K2.6` | 262 | 262 |
| `gptoss` | `openai/gpt-oss-120b` | 128 | 128 |
| `nemotron` | `nvidia/Nemotron-120B-A12B` (Nemotron Super) | 202 | 202 |

Other aliases, such as `ds`, `glm-4.7`, `k2.6`, `gpt-oss`, and `super`, are defined in
`src/eal_bench/llm/models.py`.

## Notes

- Reasoning models such as `gptoss` and `nemotron` use completion tokens for hidden reasoning.
  Give them a generous `max_tokens`; a small limit can return empty content with
  `finish_reason="length"`.
- Add models through `model_targets` with an exact provider slug. Change
  `src/eal_bench/llm/models.py` only when adding a Baseten alias and its metadata.
- Baseten is the default experimental provider. OpenRouter is an explicit portability route.
  Keep provider and target provenance separate in analysis.
- Baseten's [Model APIs catalogue](https://docs.baseten.co/inference/model-apis/overview) is the
  source for the roster. Availability and pricing can change.
