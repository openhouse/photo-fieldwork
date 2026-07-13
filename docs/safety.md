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

Only `safety_state=clear_for_editor_field` or the legacy `safety_status=clear` state may enter ranking. `review_required`, `hold_automatic`, `hold_human`, `editor_only`, hidden, missing, and unknown non-empty states fail closed. Validation independently rejects a non-clear state even when a hold manifest is incomplete.

The HOLD set should be private and access-controlled. It is not an editor album and must not be exported casually.

Publication consent is separate from safety state. No editor-field state, album membership, or People association grants permission to publish.

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
