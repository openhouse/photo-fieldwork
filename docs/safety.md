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

## Safety-state contract

Safety is separate from editorial relevance:

- `clear_automated`: no automated hold signal; not publication clearance.
- `hold_automated`: quarantined before ranking.
- `review_sensitive`: protected human review required.
- `cleared_editor_private`: human-cleared for a private editor field.
- `cleared_public_candidate`: human-cleared as a candidate for later public editing.
- `restricted_private`: privately retained and excluded from general fields.

Legacy `clear`, `hold`, and `needs-review` values normalize to the corresponding automated states. Automated logic may escalate sensitivity. Only `actor=human-editor` may grant a clearance state. Hidden and missing items enter `hold_automated`. Validation fails if a restricted ID appears in the general master.

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
