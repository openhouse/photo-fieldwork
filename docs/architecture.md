# Architecture

Photo Fieldwork keeps archive-specific access separate from archive-independent judgment.

```text
Versioned source adapter + source manifest
              |
              v
       inventory.csv
              |
              v
retrieval hypotheses + local inspection
              |
              v
 explicit editorial assignments
              |
              v
 deterministic selector ---> hold-sensitive.csv
              |
              v
   proposed-master.csv + master_sha256 + hold_sha256
        |            |
        v            v
 scoped evaluation   hash-bound catalog-plan.json
                         |
                         v
                 catalog writer adapter
                         |
                         v
              hash-bound app receipt
                         |
                         v
                  independent verifier
```

## Core

The standard-library Python core reads a normalized CSV, applies typed safety exclusions, reduces exact, burst, and perceptual clusters, consumes explicit editor assignments, creates selection reasons, freezes proposal and sample hashes, distinguishes evaluation scopes and release classes, validates invariants, and emits an adapter-neutral catalog plan only when the exact master and source match a passing final evaluation.

The core does not read a Photos database, open images, call a model, or mutate a catalog.

## Reader adapters

A reader converts a versioned source snapshot into `inventory.csv`. Reader development should preserve stable IDs and existing human metadata while minimizing sensitive exports. Source manifests record the adapter identifier, observed count, predicate version, and fingerprint; an unacknowledged source change blocks later phases.

Potential adapters include:

- `osxphotos` inventory export;
- Apple PhotoKit;
- a filesystem plus EXIF sidecars;
- Lightroom or Capture One catalog exports;
- a DAM API explicitly approved by its owner.

## Inspector adapters

An inspector may add local visible-context, technical-quality, and generalized safety fields. It must declare whether pixels leave the machine and whether raw OCR persists. The safe default for both is no.

## Writer adapters

A writer consumes schema-version-2 `catalog-plan.json`. It may create version folders, create albums, and add existing stable IDs. It must not invent selection logic. It must decode and preserve source, proposal, master, hold, plan, release, and helper-revision fields; emit a matching receipt; update durable run state; and be safe to rerun.

## Verifier adapters

A verifier independently compares plan, receipt, source membership, and catalog. It should be read-only and should not share mutation code with the writer. Count equality alone is insufficient: the source membership digest must match.

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
