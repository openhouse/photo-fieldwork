# Apple Photos integration

The included practice CLI does not read or write Apple Photos. Production integration should be implemented as adapters around the same manifests and invariants.

## Recommended read path

Resolve each run through a versioned source manifest. The included permissioned helper supports an album identifier and `visible-library-stills://v1`, which means visible, non-hidden, non-trashed still photographs in the primary library scope. Record the observed source membership digest, count, predicate version, and fingerprint before retrieval.

Use a documented tool such as `osxphotos` or a read-only library API to inventory:

- stable asset UUIDs;
- album and folder membership;
- existing People & Pets associations;
- favorite and edit status;
- dates and coarsened places;
- duplicate and burst groups;
- local/cloud/missing state;
- Apple aesthetic scores when available.

Use the `retrieval` inventory profile by default: retain `has_location` or coarse place context but omit exact coordinates and the local Photos database path. The `debug` profile is private-operational and opt-in. Read installed local help before assuming command syntax. Do not upgrade tools during a production run.

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

Keep the source scope and every earlier version unchanged. Every write plan must include the source fingerprint, `proposal_id`, `master_sha256`, `hold_sha256`, release class, exact `plan_sha256`, and required helper revision.

## Reusable permission helper

For repeated local work, a small signed macOS application with a stable bundle identifier can request Photos permission once and execute reviewed album-membership plans. Renaming or changing the bundle identifier creates a new permission identity. Revision B plans require the reviewed helper revision and schema version; an older installed helper must fail before mutation. `photo_archive_bridge.py doctor` checks the capability handshake.

## Verification

After writing, compare planned and actual memberships through an independent read-only query. Verify:

- exact album counts;
- no missing IDs;
- no unexpected IDs;
- no members outside the source;
- no HOLD overlap;
- source membership digest and count unchanged;
- receipt and plan source, proposal, master, hold, plan, release, and helper fields match.
