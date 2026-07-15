# Safety model

## Data minimization

- Resolve and fingerprint only the source scope needed for the run.
- Use the `minimal` or `retrieval` inventory profile unless a private-operational debug artifact is explicitly required.
- Use previews rather than originals when possible.
- Keep exact coordinates out of editor-facing manifests.
- Store generalized safety flags, not detected private text.
- Never publish archive manifests containing private local paths or named-person associations without review.
- Label artifacts `private-operational`, `review-sensitive`, or `public-safe`. Run the public-report linter before human publication review.

## Prohibited by default

- Direct writes to Photos SQLite.
- Deleting, hiding, editing, retagging, moving, or importing assets.
- Uploading pixels, faces, OCR, locations, or manifests to a cloud service.
- Identifying unnamed people.
- Inferring age, race, health, sexuality, or other sensitive traits.
- Using aesthetic models to rank unrelated photographs.

## Typed safety contract

Revision B recognizes these primary states:

- `clear-automated`: automation found no configured hold signal; this is not human publication approval.
- `needs-human-review`: dignity, consent, or contextual safety requires a person.
- `cleared-human`: a person resolved the review for the declared editor-field purpose.
- `hold-automated`: a conservative detector quarantined the item.
- `hold-human`: a person explicitly withheld the item.

Legacy `clear`, `needs-review`, and `hold` remain readable. Only states listed in `eligible_safety_states` may enter selection. Hidden, missing, held, and unresolved review rows are excluded before ranking. Validation and plan generation fail if an ineligible state appears in the proposed master.

The HOLD set and preview workspace should be private and access-controlled. Versioned run directories are created owner-only. Raw OCR is not persisted. A public export needs separate allowlisting and human review.

## Catalog adapter contract

A production adapter must:

1. Confirm the intended library and source album.
2. Accept stable IDs from a reviewed plan.
3. Create only folders, albums, and membership.
4. Run a ten-item write test first.
5. Be idempotent and resumable.
6. Emit a receipt bound to source, proposal, master, holds, plan hash, release class, and helper revision.
7. Support independent read-only verification.

If an adapter cannot meet all seven conditions, it is not production-ready.
