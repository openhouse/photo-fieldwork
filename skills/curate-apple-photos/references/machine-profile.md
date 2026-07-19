# Private local profile

Photo Fieldwork keeps machine paths, source identifiers, protected folder identifiers, and permissioned-app identity outside the public repository.

## Create the profile

Copy `config/local-profile.example.json` to a private location outside the repository, fill in the local values, and keep the file out of source control. The default lookup is `.photo-fieldwork.local.json`; `PHOTO_FIELDWORK_PROFILE` or `--profile` may point elsewhere.

The profile declares:

- private run workspace root;
- read-only Photos database path used by inventory and verification adapters;
- stable permissioned application path and optional bundle identifier;
- private inventory database path;
- source kind, identifier, and expected count;
- existing root, private-review, and audit folder identifiers.

The profile itself is never copied into a run. `photo-fieldwork run` records only its SHA-256 so a changed profile cannot silently resume an existing run.

## Source choices

Use `kind: album` for a frozen source album. Use `kind: visible-library-stills` with identifier `visible-library-stills://v1` when the brief explicitly requires the whole visible still-photo library.

Count is a human-readable preflight, not source identity. Build or refresh the private inventory so its `meta` table contains `source_membership_sha256`. The writer plan, writer receipt, and independent verifier must bind to the same digest.

## Permissioned helper

Launch plans through the configured application bundle so macOS uses its stable Photos permission identity:

```bash
python3 scripts/photo_archive_bridge.py run-plan \
  --profile /absolute/path/to/.photo-fieldwork.local.json \
  --plan /absolute/path/to/plan.json
```

The helper supports only:

- local PhotoKit image retrieval with network access disabled;
- optional local Vision classification, face count, and ephemeral OCR-derived safety flags;
- creation of folders and albums;
- addition of existing asset membership.

It must not edit, delete, move, retitle, upload, or directly mutate Photos SQLite.

## Read-only verification

Open Photos SQLite with URI `mode=ro&immutable=1` and `PRAGMA query_only=ON`. Never issue `INSERT`, `UPDATE`, `DELETE`, schema changes, or a non-read-only connection.

Run `photo_archive_bridge.py doctor --profile ...` before every production session. A source count, profile digest, or inventory digest mismatch is a stop condition, not a warning.
