# Roadmap after revision F

Revision F makes the trustworthy production path substantially more native:

- atomic run state with append-only recovery history;
- frozen source profiles and exact membership fingerprints;
- exact capacity-aware view assignment;
- UUID- and sample-hash-addressed feedback;
- separate evaluation denominators and enforceable per-view gates;
- explicit safety states and human-only clearance;
- semantic catalog plans;
- independent JSON and Markdown verification;
- synthetic CI and expanded failure-mode tests.
- relational safety propagation across duplicate and burst groups;
- decoded preview integrity reports;
- final-holdout freshness gates;
- evaluation seals binding the reviewed candidate to catalog planning;
- a ten-scenario executable eval suite with a 4,000-item benchmark.

The following recommendations remain deliberately separate. They should land as focused changes with production-scale evidence rather than being hidden inside this revision.

## Retrieval engine

Replace repeated `%LIKE%` scans with an indexed or compiled single-pass retrieval engine. Add validated exclusion terms, prior-corpus freshness floors by view, quality-floor diagnostics, and retrieval performance fixtures at realistic whole-library scale.

## Review workspace

Build a local keyboard-first review surface with blind-first inspection, optional provenance reveal, stable UUIDs, explicit safety routing, and UUID-keyed exports. It must remain local and must not automate taste.

## Preview pipeline

Shard preview work and resume it from receipts. Decode and checksum verification now distinguishes missing or corrupt previews; the next step is bounded parallel export with per-shard recovery.

## Reproducible rounds

Standardize round bundles containing configuration, sampled-manifest hash, feedback, policy changes, outputs, score contributions, and comparison reports. Separate retrieval score, visible fit, provenance status, safety state, and editorial tier.

## Catalog concurrency

Add an adapter-level exclusive writer lock and capability handshake. Read-only work may coexist; Photos mutation must have one active writer.

## Generated handoffs and adapter conformance

Generate editor and completion reports from structured receipts. Add synthetic conformance fixtures for readers, inspectors, writers, and verifiers, including idempotence and same-count source-drift failures.
