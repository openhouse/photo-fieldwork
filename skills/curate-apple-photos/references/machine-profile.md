# Jamie's local photo system

Use these as defaults, then verify them live.

## Permissioned helper

- App: `/Applications/Jamie Photo Archive.app`
- Executable: `/Applications/Jamie Photo Archive.app/Contents/MacOS/JamiePhotoArchive`
- Bundle identifier: `art.jamieburkart.jamiephotoarchive`
- Installed app version reported on 2026-07-10: 1.0. Capabilities and stable bundle identifier are authoritative; do not replace the app merely for a version-label mismatch.
- Supported operations:
  - `inspect-local-images`: local PhotoKit image retrieval, Vision labels, face counts, ephemeral OCR-based safety flags, optional private previews;
  - snapshot plans: create folders/albums and add existing asset membership only.

Always launch plans through the app bundle so macOS uses its stable Photos permission identity:

```bash
open -W -n "/Applications/Jamie Photo Archive.app" --args --plan /absolute/path/plan.json
```

## Immutable wide source

- Album title: `00 MASTER — PHOTO EDITORS — TARGET 5K`
- Local identifier: `360ED78F-FB05-490A-8FFD-F3CB951D0D0A/L0/040`
- Verified 2026-07-10 count: 124,484 unique still photographs
- Shared compact inventory: `/Users/jburkart/Documents/Jamie-Photo-Archive-2026/shared/wide-corpus.sqlite`
- Inventory contains existing people, albums, labels, places, search text, favorite/edit status, duplicate and burst data, and Apple aesthetic fields.
- The shared inventory is a snapshot. Rebuild or reconcile it when source count or Photos metadata materially changes.

## Whole visible-library source

- Virtual identifier: `visible-library-stills://v1`
- Scope: visible, non-hidden, non-trashed, primary-scope still photographs
- Build a fresh immutable inventory with `scripts/build_visible_library_inventory.py` and pass `--expected-count` from the reviewed source profile.
- The source profile, inventory metadata, PhotoKit fetch, and independent verifier must agree on the exact count. A count change blocks release until reconciled.

## Photos database

- Library: `/Volumes/apple-photos-8tb-external-ssd/Photos Library.photoslibrary`
- Database: `/Volumes/apple-photos-8tb-external-ssd/Photos Library.photoslibrary/database/Photos.sqlite`
- Verification access must use SQLite URI `mode=ro&immutable=1` and `PRAGMA query_only=ON`.
- Never issue `INSERT`, `UPDATE`, `DELETE`, schema changes, or a non-read-only connection.

## Existing protected folders

- Root: `JAMIE PHOTO EDIT — 2026`, identifier `92BBCF49-B077-478D-B9EE-DD94FAAFEAB5/L0/020`
- Private review: `90 PRIVATE REVIEW — DO NOT SHARE`, identifier `1095845F-B6FA-41D0-8A22-D156C3071631/L0/020`
- Audit: `99 WRITE TESTS / AUDIT`, identifier `7F9EB400-C06D-412C-9443-300A2C47CCE7/L0/020`

## Workspaces

- Durable root: `/Users/jburkart/Documents/Jamie-Photo-Archive-2026`
- Workflow source: `/Volumes/16TB_SSD/Sites/photo-fieldwork`
- Reviewed helper source: `/Volumes/16TB_SSD/Sites/photo-fieldwork/integrations/jamie-photo-archive`
- Preserve every version as its own durable workspace and Photos folder.
