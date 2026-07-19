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

For whole-library work, `visible-library-stills://v1` means visible, non-hidden,
non-trashed, primary-scope still photographs. The inventory builder records the
count it observes and accepts an optional expected count; it does not hard-code
a previous library size. It also records a SHA-256 digest of sorted source UUID
membership so equal counts with different members do not look identical.

Machine-specific paths and protected identifiers belong in a private profile
conforming to `schemas/profile.schema.json`.

Use `photo_archive_bridge.py init-profile --help` to create a mode-`0600`
profile without editing the public example in place.

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

Before expensive work, launch a `preflight-read-only` plan through the installed
bundle. It checks the authorization state observed by that process, resolves the
source, compares the frozen count, and requests one local 64-pixel sample with
network access disabled. It always attempts to write a diagnostic receipt,
including on failure, and performs no mutation.

On an interrupted inspection, the helper validates existing JSONL rows and
skips their identifiers. Its final receipt aggregates pixel, preview, HOLD, and
unavailable counters across both prior and newly appended rows. Batch-only
counters are not a valid completion receipt.

```bash
python3 skills/curate-apple-photos/scripts/photo_archive_bridge.py \
  doctor --profile /private/path/profile.json --live
```

## Writer backends

PhotoKit is preferred. A fail-closed AppleScript adapter is available for an
explicit fallback when macOS TCC makes the installed PhotoKit identity unusable.
Both consume the same frozen membership plan and reject duplicate target names,
unexpected existing members, duplicate IDs, missing IDs, and wrong final counts.

Render without executing:

```bash
python3 skills/curate-apple-photos/scripts/applescript_writer.py \
  --plan RUN/manifests/production-plan.json \
  --script RUN/scripts/production.applescript \
  --id-directory RUN/private-writer-ids
```

Execution requires the additional `--execute` flag. The receipt records the
backend and script hash. The AppleScript writer does not claim to verify the
source independently; live preflight and post-write read-only verification
remain required.

## Verification

After writing, compare planned and actual memberships through an independent read-only query. Verify:

- exact album counts;
- no missing IDs;
- no unexpected IDs;
- no members outside the source;
- no HOLD overlap;
- source count unchanged.
