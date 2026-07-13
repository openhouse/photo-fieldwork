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

The standard-library Python core reads a normalized CSV, applies immutable safety exclusions, reduces duplicate and burst clusters, assigns editor views, creates selection reasons, samples evaluations, measures results, validates invariants, and emits an adapter-neutral catalog plan.

The core does not read a Photos database, open images, call a model, or mutate a catalog.

## Decision lineage

`photo-fieldwork ledger` emits stable JSONL events for selection, HOLD, and evaluation. Each event keeps retrieval hypotheses, visible descriptions, and verified contexts separate and carries the proposal and exact-master hash when available. Generated reports and editor packets should treat this ledger as their index rather than silently overwriting prior decisions.

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
