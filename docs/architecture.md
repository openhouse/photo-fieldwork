# Architecture

Photo Fieldwork keeps archive-specific access separate from archive-independent judgment.

```text
Catalog reader or filesystem scanner
              |
              v
       inventory.csv
         + source-profile.json
              |
              v
 deterministic selector ---> hold-sensitive.csv
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
                  independent verifier
```

## Core

The standard-library Python core reads a normalized CSV, fingerprints its frozen source, applies immutable safety exclusions, reduces duplicate and burst clusters, solves exact view capacities, creates selection reasons, samples evaluations, measures distinct evaluation denominators, validates invariants, and emits an adapter-neutral semantic catalog plan.

Every production run also has an append-only `events.jsonl`. `run-state.json` is an atomic materialized view of that ledger, not the sole record of progress. Completed transitions require an artifact checksum. `photo-fieldwork status RUN` reconstructs current state from history.

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

A writer consumes `catalog-plan.json`. Albums carry stable keys, semantic roles, visibility, parent folders, and exact membership. A writer may create version folders, create albums, and add existing stable IDs. It must not invent selection logic. It must emit a receipt and be safe to rerun.

## Verifier adapters

A verifier independently compares plan and catalog. It should be read-only and should not share mutation code with the writer. It verifies exact source fingerprints, master/HOLD separation, view subsets, and missing, unexpected, or outside-source memberships. It emits real JSON for machines and Markdown for people.

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
