# Safety model

## Data minimization

- Inventory only the source corpus needed for the run.
- Use previews rather than originals when possible.
- Keep exact coordinates out of editor-facing manifests.
- Store generalized safety flags, not detected private text.
- Never publish archive manifests containing private local paths or named-person associations without review.

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

## Relational propagation

Some safety meaning is not visible in one frame. A declarative policy may conservatively propagate `needs-review` or HOLD through:

- protected album families;
- pre-existing People associations configured by the archive owner;
- event and sequence clusters;
- exact asset decisions;
- generalized label classes.

Every propagated decision records a rule ID, relation type, generalized reason, and timestamp. Existing human context and source face counts are preserved separately from local detector results; a detector returning zero cannot erase a positive source count. Overrides append a decision rather than rewriting history.

Album membership is not publication permission. Named People metadata remains private archive structure unless separately approved for release.

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
