# Apple Photos integration

The included practice CLI does not read or write Apple Photos. Production integration should be implemented as adapters around the same manifests and invariants.

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

## Verification

After writing, compare planned and actual memberships through an independent read-only query. Verify:

- exact album counts;
- no missing IDs;
- no unexpected IDs;
- no members outside the source;
- no HOLD overlap;
- source count unchanged.

### WAL-aware frozen snapshots

Do not assume a direct immutable connection represents the current PhotoKit
state. SQLite's immutable mode intentionally ignores the WAL. Immediately after
a PhotoKit write, the main database file may therefore lack the new album even
though a normal read-only connection and PhotoKit can see it.

Use the two-step verifier:

```bash
python3 skills/curate-apple-photos/scripts/build_verification_snapshot.py \
  --photos-db /path/to/Photos.sqlite \
  --plan RUN/manifests/v01-production-plan.json \
  --receipt RUN/manifests/v01-photo-archive-receipt.json \
  --output RUN/reports/v01-verification.sqlite

python3 skills/curate-apple-photos/scripts/verify_photos_commit.py \
  --photos-db RUN/reports/v01-verification.sqlite \
  --plan RUN/manifests/v01-production-plan.json \
  --receipt RUN/manifests/v01-photo-archive-receipt.json \
  --master RUN/manifests/master.csv \
  --holds RUN/manifests/holds.csv \
  --config RUN/config.json \
  --report RUN/reports/v01-production-verification.md
```

The first command is WAL-aware but read-only. The second command opens the
closed compact snapshot with `mode=ro&immutable=1` and `query_only`. It refuses
the live Photos database, binds the approved plan to the exact supplied
manifest hashes, and fails if a hashed manifest is omitted or changed.
