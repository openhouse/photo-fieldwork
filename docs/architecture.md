# Architecture

Photo Fieldwork keeps archive-specific access separate from archive-independent judgment.

```text
Catalog reader or filesystem scanner
              |
              v
 frozen source inventory + source manifest
        |          |
        |          +------> hold-sensitive.csv
        v
 decision-aware selector <------ editorial-decisions.csv
        |
        v
 proposed-master.csv + HOLD
    |                 |                 |
    v                 v                 v
 final holdout   release candidate   publication-clearance.csv
    |                 |
    +------> sealed catalog plan ----> catalog writer adapter
                       |
                       v
                independent verifier

 hash-chained events.jsonl + recoverable run-state.json wrap every phase
```

## Core

The standard-library Python core reads a normalized CSV, applies immutable safety exclusions, reduces duplicate and burst clusters, solves exact view and diversity assignment, preserves editorial decisions, samples evaluations, enforces per-view gates, validates invariants, records version integrity, and emits adapter-neutral plans.

The core does not read a Photos database, open images, call a model, or mutate a catalog.

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

A writer consumes a schema-2 `catalog-plan.json` bound to one release candidate. It may create version folders, create albums, and add existing stable IDs. It must not invent selection logic. It emits a helper-, plan-, candidate-, source-, and execution-bound receipt and must be safe to rerun under a distinct nonce.

## Verifier adapters

A verifier independently compares plan and catalog. It is read-only and does not share mutation code with the writer. The Apple Photos adapter freezes a WAL-visible SQLite backup, then verifies that private snapshot through an immutable query-only connection.

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

## Profiles

Machine paths, source identifiers, protected album identifiers, and permissioned helper details belong in adapter profiles and `machine-profile.md`, not in selection logic. The public core remains usable without Apple Photos. The Jamie profile is intentionally explicit because it is operational documentation for one local system; other users should provide their own adapter values.
