# Local Apple Photos machine profile

The public repository contains contracts, not a person's archive locators.
Keep application paths, Photos database paths, protected folder identifiers,
source identifiers, and verified library counts in a private JSON profile.

## Configure

1. Copy `machine-profile.example.json` outside the repository to:
   `~/.config/photo-fieldwork/apple-photos.json`.
2. Replace every example path, bundle identifier, source value, and folder
   value with locally verified information.
3. Set the directory to mode `0700` and the profile to mode `0600`.
4. Freeze the intended source with `freeze_source_profile.py` and copy its
   count and identifier digest into `default_source`.
5. Run the static check, then the zero-image live authorization check:

```bash
python3 scripts/photo_archive_bridge.py doctor
python3 scripts/photo_archive_bridge.py doctor --live
```

Set `PHOTO_FIELDWORK_PROFILE` or pass `--profile` before the subcommand to use
another profile:

```bash
python3 scripts/photo_archive_bridge.py \
  --profile /private/path/apple-photos.json \
  doctor
```

## Profile contract

The profile declares:

- the stable permissioned app bundle and expected bundle identifier;
- the durable private run root;
- the compact retrieval inventory;
- the live Photos database used only through read-only snapshots;
- the default frozen source contract;
- the existing or title-discovered root, private-review, and audit folders.

An identifier may be `null` when the helper should resolve a unique child by
title or create it. For protected existing folders, a verified identifier is
safer because it prevents an unexpected same-title match.

Never commit the completed profile. Never put People names, exact locations,
private album titles, credentials, or raw archive records in the public
repository.

## Permissioned helper

Always launch plans through the configured `.app` bundle so macOS uses its
stable Photos permission identity. Replacing or rebuilding the installed app
is a separate explicit operation because macOS may request authorization again.

Read [the helper authorization guide](../../../docs/helper-authorization.md)
before diagnosing a permission failure. The live doctor retains a private,
nonce-bound receipt and performs no Photos catalog write.

Supported operations are:

- `inspect-local-images`: local PhotoKit retrieval, optional Vision labels and
  face counts, ephemeral OCR safety flags, and optional private previews;
- snapshot plans: create folders and albums, then add existing membership only.

## Photos database safety

Inventory and verification tools create a consistent backup from a live
`mode=ro`, `query_only=ON` connection so committed WAL content is included.
They then open only the frozen backup with `mode=ro&immutable=1` and
`query_only=ON`.

Never issue `INSERT`, `UPDATE`, `DELETE`, schema changes, or a writable
connection against a Photos database.
