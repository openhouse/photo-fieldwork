# Architecture

Photo Fieldwork keeps archive-specific access separate from archive-independent judgment.

```text
Versioned source profile
              |
              v
Catalog reader or filesystem scanner
              |
              v
       inventory.csv
              |
              v
retrieval hypotheses + local inspection
              |
              v
append-only human decision ledger
              |
              v
 reviewed assignments + related-frame holds
              |
              v
 deterministic selector ---> hold-sensitive.csv
              |
              v
 proposed-master.csv + master_sha256
        |            |
        v            v
per-view evaluation   validation + catalog-plan.json
        |                         |
        +------------+------------+
                     v
          candidate-bound release seal
                     |
                     v
             catalog writer adapter
                     |
                     v
              independent verifier
                     |
                     v
          separate publication review
```

## Core

The standard-library Python core reads a normalized CSV, applies safety exclusions, reduces
exact, burst, and perceptual clusters, consumes explicit reviewed assignments, freezes
proposal hashes, validates structured feedback, enforces global and per-view evaluation
gates, and emits a catalog plan only for a passing full audit of the same master hash.

The core does not read a Photos database, open images, call a model, or mutate a catalog.

`decisions.jsonl` preserves human assignment, evaluation, and safety decisions as a hash-chained,
append-only history. Superseding events do not erase their predecessors. Materialization applies
the latest decision and propagates unresolved holds through perceptual, duplicate, and burst
relationships.

`run-state.json` records phase status and hashes of completed artifacts. The run-state
layer does not rerun commands automatically; `status`, `resume`, and `audit` identify the
next phase and detect changed or missing evidence before an operator proceeds.

`release-seal.json` binds the frozen source, configuration, exact master assignments, full
evaluation, validation, and catalog plan. It grants authority for a bounded write test only.
Any sealed artifact drift invalidates the seal.

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

A writer consumes `catalog-plan.json`. It may create version folders, create albums, and add
existing stable IDs. It preserves proposal and master hashes in the receipt, must not invent
selection logic, and must be safe to rerun.

## Verifier adapters

A verifier independently compares plan and catalog. The Apple Photos verifier opens the
live database read-only so committed WAL state remains visible, copies only the source IDs
and receipt albums into a bounded compact database, then verifies that snapshot in
immutable mode. It does not share mutation code with the writer.

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
