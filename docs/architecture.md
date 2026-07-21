# Architecture

Photo Fieldwork keeps archive-specific access separate from archive-independent judgment.

```text
Frozen source profile + catalog reader
              |
              v
       inventory.csv
              |
              v
 retrieval hypotheses ---> deterministic constrained assignment
                                   |
                                   v
                         selector ---> hold-sensitive.csv
              |
              v
 proposed-master.csv + proposal hash
        |            |                 |
        v            v                 v
 verified offline   bound catalog-    default-closed
 review + evaluation plan.json        clearance ledger
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

The core keeps retrieval hypotheses separate from explicit assignment. Exact
membership plus assignments produce a stable proposal hash. Evaluation and
catalog plans must reference the same hash.

The private review layer accepts only digest-verified previews inside an
explicit root. It copies them under content-derived names into an offline field,
requires complete visible judgments, and keeps delegated inference distinct
from named human review.

The publication layer is a separate projection. It starts closed, binds each
decision to the exact proposal and destination, and emits only an allowlisted
public-safe row with a destination-specific opaque identifier. Editor-field
membership never implies rights, consent, safety, or publication approval.

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

The Apple Photos verifier creates a consistent backup from a live read-only,
query-only connection so committed WAL content is included. It then verifies
only against the frozen immutable snapshot.

## Run state

The skill bridge records ordered phases and a SHA-256 ledger of the artifacts
that complete each phase. Run directories and sensitive artifacts are private
by default. The ledger supports interruption and review without making the
mutable Photos catalog itself the only record of what happened.

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
