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
- optional explicit paths to the reviewed osxphotos and ExifTool executables;
- the default frozen source contract;
- an optional existing workspace-parent anchor when the writable root is
  nested inside another Photos folder;
- the existing or title-discovered root, private-review, and audit folders.

An identifier may be `null` when the helper should resolve a unique child by
title or create it. For protected existing folders, a verified identifier is
safer because it prevents an unexpected same-title match.

Existing collection identifiers must be complete PhotoKit local identifiers,
including their `/L0/NNN` type suffix. A bare `ZUUID` copied from Photos SQLite
is not a PhotoKit local identifier. The helper rejects it before calling the
PhotoKit fetch API. When bootstrapping a protected workspace, first use
parent-constrained unique-title discovery in a no-new-folder plan, then copy
the typed identifiers from the private receipt into the private profile.

Set `workspace_parent` to an existing title and identifier when `folders.root`
is nested. The standard planner verifies that anchor and makes every version,
private-review, and audit child beneath `folders.root`; it never creates the
anchor. The anchor itself may be nested elsewhere in Photos; its own parent is
outside the governed workspace and is therefore verified as an external anchor
rather than as a top-level folder. Leave `workspace_parent` as `null` only when
the root is a true top-level Photos folder.

Never commit the completed profile. Never put People names, exact locations,
private album titles, credentials, or raw archive records in the public
repository.

Use the optional `tools.osxphotos` and `tools.exiftool` keys to pin reviewed
executables. This avoids accidentally falling back to an older global install.
The capability reporter never prints these paths. Existence alone is not a
passing osxphotos canary; run one bounded private read before retrieval.

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
