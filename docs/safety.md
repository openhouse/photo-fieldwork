# Safety model

## Data minimization

- Inventory only the source corpus needed for the run.
- Use previews rather than originals when possible.
- Keep exact coordinates out of editor-facing manifests.
- Store generalized safety flags, not detected private text.
- Never publish archive manifests containing private local paths or named-person associations without review.
- Label artifacts `private-operational`, `review-sensitive`, or `public-safe`. Use the
  public-report linter before human publication review.

## Prohibited by default

- Direct writes to Photos SQLite.
- Deleting, hiding, editing, retagging, moving, or importing assets.
- Uploading pixels, faces, OCR, locations, or manifests to a cloud service.
- Identifying unnamed people.
- Inferring age, race, health, sexuality, or other sensitive traits.
- Using aesthetic models to rank unrelated photographs.

## Safety hold contract

Any item whose safety status begins with `hold`, is `unavailable`, hidden, or missing is
excluded before ranking. A preview that is missing, corrupt, or undecodable is unavailable,
not clear. Human-sensitive machine labels such as `child` or `teen` trigger review rather
than asserting an age or identity. Validation fails if any such ID appears in the master.

The HOLD set should be private and access-controlled. It is not an editor album and must not be exported casually.

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
