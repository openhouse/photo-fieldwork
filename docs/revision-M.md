# Revision M implementation

Revision M turns the successful whole-library production path into reviewed
project capability. It is the `0.2.0` boundary, not a claim that Photo Fieldwork
performs a final publication edit.

## Implemented

- Album and visible-library still sources share one PhotoKit contract.
- Source count and a non-reversible identifier digest freeze the run boundary.
- `freeze_source_profile.py` creates that contract from a WAL-aware read-only
  snapshot without exporting raw asset identifiers.
- Personal paths, source values, and protected folder identifiers move to a
  private mode-`0600` machine profile outside git.
- Whole-library inventory generation has no fixed personal count.
- Live Photos SQLite reads use `mode=ro`, `query_only=ON`, and SQLite backup so
  committed WAL content enters a private consistent snapshot.
- Independent verification opens only that frozen snapshot with
  `mode=ro&immutable=1` and `query_only=ON`.
- Run roots are mode `0700`; private manifests, receipts, reports, previews, and
  profiles are mode `0600`.
- Inspection resume reconstructs all receipt totals from prior JSONL rows and
  rejects malformed or duplicate rows.
- Existing previews are decoded before reuse; the verifier checks exact
  export state, decodability, dimensions, EXIF absence, symlinks, and modes.
- Retrieval records aggregate signal classes without exposing matched private
  terms. It supports excluded album terms and required diversity outside a
  prior corpus.
- Retrieval hypotheses and editorial assignment are separate fields.
- Deterministic constrained maximum flow satisfies exact view quotas and emits
  infeasibility diagnostics.
- Exact membership and assignments generate `master_sha256` and `proposal_id`.
- Evaluation is bound to that proposal and enforces per-view coverage,
  decisive-sample, precision, uncertainty, and Wilson interval reporting.
- Catalog plans require a passing evaluation for the exact proposal.
- Ordered run phases maintain a SHA-256 artifact ledger.
- First and second app receipts can be compared for idempotence.
- `make check` validates the core tests, skill scripts, JSON contracts, and
  Swift helper.

## Intentionally deferred

The following recommendations remain appropriate for later, separately
reviewable releases:

- a static local browser review interface;
- explicit HOLD-release and publication-approval commands;
- fresh versus validated-cache policy and cache invalidation;
- sequence and event-neighborhood review manifests;
- a full editor-to-publication shortlist schema;
- catalog adapters beyond Apple Photos;
- a signed helper release and installation pipeline.

These are deferred to keep the `0.2.0` change focused on the production path
that was actually exercised and verified.

## Migration

1. Create the private machine profile from the tracked example.
2. Rebuild the inventory through a WAL-aware snapshot.
3. Freeze the source count and identifier digest into the profile and run.
4. Recreate evaluation samples because proposal identity now includes exact
   assignments.
5. Pass the final evaluation report when building a catalog plan.
6. Run the ten-item test, production write, idempotent rerun, receipt
   comparison, and independent verification.

Earlier run workspaces remain evidence. Do not rewrite them to the new schema.
