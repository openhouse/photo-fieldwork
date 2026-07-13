# Changelog

## Revision I - 2026-07-13

### Added

- Versioned visible-library source support and privacy-aware inventory profiles.
- Explicit editorial assignments separate from retrieval hypotheses.
- Frozen proposal IDs and SHA-256-bound evaluation and write plans.
- Per-view evaluation gates, uncertainty limits, confidence intervals, fresh samples, and regression canaries.
- Structured feedback validation and application commands.
- Local perceptual duplicate clustering and indexed contact sheets.
- Preview verification, public-report linting, typed verifier reports, and atomic run-state transitions.
- Regression coverage and GitHub Actions checks.

### Changed

- Configuration schema version 2 is required.
- Eligible rows require `assigned_view`, `assignment_status`, `assignment_reason`, and `assignment_version`.
- Catalog and Apple Photos snapshot plans require a passing matching final evaluation report.

See [the migration guide](docs/revision-I.md) for details.
