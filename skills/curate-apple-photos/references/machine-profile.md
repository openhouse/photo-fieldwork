# Local machine profile

Production settings belong in a validated local profile outside Git.

## Create the profile

Copy `config/machine-profile.example.json` to:

```text
~/.config/photo-fieldwork/profile.json
```

Replace every placeholder. Never commit the populated file.

The profile records:

- a private, local, non-File-Provider workspace root;
- the Photos database path used read-only;
- the stable permissioned helper app path and bundle identifier;
- one or more source identifiers, expected counts, and compact inventories;
- existing protected root, private-review, and audit folder identifiers.

## Preflight

Run both checks before retrieval:

```bash
photo-fieldwork profile check
python3 scripts/photo_archive_bridge.py doctor
python3 scripts/photo_archive_bridge.py probe
```

`profile check` validates local paths and free space. `doctor` validates the adapter files and inventory contract. `probe` launches the stable app for an operational, read-only Photos authorization and source-count check with network access disabled.

Do not rebuild, rename, or replace an installed helper during a production run. macOS permission follows the signed app identity, not the source directory.

## Source contracts

Use a named profile source. A source may be a Photos album identifier or `visible-library-stills://v1`. Record the live source count in preflight and refuse a mismatch later.

## Verification boundary

Verification opens the live Photos database in a WAL-aware, read-only transaction, extracts only relevant source checks and target album memberships into compact evidence, then reopens that evidence with `mode=ro&immutable=1` and `PRAGMA query_only=ON`.

Never issue `INSERT`, `UPDATE`, `DELETE`, or schema changes against Photos SQLite.
