# Apple Photos recovery guide

Every recovery begins with two rules: do not alter the source, and do not
delete a prior version to make a rerun easier.

## Authorization denied or stale

1. Run `photo_archive_bridge.py doctor` with the private machine profile.
2. Confirm the configured app path, bundle identifier, executable hash, and
   Photos database availability.
3. Open macOS Privacy and Security settings and review Photos access for the
   configured app.
4. Do not reset authorization or replace the app bundle automatically.
5. Rerun the same plan after the human authorization action. The plan is
   idempotent.

## External Photos library unavailable

Stop. Reconnect and unlock the expected volume, then rerun `doctor`. Do not
point the profile at another library merely because it is available.

## Source count or digest changed

Stop before inspection or writing. Preserve the run and decide whether the
change was expected. An expected change requires a new versioned run and newly
frozen source contract. Never edit the old contract in place.

## Interrupted inspection

Rerun the same inspection plan. The helper validates existing JSONL rows,
recomputes prior totals, skips exact completed identifiers, and continues.
Malformed or duplicate rows block the resume and require a reviewed repair of
the private inspection manifest.

## Corrupt or missing preview

Run `verify_preview_exports.py`. A failure blocks visual evaluation. Rerunning
the same inspection plan revalidates existing previews and replaces a corrupt
preview. Do not mark the item visually reviewed from metadata alone.

## Incomplete album batch

Rerun the identical plan. The writer refuses unexpected membership, adds only
missing planned membership, verifies each batch, and emits a refreshed
receipt. Do not create a same-title replacement album.

## Receipt absent or stale

Treat the operation as unverified. Inspect the helper log, rerun the same plan,
and require a newly modified receipt. Never infer completion from an album
title or visible count alone.

## Active Photos WAL

Use `verify_photos_commit.py --photos-db ...`. The verifier creates a
WAL-aware read-only snapshot automatically. Do not copy only `Photos.sqlite`
and do not issue a checkpoint against the Photos library.

## Insufficient candidates for a quota

Read the infeasibility diagnostic. Revise the retrieval terms, the view quota,
or the editorial taxonomy, then create a new proposal and evaluation. Do not
fill a project view with generic context solely to reach a number.

## Temporary snapshot after failure

The snapshot context removes its private temporary database on handled exit.
If a process was killed, inspect only the configured private snapshot
directory and remove the orphan after confirming no verifier is running.
Never run cleanup against the Photos library directory.
