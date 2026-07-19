# Run lifecycle

Photo Fieldwork run state is evidence-backed. A phase is complete because its
required artifact exists, parses, passes its gate, and has a recorded hash, not
because a process once started.

## Commands

```bash
photo-fieldwork run init --workspace RUN --run-id ID --version v01 \
  --target 4000 --source-identifier SOURCE --source-count COUNT
photo-fieldwork run status --workspace RUN
photo-fieldwork run reconcile --workspace RUN --expected-revision REVISION
photo-fieldwork run reconcile --workspace RUN --expected-revision REVISION \
  --allow-phase-update recursive_evaluation
photo-fieldwork run finalize --workspace RUN --expected-revision REVISION
photo-fieldwork run recover --workspace RUN
```

`reconcile` uses compare-and-swap revision checks and recognizes conventional artifacts for the brief, retrieval,
inspection, evaluation, validation, write test, production commit, and
independent verification phases. It records SHA-256 hashes and phase changes.
It also requires the materialized state and latest event snapshot to agree.

Every transition is appended to `run-events.jsonl` before `run-state.json` is
atomically replaced. `recover` rematerializes the latest coherent state from
that event stream after an interrupted state-file write.

`finalize` reruns reconciliation and refuses completion while any required phase
is pending. It never waives a failed gate.

## Interruption and resumption

Inspection plans remain resumable through their JSONL output and receipt. Run
reconciliation is repeatable: it can be invoked after an interruption without
rewriting editorial decisions or catalog membership. A changed or missing
artifact that was already complete enters a sticky `blocked` state; another
reconciliation cannot accept changed bytes or a newer artifact as a new
baseline. After reviewing a legitimate replacement, name that phase with
`--allow-phase-update`; the expected revision still prevents concurrent or
stale acceptance.

## Mutation boundary

A completed production album is an add-only snapshot. If later review changes
the selection, create a new version. Do not remove membership from a committed
version to make its history look cleaner.
