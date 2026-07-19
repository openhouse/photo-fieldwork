# Safety model

## Data minimization

- Inventory only the source corpus needed for the run.
- Use previews rather than originals when possible.
- Keep exact coordinates out of editor-facing manifests.
- Store generalized safety flags, not detected private text.
- Never publish archive manifests containing private local paths or named-person associations without review.
- Keep populated machine profiles outside Git.
- Extract compact verification evidence instead of copying the full catalog database.

## Prohibited by default

- Direct writes to Photos SQLite.
- Deleting, hiding, editing, retagging, moving, or importing assets.
- Uploading pixels, faces, OCR, locations, or manifests to a cloud service.
- Identifying unnamed people.
- Inferring age, race, health, sexuality, or other sensitive traits.
- Using aesthetic models to rank unrelated photographs.

## Safety hold contract

Any item marked `safety_status=hold`, hidden, or missing is excluded before ranking. HOLD propagates transitively through exact duplicate, perceptual-match, and burst relations so a crop, edit, or sequence neighbor cannot evade protection. Validation fails if a hold ID appears in the proposed master.

The HOLD set should be private and access-controlled. It is not an editor album and must not be exported casually.

Historical HOLD state persists across runs. A changed album label or retrieval term cannot automatically return a held asset to eligibility. Known visible false positives are also retained as regression controls.

Publication clearance is default closed and item specific. Library ownership, a passing editor-field evaluation, or advice from an imagined panel does not establish rights, consent, collaborator approval, caption accuracy, credit, alt text, or destination suitability.

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
