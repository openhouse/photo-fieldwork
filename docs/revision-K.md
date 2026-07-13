# Revision K implementation note

Revision K converts lessons from the v04-K whole-library curation into repository contracts.
It is intentionally an operational hardening release, not an attempt to automate taste.

## Implemented

- **Source fidelity:** versioned `source.json` profiles distinguish named albums, the visible
  whole-library still predicate, and synthetic practice data. The bridge and Swift helper
  support schema-v2 whole-library plans and negotiate capabilities before execution.
- **Whole-library inventory:** a WAL-visible, read-only builder creates a compact inventory
  without a machine-specific count assertion and records its predicate and snapshot count.
- **Retrieval provenance:** candidates retain the channels that surfaced them. Exact
  provenance albums, contextual prior corpora, generated-album exclusions, and a bounded
  outside-prior discovery budget are represented separately.
- **Editorial assignment:** retrieval leaves `assigned_view` blank. Pixel review or external
  provenance must supply the assignment, status, and reason before selection can proceed.
- **Redundancy control:** local difference hashes add perceptual clusters before quota selection;
  hashes and pixels remain private and local.
- **Fail-closed pixels:** expected previews are independently decoded. Missing, corrupt, or
  unavailable pixels cannot enter the master. Human-sensitive machine labels trigger review
  without becoming identity or age claims.
- **View-level evaluation:** release gates include per-view decisive precision, coverage,
  uncertainty, visible reasons, error categories, and safety regressions. Follow-up samples
  can target only failed views while preserving round IDs.
- **Write authorization:** exact membership and reviewed assignments produce a stable proposal
  hash. Structured feedback is validated separately, and only a passing full-master audit of
  that same hash can produce a catalog plan.
- **Data minimization:** inventory profiles omit exact coordinates and source paths by default;
  a public-report linter catches common operational leaks before human review.
- **Recoverability:** `photo-fieldwork state status|resume|audit|mark` maintains phase state
  and artifact hashes, detecting changed or missing evidence after an interruption.
- **Independent verification:** the verifier opens the live Photos database read-only with
  WAL visibility, copies only required membership into a bounded temporary database, then
  verifies that compact snapshot as immutable and removes it.
- **Regression coverage:** synthetic tests exercise source contracts, retrieval channels,
  preview corruption, per-view gates, state drift, and WAL-visible album verification.

## Deliberately retained boundaries

- Editorial judgment remains human and pixel-based.
- Vision labels and OCR remain retrieval and safety aids, not factual captions.
- The app writes only folders, albums, and existing membership through PhotoKit.
- The repository does not install or replace the permissioned app automatically. Deploying
  the revised Swift helper remains an explicit, signed local operation because its bundle
  identity controls Photos authorization.
- Run-state commands identify and audit the next phase; they do not automatically execute
  private-library operations.
