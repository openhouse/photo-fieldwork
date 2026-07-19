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

Only `safety_status=clear` or an attributed `clear_for_editor_field` decision may enter ranking. The latter requires a non-empty `safety_clearance_actor` and `safety_clearance_authority=human-editor`. Missing state, `review_required`, automatic HOLD, human HOLD, `editor_only`, hidden, and unavailable material fail closed. Validation independently rejects a non-clear state even when a hold manifest is incomplete.

An unresolved state propagates transitively through perceptual-cluster, duplicate-group, duplicate-group-id, and burst-group relationships. This is conservative protection against another frame carrying the same sensitive content. Event, person, location, and date associations never propagate a hold by themselves.

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
8. Verify the exact source-membership fingerprint and required helper revision before mutation.
9. Bind the receipt to a fresh execution nonce and the SHA-256 of the exact plan bytes executed.

If an adapter cannot meet all nine conditions, it is not production-ready.

## Public derivative contract

An editor field is never publication permission. Public projection requires separate explicit values for rights, consent, factual-claim support, safety, and publication approval. The public manifest contains only `public_id`, repository-relative derivative path, alt text, caption, credit, and view label. Source UUIDs, People associations, raw OCR, coordinates, and private evidence remain in the private workspace.
