# Paper v2 extensions

The second version of the paper adds the following studies and analyses:

- **Memory designs and mitigations:** compare text, typed and hybrid memory, rebuilding
  from history, retrieval, and a short instruction to preserve authorization boundaries.
  See the [writer variants runner](../experiments/writer_variants_run.py).
- **Closed-loop behavior:** let the agent's actions feed back into memory, with neutral
  log entries as a control. See the [closed-loop runner](../experiments/closed_loop.py).
- **Controlled histories:** vary how often an outdated permission is repeated in
  generated [procurement histories](../domains/procurement/corpus/generated_v2/).
- **Broader comparisons:** extend model and seed coverage, replay memories with another
  executor, vary memory capacity, and compare writer candidate selection strategies.
- **Failure analysis:** locate where false permissions enter memory and combine writer
  validation records with judge labels to explain the failures.

The code follows the existing repository layout: experiment runners are in
[`experiments/`](../experiments/), while [`analysis/extensions/`](../analysis/extensions/)
contains selected final analyses and plots. [`results/extensions/`](../results/extensions/)
holds saved summaries and an index of the available inputs.
