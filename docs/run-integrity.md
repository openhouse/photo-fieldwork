# Run integrity

Photo Fieldwork treats a long private-archive operation as a recoverable sequence of evidenced transitions.

## Event ledger

`events.jsonl` is append-only. Each event has a monotonically increasing revision. `run-state.json` is written to a temporary file, flushed, and atomically renamed while the run lock is held.

Use compare-and-swap revisions when more than one process could report progress:

```bash
./bin/photo-fieldwork transition \
  --run runs/v01 \
  --phase retrieval \
  --status completed \
  --expected-revision 2 \
  --artifact runs/v01/manifests/candidate-pool.csv \
  --attempt-id retrieval-0001
```

A `completed` transition is rejected unless its artifact exists. The ledger records the artifact's SHA-256 checksum. Later transitions rehash every completed artifact, enforce configured phase order, and reject reused attempt IDs.

## Recovery

```bash
./bin/photo-fieldwork status runs/v01
```

`status` reconstructs current state from the ledger and atomically replaces the materialized state. It does not infer completion from a file's name or presence alone.

## Source identity

A source profile records scope, inventory location, exact unique count, generation time, and a fingerprint over sorted canonical UUIDs. Verification compares both count and fingerprint. A same-count membership change is a failure.

## Concurrency

Run-state transitions take an exclusive file lock. Catalog adapters should independently enforce a single writer for Photos mutation; read-only inventory, preview inspection, and verification processes may coexist when the underlying catalog supports them.

## Release identity

Before a write, `doctor --helper-profile-output` records the stable bundle identifier, helper binary SHA-256, supported plan schemas, and capabilities. The catalog plan authorizes that exact helper. Each launch uses a fresh nonce; its receipt binds the raw plan bytes, canonical plan content, source identity, helper identity, and exact folder/album topology. Two distinct equivalent receipts are required for an idempotence claim.
