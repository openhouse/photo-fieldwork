# Contributing

Photo Fieldwork welcomes improvements to selection logic, evaluation design, privacy safeguards, catalog adapters, and editor handoffs.

Before opening a change:

1. Run `make demo` and `make check`.
2. Explain which workflow phase the change affects.
3. Add or update a test for behavioral changes.
4. State whether the change touches pixels, OCR, faces, locations, or catalog writes.
5. Include a failure case. A successful example alone is not an evaluation.
6. Add a schema migration when a persisted contract changes.
7. Confirm that a fresh replay produces the stored result.

Do not commit real private photographs, raw OCR, exact private locations, credentials, contact exports, or personal Photos manifests. Use synthetic fixtures.

Machine profiles containing real paths, folder identifiers, People data, or
library counts do not belong in the public repository. Use
`profiles/profile.example.json` as the fixture shape.
