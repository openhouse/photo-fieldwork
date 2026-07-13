# Safety model

## Data minimization

- Inventory only the source corpus needed for the run.
- Use previews rather than originals when possible.
- Keep exact coordinates out of editor-facing manifests.
- Store generalized safety flags, not detected private text.
- Never publish archive manifests containing private local paths or named-person associations without review.
- Create run workspaces with mode `0700` and writer ID files with mode `0600`.
- Define a retention decision for previews, contact sheets, review storage, and HOLD manifests.

## Prohibited by default

- Direct writes to Photos SQLite.
- Deleting, hiding, editing, retagging, moving, or importing assets.
- Uploading pixels, faces, OCR, locations, or manifests to a cloud service.
- Identifying unnamed people.
- Inferring age, race, health, sexuality, or other sensitive traits.
- Using aesthetic models to rank unrelated photographs.

## Safety hold contract

Any item marked `safety_status=hold`, hidden, or missing is excluded before ranking. Validation fails if a hold ID appears in the proposed master.

Items marked `needs-review` or `unavailable` are also ineligible for automatic
master selection. Human review may clarify their state, but selection logic does
not silently treat ambiguity as clearance.

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

## Publication boundary

Safety clearance does not establish rights, consent, caption accuracy, or public
readiness. Those states remain separate. Public projections are allowlisted and
must not contain archive UUIDs, People associations, private paths, exact
locations, OCR, HOLD membership, or safety reasons.

Read [the threat model](threat-model.md) before a production archive run.
