# Changelog

## Unreleased

### Evaluation

- Expanded the skill bank from four prompts to twelve evidence-gradeable,
  adversarial scenarios spanning recovery, freshness, source identity,
  per-view quality, safety, artifact binding, catalog verification, privacy,
  and provenance.
- Added a recursive eval hill-climb protocol and structural regression tests.
- Promoted observed eval failures into executable gates for unique evaluation
  UUIDs, sampled requested views, exact view quotas, ordered run phases, unique
  attempt IDs, and nonblank editorial evidence.
- Clarified that active run configuration, not documentation defaults, controls
  numeric release thresholds.

## 0.2.0 - 2026-07-13

### Added

- Whole-visible-library Apple Photos source profile and inventory builder.
- Frozen source snapshots with sorted-membership SHA-256 verification.
- Append-only run events with derived status and next-phase commands.
- Per-view evaluation, decisive-sample, and uncertainty gates.
- Provenance-aware safety states and explicit human review tooling.
- Fresh inspection delta and conflict-safe inspection merge tools.
- Preview decode verification and corrupt-preview contact-sheet handling.
- Content-addressed production plans and immutable write-attempt receipts.
- Independent verification of source digests, folder topology, plan integrity,
  exact membership, and master/HOLD disjointness.

### Changed

- The safety album is now named `SAFETY HOLD`; automated and human decisions are
  no longer represented as one automated state.
- Whole-library counts are observed per run instead of hard-coded globally.
- The public case study now documents the three-round whole-library v04-J run.
- Removed the previously advertised but unenforced `exploratory_fraction` and
  `event_cluster` fields from the supported contract.

### Privacy

- No private photographs, asset identifiers, People manifests, OCR, contact
  sheets, local paths, or HOLD records are included in this release.
