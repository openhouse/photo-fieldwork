# Apple Photos integration

The included practice CLI does not read or write Apple Photos. Production integration should be implemented as adapters around the same manifests and invariants.

## Source profiles

Every run carries `source.json` with a source kind, canonical identifier, predicate version,
snapshot count, membership fingerprint, sensitivity, and optional inventory path. Supported kinds are a named album, the visible
whole-library still predicate, and synthetic practice data. The whole-library identifier is
`visible-library-stills://v1`.

Build a compact whole-library inventory with:

```bash
python3 skills/curate-apple-photos/scripts/build_visible_library_inventory.py \
  --inventory-profile retrieval \
  --output /private/path/visible-library.sqlite
```

The reader opens Photos with `mode=ro` so current WAL state is visible. `--immutable` is an
expert-only option for a known checkpointed snapshot.

`minimal` omits relation tables and descriptive text; `retrieval` keeps the contextual fields
needed for search while redacting exact coordinates and the database path; `debug` is private
operational output and is the only profile that retains exact coordinates.

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

Keep the wide source album and every earlier version unchanged.

## Reusable permission helper

For repeated local work, a small signed macOS application with a stable bundle identifier can request Photos permission once and execute reviewed album-membership plans. Renaming or changing the bundle identifier creates a new permission identity. The helper must display the plan ID, source count, intended mutations, and final receipt.

The included bridge probes `--capabilities` before running a schema-v2 plan and records the
helper version and plan schema in receipts.

## Verification

After writing, compare planned and actual memberships through an independent read-only query.
The default verifier takes a bounded compact snapshot from a read-only transaction, then
reopens the compact snapshot as immutable. This preserves live WAL visibility without
copying the full Photos database. Verify:

- exact album counts;
- no missing IDs;
- no unexpected IDs;
- no members outside the source;
- no HOLD overlap;
- source count unchanged.
