# Contributing

Photo Fieldwork welcomes improvements to selection logic, evaluation design, privacy safeguards, catalog adapters, and editor handoffs.

Before opening a change:

1. Run `make demo` and `make check`.
2. Explain which workflow phase the change affects.
3. Add or update a test for behavioral changes.
4. State whether the change touches pixels, OCR, faces, locations, or catalog writes.
5. Include a failure case. A successful example alone is not an evaluation.
6. When changing the bundled skill, add or refine an adversarial case in
   `skills/curate-apple-photos/evals/evals.json`. Compare it with the previous accepted skill,
   preserve ties and failures, and rerun at least one unrelated safety canary.

Do not commit real private photographs, raw OCR, exact private locations, credentials, contact exports, or personal Photos manifests. Use synthetic fixtures.
