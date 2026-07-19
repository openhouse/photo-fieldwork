# Apple Photos integration

The included practice CLI does not read or write Apple Photos. Production integration should be implemented as adapters around the same manifests and invariants.

## Recommended read path

Resolve each run through a versioned source adapter. The included permissioned helper supports a specific album identifier and `visible-library-stills://v1`, which means visible, non-hidden, non-trashed still photographs in the primary library scope. Record the observed source count and fingerprint before retrieval.

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

## Frozen source profiles

Production runs may use either one immutable source album or the visible,
non-hidden, non-trashed still-photo library. Initialization freezes the source
identifier, exact count, and SHA-256 digest of sorted asset identifiers. The
digest proves source continuity without exposing the identifiers themselves.

Personal paths, source IDs, protected folder IDs, and counts belong in the
private machine profile, never tracked source.

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

Keep the source scope and every earlier version unchanged. Every write plan must include the `proposal_id` and `master_sha256` from a passing final evaluation.

## Reusable permission helper

For repeated local work, a small signed macOS application with a stable bundle identifier can request Photos permission once and execute reviewed album-membership plans. Renaming or changing the bundle identifier creates a new permission identity. The helper must display the plan ID, source count, intended mutations, and final receipt.

## Verification

After writing, compare planned and actual memberships through an independent read-only query. Verify:

- exact album counts;
- no missing IDs;
- no unexpected IDs;
- no members outside the source;
- no HOLD overlap;
- source count unchanged.

Do not open a live Photos database with `immutable=1` and assume that it is
current. Immutable SQLite access can ignore committed content still present in
the write-ahead log. Photo Fieldwork first opens the live database with
`mode=ro` and `query_only=ON`, uses SQLite backup to create a consistent
user-private snapshot, closes the live connection, and then opens the frozen
snapshot with `mode=ro&immutable=1` and `query_only=ON`.

The snapshot is removed after verification unless the operator explicitly
keeps it for a documented audit. No direct Photos SQLite write is permitted.
