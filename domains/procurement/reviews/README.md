# Approval and optional blinded review for `benchmark_v1`

The repository owner approved the release scope recorded in `benchmark_v1.json`, so independent
review is not a freeze requirement.

- `benchmark_v1_authorization_blinded.jsonl` supports independent authorization labeling.
- `benchmark_v1_attractiveness_blinded.jsonl` supports operational ranking without authorization
  labels.
- Do not give either group `benchmark_v1_private_mapping.json`; it maps opaque review IDs to
  internal benchmark identities.
- Record reviewer identities, assignments, decisions, and any source-based adjudication in
  `benchmark_v1.json` without changing the blinded packets.

Independent review remains useful but optional. Any recorded disagreement blocks acceptance until
it is resolved from visible evidence and the release hashes are regenerated.
