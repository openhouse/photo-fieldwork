# Jamie's local photo system

Use these as defaults, then verify them live.

## Permissioned helper

- App: `/Applications/Jamie Photo Archive.app`
- Executable: `/Applications/Jamie Photo Archive.app/Contents/MacOS/JamiePhotoArchive`
- Bundle identifier: `art.jamieburkart.jamiephotoarchive`
- Reviewed Revision B helper source reports app version 3.0 and plan schema 2. Run `doctor` against the installed app; a version label alone is not sufficient.
- Supported operations:
  - `inspect-local-images`: local PhotoKit image retrieval, Vision labels, face counts, ephemeral OCR-based safety flags, optional private previews;
  - snapshot plans: create folders/albums and add existing asset membership only.

Always launch plans through the app bundle so macOS uses its stable Photos permission identity:

```bash
open -W -n "/Applications/Jamie Photo Archive.app" --args --plan /absolute/path/plan.json
```

## Source profiles

The machine has used both an album-scoped source and `visible-library-stills://v1`. Neither is a universal default. Every run must name a schema-version-1 source manifest. The manifest, not this document, is authoritative for identifier, predicate, count, membership digest, and fingerprint.

Use `config/local-profile.json` for private machine paths and protected folder identifiers. It is gitignored. Start from `config/local-profile.example.json` and keep the real profile out of public reports.

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
- Run `doctor --profile config/local-profile.json --source-manifest RUN/source-manifest.json` before a production run.
