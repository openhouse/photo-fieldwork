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
- Existing previews are decoded before reuse; the verifier checks exact export
  state, decodability, dimensions, EXIF absence, symlinks, and modes, then emits
  a complete private digest-bound evidence index.
- Retrieval records aggregate signal classes without exposing matched private
  terms. Per-view score and reason maps are deterministically bounded. Retrieval
  supports configured and derived album exclusions, required diversity outside
  a prior corpus, and generalized event clusters.
- Retrieval hypotheses and editorial assignment are separate fields.
- Deterministic constrained maximum flow satisfies exact view quotas and emits
  infeasibility diagnostics.
- Exact source, configuration, membership, and assignments generate
  `config_sha256`, `master_sha256`, and `proposal_id`.
- Evaluation is bound to that proposal and its deterministic, freshly inspected
  sample; it enforces per-view coverage, decisive-sample, precision,
  uncertainty, and Wilson interval reporting.
- Every evaluated row names a real local inspection artifact whose digest is
  recomputed and bound to the exact round and deterministic sample.
- Catalog plans recompute evaluation from the exact feedback and validation
  from the exact master and HOLD manifest before accepting a release bundle.
- Ordered run phases require unique SHA-256-tracked evidence artifacts; release
  gates must pass and write phases bind the exact plan, receipt, source, and
  evaluation candidate. An untouched ledger reports `NOT-STARTED`, not `PASS`.
- First and second app receipts must represent distinct executions, are
  validated for real identities and hashes, reconciled with the exact plan,
  and only then compared for idempotence against fresh live-catalog evidence.
- Generated write plans are registered by exact digest before launch; each app
  execution is bound to a bridge-generated nonce recorded in its receipt.
- Independent verification checks collection kinds and folder/album parentage,
  and emits candidate-bound machine evidence through a governed `verify-phase`
  command rather than accepting a user-authored PASS marker.
- A private offline workbench accepts only verified previews, uses content-
  derived asset names, omits People, paths, and raw OCR from its visible context,
  and distinguishes named human review from delegated editorial inference.
- A relation-aware split audit blocks UUID, duplicate, burst, event, perceptual,
  and inspection-digest leakage into final holdouts without printing sensitive
  identifiers by default.
- Publication begins with a default-closed clearance ledger. Its separate
  destination-bound projection requires exact rights, consent, claim, safety,
  attribution, and named human approval before emitting an allowlisted row.
- A public synthetic bank exercises 30 adversarial cases through 11 fixture and
  43 allowlisted executable canaries, while keeping human and publication gates
  explicit.
- `make check` validates the core tests, skill scripts, JSON contracts, and
  Swift helper. GitHub Actions runs core checks on Python 3.11 and 3.13 and the
  PhotoKit helper contract on macOS.

## Intentionally deferred

The following recommendations remain appropriate for later, separately
reviewable releases:

- fresh versus validated-cache policy and cache invalidation;
- sequence and event-neighborhood review manifests;
- explicit governed HOLD-release workflow;
- catalog adapters beyond Apple Photos;
- a signed helper release and installation pipeline.

These are deferred to keep the `0.2.0` change focused on the production path
that was actually exercised and verified.

## Migration

1. Create the private machine profile from the tracked example.
2. Rebuild the inventory through a WAL-aware snapshot.
3. Freeze the source count and identifier digest into the profile and run.
4. Recreate evaluation samples because proposal identity now includes exact
   source, policy, assignments, and sample membership.
5. Pass the final feedback, evaluation report, HOLD manifest, and validation
   report when building a catalog plan.
6. Run the ten-item test, production write, idempotent rerun, receipt
   comparison, and independent verification.

Earlier run workspaces remain evidence. Do not rewrite them to the new schema.
