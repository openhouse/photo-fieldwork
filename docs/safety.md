# Safety model

## Data minimization

- Inventory only the source corpus needed for the run.
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

## Public handoff contract

Public export is destination-specific and allowlist-only. A cleared row needs
positive rights, consent, claim, human safety, and editorial states plus an
authorized reviewer, date, alt text, and credit. The exported package uses a
salted opaque ID and omits source UUIDs, filenames, paths, People associations,
coordinates, raw OCR, and private review actors. Claimed clearances with an
unresolved gate fail closed into a private remediation report.

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
