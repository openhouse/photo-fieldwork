# Apple Photos integration

The included practice CLI does not read or write Apple Photos. Production integration uses a populated local machine profile and adapters around the same manifests and invariants.

Machine-specific paths, source counts, app identities, and protected folder identifiers must remain outside Git.

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

Use a reviewed PhotoKit, PhotoScript, AppleScript, or documented `osxphotos` album-writing adapter. Select the adapter during preflight and record its capability version. Never issue SQL mutations against the Photos database.

The only default writes are:

- create a version folder;
- create named albums;
- add existing stable IDs to those albums.

Keep the wide source album and every earlier version unchanged.

## Reusable permission helper

For repeated local work, a small signed macOS application with a stable bundle identifier can request Photos permission once and execute reviewed album-membership plans. Renaming or changing the bundle identifier creates a new permission identity. The helper must support an operational read-only probe, declare its capability version, and emit an exact receipt.

## Verification

After writing, open the live database in one WAL-aware, read-only transaction and extract only relevant source checks and target memberships into a compact evidence database. Reopen that evidence with `mode=ro&immutable=1` and `PRAGMA query_only=ON`, then verify:

- exact album counts;
- no missing IDs;
- no unexpected IDs;
- no members outside the source;
- no HOLD overlap;
- source count unchanged.
- plan and receipt file checksums;

This avoids treating an immutable connection to a live WAL-backed database as current, and avoids copying the entire Photos database for each verification.
