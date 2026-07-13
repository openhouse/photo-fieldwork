# Revision H implementation note

Revision H turns lessons from a whole-library production run into reusable protocol guarantees.

## Implemented

- Versioned source profiles and source fingerprints.
- Whole visible-library inventory, PhotoKit fetch, and independent verification support.
- View-order-independent candidate reservation before global truncation.
- Outside-prior floors with deterministic feasibility failure.
- Typed retrieval index, visible evidence, source provenance, and editor hypothesis fields.
- Canonical UUID and boolean normalization.
- Separate source, inspected, and conservative known face counts.
- Declarative relational safety propagation with generalized append-only decisions.
- Policy-fingerprinted inspection ledgers and indexed preview paths.
- Preview decode verification and corrupt-preview contact-sheet handling.
- Overall and per-view evaluation release gates.
- Required visible reasons, safety states, error categories, round IDs, and reviewer lenses.
- Deterministic feedback application with cascading replacement review.
- Cross-UUID duplicate review using exact preview hashes, adapter-provided perceptual hashes, or complete file signatures.
- Exact quota, still-only, pixel-availability, HOLD-disjointness, replacement, and duplicate validation gates.
- Membership-plan linting and deterministic plan digests.
- Bridge refusal of unlinted, unsealed, or modified plans.
- Append-only run-state transitions and next-phase reporting.
- Preserved rerun receipts and explicit idempotence comparison.
- Human-readable and JSON independent-verification reports.
- Artifact-derived completion reporting.
- Public-safe whole-library benchmark documentation.
- Expanded regression coverage and JSON schema contracts.

## Deliberate boundaries

- Photo Fieldwork still does not automate taste, consent, provenance research, or publication clearance.
- Perceptual hashing remains an adapter input so the standard-library core does not acquire an image dependency. Exact local preview hashing is built in.
- The editor experience remains contact-sheet and manifest based. A later local review interface should consume these same artifacts rather than introduce another data model.
- The permissioned Apple Photos bridge remains a named integration; the package core and source-profile contracts are portable.

These boundaries are product decisions, not missing claims. Revision H concentrates automation around evidence, safety, reproducibility, and release integrity while keeping editorial authority human.
