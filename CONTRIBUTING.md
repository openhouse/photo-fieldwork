# Contributing

Photo Fieldwork welcomes improvements to selection logic, evaluation design, privacy safeguards, catalog adapters, and editor handoffs.

Before opening a change:

1. Run `make demo` and `make check`.
2. Explain which workflow phase the change affects.
3. Add or update a test for behavioral changes.
4. State whether the change touches pixels, OCR, faces, locations, or catalog writes.
5. Include a failure case. A successful example alone is not an evaluation.
6. Keep populated machine profiles, live Photos identifiers, and user-specific absolute paths out of Git.
7. Preserve plan, receipt, and helper compatibility or document the schema change.

Do not commit real private photographs, raw OCR, exact private locations, credentials, contact exports, or personal Photos manifests. Use synthetic fixtures.

CI runs only privacy-safe synthetic fixtures. Real-library integration checks remain local and should emit generalized receipts, not archive content.
