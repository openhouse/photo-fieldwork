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

Every production phase also emits an append-only receipt. `run-state.json` and the completion report are derived views of those receipts.

## Core

The standard-library Python core reads a normalized CSV, applies immutable safety exclusions, reduces duplicate and burst clusters, jointly assigns multi-view candidates through deterministic capacity max-flow, creates selection reasons, samples evaluations, measures results, validates invariants, and emits an adapter-neutral catalog plan.

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

A writer consumes `catalog-plan.json`. It may create version folders, create albums, and add existing stable IDs. It must not invent selection logic. It must emit a receipt and be safe to rerun.

Plan schema 2 binds the exact source membership, proposed-master membership and assignments, exact passing final-evaluation and validation reports, and plan content. A writer must reject a missing or mismatched identity rather than reconstructing authorization from filenames.

## Verifier adapters

A verifier independently compares plan and catalog. It should be read-only and should not share mutation code with the writer.

For Apple Photos, the verifier first opens the live catalog in one WAL-aware, read-only transaction and extracts only relevant source checks and target memberships into compact evidence. Verification then reopens that evidence with immutable and query-only flags.

## Machine profiles

User-specific paths, source counts, stable app identities, and protected Photos identifiers live in a validated local profile outside Git. Public code consumes the profile but does not carry live machine topology.

## Run state

Semantic versions are reserved before work. Phase receipts contain checksums for declared input and output files. State derivation rechecks those artifacts; missing or changed evidence blocks the workspace. Later phases cannot pass while prerequisites are incomplete. Repeated evaluation receipts are allowed; the latest passing receipt determines phase state only while receipt integrity holds.

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
