# Safety model

## Data minimization

- Resolve and fingerprint only the source scope needed for the run.
- Use the `minimal` or `retrieval` inventory profile unless a private-operational debug artifact is explicitly required.
- Use previews rather than originals when possible.
- Keep exact coordinates out of editor-facing manifests.
- Store generalized safety flags, not detected private text.
- Never publish archive manifests containing private local paths or named-person associations without review.
- Create private run directories with mode `0700` and sensitive files with mode
  `0600`.
- Keep the completed machine profile outside git.

## Prohibited by default

- Direct writes to Photos SQLite.
- Deleting, hiding, editing, retagging, moving, or importing assets.
- Uploading pixels, faces, OCR, locations, or manifests to a cloud service.
- Identifying unnamed people.
- Inferring age, race, health, sexuality, or other sensitive traits.
- Using aesthetic models to rank unrelated photographs.

## Safety hold contract

Any item marked `safety_status=hold`, hidden, or missing is excluded before ranking. Validation fails if a hold ID appears in the proposed master.

The HOLD set should be private and access-controlled. It is not an editor album and must not be exported casually.

Use separate states for automated safety screening, human editor-field review,
and publication review. `clear-automated` means only that the configured local
detectors did not place the item in HOLD. It is never publication permission.

Every selected row defaults to `publication-review-required`. Selection into a
master or Photos album cannot change that state.

## Publication derivative contract

The private editor field and a public handoff are different datasets. A row may
enter a public derivative only when independent human review records all of:

- publication clearance for one named destination;
- verified ownership or a license for that specific use;
- scoped consent or an explicit not-applicable decision;
- a visible-only, provenance-backed, or caption-review claim status.

`photo-fieldwork public-handoff` replaces the private Photos UUID with a salted
public identifier and emits only allowlisted editorial fields. It skips
unreviewed rows and blocks when a row claims publication readiness but any gate
is missing or scoped to another destination. This command minimizes a handoff;
it does not grant rights, consent, or publication approval.

## Catalog adapter contract

A production adapter must:

1. Confirm the intended library and source album.
2. Accept stable IDs from a reviewed plan.
3. Create only folders, albums, and membership.
4. Run a ten-item write test first.
5. Be idempotent and resumable.
6. Emit a receipt with exact identifiers and counts.
7. Support independent read-only verification.

If an adapter cannot meet all seven conditions, it is not production-ready.
