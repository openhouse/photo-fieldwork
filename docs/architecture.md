# Architecture

Photo Fieldwork keeps archive-specific access separate from archive-independent judgment.

```text
Catalog reader or filesystem scanner
              |
              v
       inventory.csv
              |
              v
 feasibility preflight
              |
              v
 capacity-flow selector ---> hold-sensitive.csv
              |
              v
   proposed-master.csv
        |            |
        v            v
 offline review    digest-bound catalog-plan.json
        |                    |
        v                    v
 feedback loop      decision ledger + final holdout
        |                    |
        +----------> release audit
                             |
                             v
                    editor-field release seal
                             |
                             v
                     catalog writer adapter
                             |
                             v
                      bound writer receipt
                             |
                             v
                    independent verifier
```

## Core

The standard-library Python core reads a normalized CSV, applies immutable safety and evaluation exclusions, reduces duplicate and burst clusters, assigns exact view quotas through deterministic capacity flow, creates selection reasons, samples evaluations, measures uncertainty, validates invariants, and emits an adapter-neutral digest-bound catalog plan. Its governance layer verifies run-bound append-only decision history, reconciles asset-specific human safety clearances to a frozen pre-clearance baseline, checks holdout separation, recomputes release gates, and seals the exact editor-field candidate.

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

A writer consumes a plan generated from `catalog-plan.json` and a matching editor-field release seal. It may create version folders, create albums, and add existing stable IDs. It must not invent selection logic. It must carry the candidate, release, catalog-plan, and assignment identities into its receipt, bind the receipt to the exact writer plan SHA-256, and be safe to rerun.

## Verifier adapters

A verifier independently compares plan and catalog. It should be read-only and should not share mutation code with the writer. It recomputes source and destination membership digests; equal-count membership substitution must fail. It also verifies that the plan, writer receipt, and supplied release seal identify the same candidate. Its structured receipt keeps `publication_clearance` false.

## Private profiles and run state

Machine paths and real catalog identifiers live in a gitignored local profile. A run stores the profile digest, not the profile. Fourteen ordered phases checkpoint artifact names, sizes, and SHA-256 values, including a required release audit before the write test. Identical retries are idempotent; changed evidence behind a completed phase is rejected.

## Trust artifacts

- `decision-events.jsonl` is a hash-chained history bound to the catalog plan run, not a mutable current-state file.
- The pre-clearance safety baseline freezes each asset's post-inspection safety state so later human transitions cannot erase their provenance.
- `holdout-audit.json` records only split counts, digests, and contamination counts.
- `release-seal.json` is a deterministic content binding for an editor-field candidate. It is not a signature and grants no publication authority.
- Apple Photos plans and receipts carry the same release identity into and out of the permissioned writer.
- `verification-report.json` is an independent, read-only observation of the written catalog and release identity.

## Review and projection

The static local review workspace records category fit, visible reason, safety, public suitability, provenance, and error category separately. A public-safe evidence handoff may summarize approved observations, but it contains no asset IDs or private archive metadata and grants no publication approval.

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
