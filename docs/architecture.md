# Architecture

Photo Fieldwork keeps archive-specific access separate from archive-independent judgment.

```text
Catalog reader or filesystem scanner
              |
              v
       inventory.csv
              |
              v
 deterministic selector ---> hold-sensitive.csv
              |
              v
   proposed-master.csv
        |                    |
        v                    v
 working evaluation     effective-final-config.json
        |                    |
        v                    v
 untouched holdout       run-lock.json
        |                    |
        +---------> catalog-plan.json
                           |
                    writer adapter
                           |
                    independent verifier
                           |
                    public-safe handoff
```

## Core

The standard-library Python core reads a normalized CSV, applies immutable safety exclusions, reduces duplicate and burst clusters, assigns editor views, creates selection reasons, samples evaluations, measures results, validates invariants, and emits an adapter-neutral catalog plan.

The core does not read a Photos database, open images, call a model, or mutate a catalog.

## Run state and replay

Run workspaces use restrictive filesystem permissions and atomic JSON state
transitions. Each recorded input and output carries a SHA-256 digest. Freezing a
master creates an effective final config whose quotas match the surviving field,
preserves the original intent quotas, and records unsupported or deliberately
empty views without forcing substitutes.

`run-lock.json` detects post-freeze mutation. Validation reports should be
recreated from locked artifacts before a writer plan is approved.

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

The bundled Apple Photos integration has two implementations of this contract:
the preferred PhotoKit helper and an explicit AppleScript membership adapter.
Backend changes are recorded and never remove the independent verification gate.

## Verifier adapters

A verifier independently compares plan and catalog. It should be read-only and should not share mutation code with the writer.

## Public handoff

The publication projection is an allowlist, not a redacted private manifest. It
contains opaque public IDs and approved page, caption, credit, crop, consent,
rights, and claim states. It excludes stable archive IDs, People associations,
albums, local paths, locations, OCR, safety reasons, and HOLD membership.

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
