# Apple Photos integration

The included practice CLI does not read or write Apple Photos. Production integration is an adapter around the same manifests and invariants. Keep machine paths, protected collection identifiers, and mutable source counts in an untracked local profile based on `config/source-profile.example.json`.

## Recommended read path

Use a documented tool such as `osxphotos` or a read-only library API to inventory:

- stable asset UUIDs;
- album and folder membership;
- existing People & Pets associations;
- favorite and edit status;
- dates and coarsened places;
- duplicate and burst groups;
- local/cloud/missing state;
- Apple aesthetic scores when available.

Read installed local help before assuming command syntax. Do not upgrade tools during a production run.

## Aesthetic scores

Apple aesthetic scores may help choose among photographs already known to be near-identical members of the same burst or duplicate cluster. They should come after the default burst pick, favorite, and edited status as appropriate to the archive owner.

Do not use the score to rank unrelated photographs, decide emotional truth, or define professional relevance.

## People

Existing named-person associations represent years of archive labor and can be crucial professional context. Preserve and use them as retrieval and diversity signals. Do not create new face identifications or expose a people manifest publicly without consent review.

## Write path

Use PhotoKit, PhotoScript, AppleScript, or a documented `osxphotos` album-writing interface. Never issue SQL mutations against the Photos database.

The only default writes are:

- create a version folder;
- create named albums;
- add existing stable IDs to those albums.

Keep the selected source and every earlier version unchanged. Supported source contracts include `album://LOCAL_IDENTIFIER` and `visible-library-stills://v1`; freeze the observed source count into each run rather than treating a historical count as permanent.

## Reusable permission helper

For repeated local work, a small signed macOS application with a stable bundle identifier can request Photos permission once and execute reviewed album-membership plans. Renaming or changing the bundle identifier creates a new permission identity. The helper must display the plan ID, source count, intended mutations, and final receipt. The Python launcher verifies the plan digest before launch and requires the same digest in the app receipt.

Plan schema v2 and digest-bearing receipts require Jamie Photo Archive 3.0. `photo_archive_bridge.py doctor` refuses production work when the installed helper does not meet that contract. Rebuilding or replacing the stable permissioned app remains an explicit local installation step.

## Verification

After writing, compare planned and actual memberships through an independent read-only query. Verify:

- exact album counts;
- no missing IDs;
- no unexpected IDs;
- no members outside the source;
- no HOLD overlap;
- source count unchanged.
