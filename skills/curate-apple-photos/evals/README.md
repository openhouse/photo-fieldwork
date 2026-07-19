# Curate Apple Photos evals

These synthetic, public-safe scenarios probe the failure modes most likely to produce a convincing but invalid result. They emphasize exact assignment, fresh evidence, per-view quality, safety, recoverability, artifact identity, and publication boundaries.

The prompt bank is intentionally adversarial. A good response should block when evidence is weak or state is ambiguous; completing every requested action is not automatically success.

Run the deterministic contract checks with:

```bash
make evals
```

When changing the skill or workflow, compare the candidate against the previous skill snapshot on the same prompts. Inspect failures, change one coherent contract, rerun the full bank, and retain regressions as permanent cases.
