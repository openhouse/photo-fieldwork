# Architecture

Photo Fieldwork keeps archive-specific access separate from archive-independent judgment.

```text
Catalog reader or filesystem scanner
              |
              v
 inventory.csv + source profile
              |
              v
 deterministic selector ---> hold-sensitive.csv
              |                       |
              +------> decision ledger <----- visual review rounds
              |
              v
   proposed-master.csv
        |            |
        v            v
 evaluation loop   catalog-plan.json
                         |
                         v
                 catalog writer adapter
                         |
                         v
             WAL-aware snapshot builder
                         |
                         v
                immutable verifier
```

## Core

The standard-library Python core reads a normalized CSV, applies immutable safety exclusions, reduces duplicate and burst clusters, assigns editor views, creates selection reasons, samples evaluations, measures results, validates invariants, and emits an adapter-neutral catalog plan.

The core does not read a Photos database, open images, call a model, or mutate a catalog.

## Decision ledger

The append-only SQLite ledger records retrieval, inspection, review, HOLD,
replacement, selection, commit, and verification events. Database triggers
reject updates and deletes. CSV manifests remain ordinary, inspectable editor
handoffs generated from the run, while the event history preserves how those
manifests changed.

## Run lifecycle

Run state is reconciled from receipts and content-addressed artifacts. A run can
be finalized only when all required phases are complete. This keeps operational
state from drifting behind the evidence on disk.

## Reader adapters

A reader converts a catalog or filesystem into `inventory.csv`. Reader development should preserve stable IDs and existing human metadata while minimizing sensitive exports.

Potential adapters include:

- `osxphotos` inventory export;
- Apple PhotoKit;
- a filesystem plus EXIF sidecars;
- Lightroom or Capture One catalog exports;
- a DAM API explicitly approved by its owner.

## Inspector adapters

An inspector may add local visible-context, technical-quality, and generalized safety fields. It must declare whether pixels leave the machine and whether raw OCR persists. The safe default for both is no.

## Writer adapters

A writer consumes `catalog-plan.json`. It may create version folders, create albums, and add existing stable IDs. It must not invent selection logic. It must emit a receipt and be safe to rerun.

## Verifier adapters

A verifier independently compares plan and catalog. It should be read-only and should not share mutation code with the writer.

For Apple Photos, a live `immutable=1` connection may ignore uncheckpointed WAL
state. The supported verifier first copies the minimum necessary rows through a
WAL-aware read-only connection, closes that compact snapshot, and then reopens
the snapshot immutably.

## Extension points

Contributors can improve one layer at a time:

- inventory mappings and provenance;
- local inspection;
- event and sequence clustering;
- safety detectors;
- balancing and evaluation metrics;
- contact-sheet interfaces;
- catalog writers and verifiers;
- editor handoff formats.

Every extension should include synthetic fixtures, a known failure case, and a statement of its privacy boundary.
