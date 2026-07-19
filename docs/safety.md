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

Any item marked `safety_status=hold`, `machine-suspected`, or `human-confirmed-hold`, hidden, or missing is excluded before ranking. Validation fails if a hold ID appears in the proposed master.

The HOLD set should be private and access-controlled. It is not an editor album and must not be exported casually.

HOLD is a lifecycle, not publication permission:

- `machine-suspected`: local automated review found a generalized risk signal;
- `human-confirmed-hold`: a reviewer confirmed private or sensitive visible content;
- `clear`: eligible for the private editor field only;
- `publication-review-required`: considered separately from field selection;
- `publication-approved`: granted only outside automated selection, with owner review.

The proposed master defaults to `publication_status=not-approved`.

Freeze a post-inspection, pre-clearance safety baseline before human review changes any machine-suspected state. Release audit binds that baseline, requires every selected asset to be present in it, and requires a matching asset-specific human `safety-cleared` event for each transition to `clear`. A current CSV cannot erase that history.

## Local derivatives

Private previews and manifests should live under a mode-700 run workspace. Raw OCR must remain ephemeral. Define retention and cleanup with the archive owner; do not automatically delete HOLD evidence or prior versions. The static review workspace starts no server and makes no network request.

## Catalog adapter contract

A production adapter must:

1. Confirm the intended library and source album.
2. Accept stable IDs from a reviewed plan.
3. Create only folders, albums, and membership.
4. Run a ten-item write test first.
5. Be idempotent and resumable.
6. Emit a structurally complete receipt with completion time, exact folder and album identifiers, and counts.
7. Bind the receipt to the exact plan SHA-256.
8. Carry the sealed release candidate, catalog plan, and master-assignment identities into the plan and receipt.
9. Reject an incompatible writer-plan schema before requesting authorization or mutating the catalog.
10. Support independent read-only verification of source and destination membership digests.

If an adapter cannot meet all ten conditions, it is not production-ready.
