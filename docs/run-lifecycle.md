# Run lifecycle

Photo Fieldwork run state is evidence-backed. A phase is complete because its
required artifact exists, parses, passes its gate, and has a recorded hash, not
because a process once started.

## Commands

```bash
photo-fieldwork run init --workspace RUN --run-id ID --version v01 \
  --target 4000 --source-identifier SOURCE --source-count COUNT
photo-fieldwork run status --workspace RUN
photo-fieldwork run reconcile --workspace RUN
photo-fieldwork run finalize --workspace RUN
```

`reconcile` recognizes conventional artifacts for the brief, retrieval,
inspection, evaluation, validation, write test, production commit, and
independent verification phases. It records SHA-256 hashes and phase changes.

`finalize` reruns reconciliation and refuses completion while any required phase
is pending. It never waives a failed gate.

## Interruption and resumption

Inspection plans remain resumable through their JSONL output and receipt. Run
reconciliation is idempotent: it can be invoked after an interruption without
rewriting editorial decisions or catalog membership.

## Mutation boundary

A completed production album is an add-only snapshot. If later review changes
the selection, create a new version. Do not remove membership from a committed
version to make its history look cleaner.
