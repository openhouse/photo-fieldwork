# Contributing

Photo Fieldwork welcomes improvements to selection logic, evaluation design, privacy safeguards, catalog adapters, and editor handoffs.

Before opening a change:

1. Run `make demo` and `make check`.
2. Explain which workflow phase the change affects.
3. Add or update a test for behavioral changes.
4. State whether the change touches pixels, OCR, faces, locations, or catalog writes.
5. Include a failure case. A successful example alone is not an evaluation.
6. For Apple Photos changes, include the source-profile, WAL, permission,
   resume, or idempotence condition the change is intended to preserve.

Do not commit real private photographs, raw OCR, exact private locations,
credentials, contact exports, completed machine profiles, personal source or
folder identifiers, Photos database paths, SQLite snapshots, or personal
Photos manifests. Use synthetic fixtures.

`make check` compiles the Python core and skill scripts, validates every tracked
JSON contract, runs the synthetic tests, and type-checks the Swift helper.
