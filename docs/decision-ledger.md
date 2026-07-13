# Decision ledger

The local SQLite decision ledger is append-only. Triggers reject `UPDATE` and
`DELETE` operations on decision events.

Each event can record a run, round, stable asset UUID, event type, actor,
previous and new state, visible reason, arbitrary structured payload, and config
or code hashes.

```bash
photo-fieldwork ledger init --ledger RUN/decisions.sqlite
photo-fieldwork ledger append --ledger RUN/decisions.sqlite \
  --run-id v01 --round-id round-01 --asset-uuid UUID \
  --event-type reviewed-uncertain --actor editor \
  --new-state uncertain --reason "Context is visible; project provenance is not"
photo-fieldwork ledger export --ledger RUN/decisions.sqlite \
  --output RUN/reports/decision-events.jsonl
```

Recommended event types include `retrieved`, `inspected`, `assigned-view`,
`reviewed-fit`, `reviewed-reject`, `reviewed-uncertain`, `placed-on-hold`,
`hold-propagated`, `replaced`, `rerouted`, `selected`, `committed`, and
`verified`.

The ledger does not replace editor-facing CSV. It preserves the lineage from
which each versioned manifest and report can be reconstructed.
