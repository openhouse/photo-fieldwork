# Photo Fieldwork

Photo Fieldwork is a local-first practice and production workflow for reducing a large personal photo archive into a smaller, editor-ready field of possibilities.

It does not automate taste. It helps people automate retrieval, deduplication, balancing, safety review, provenance, evaluation, and reversible handoff while keeping final editorial judgment human.

## Try it in two minutes

Requirements: Python 3.11 or newer. The practice workflow has no third-party dependencies and does not access Apple Photos.

```bash
make demo
```

This creates a synthetic inventory, runs a deterministic selection, quarantines unsafe records, produces a stratified evaluation sample, applies practice feedback, and validates the result under `runs/practice/`.

Inspect the outputs:

```bash
open runs/practice/reports/selection-summary.md
open runs/practice/reports/evaluation-report.md
open runs/practice/manifests/eval-sample.csv
```

Run the tests:

```bash
make check
```

## Use it with your own inventory

1. Initialize a private, permission-restricted run workspace.
2. Copy `config/starter.json` and edit the views, quotas, and thresholds.
3. Prepare a CSV using `schemas/inventory-fields.md`.
4. Run selection and use working-round samples to find systematic errors.
5. Freeze the surviving master and its effective final configuration.
6. Draw a fresh final holdout that excludes all tuning examples.
7. Generate a catalog write plan. Test ten items before any production write.
8. Verify committed membership independently and read-only.
9. Produce a separate, allowlisted public handoff only for cleared images.

```bash
./bin/photo-fieldwork run init \
  --workspace runs/my-run \
  --version v01 \
  --target 4000 \
  --source-identifier SOURCE-ID \
  --expected-source-count SOURCE-COUNT

./bin/photo-fieldwork select \
  --inventory path/to/inventory.csv \
  --config path/to/config.json \
  --output runs/my-run

./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --output runs/my-run/manifests/eval-sample.csv \
  --per-view 3

./bin/photo-fieldwork evaluate \
  --feedback runs/my-run/manifests/eval-sample.csv \
  --config path/to/config.json \
  --output runs/my-run/reports

./bin/photo-fieldwork freeze-final \
  --workspace runs/my-run \
  --intent-config path/to/config.json \
  --master runs/my-run/manifests/proposed-master.csv \
  --holds runs/my-run/manifests/hold-sensitive.csv

./bin/photo-fieldwork sample \
  --mode final-holdout \
  --sample-size 220 \
  --minimum-per-view 15 \
  --exclude-feedback runs/my-run/manifests/eval-round-01-reviewed.csv \
  --master runs/my-run/manifests/proposed-master.csv \
  --output runs/my-run/manifests/final-holdout.csv

./bin/photo-fieldwork validate \
  --master runs/my-run/manifests/proposed-master.csv \
  --holds runs/my-run/manifests/hold-sensitive.csv \
  --config path/to/config.json \
  --output runs/my-run/reports

./bin/photo-fieldwork plan \
  --master runs/my-run/manifests/proposed-master.csv \
  --config path/to/config.json \
  --plan-id my-run-v01 \
  --source-title "Wide retrieval - do not edit" \
  --source-identifier SOURCE-ID \
  --output runs/my-run/manifests/catalog-plan.json

./bin/photo-fieldwork handoff \
  --master runs/my-run/manifests/publication-reviewed.csv \
  --salt PRIVATE-RUN-SALT \
  --output runs/my-run/final/public-site-projection.csv
```

The working evaluation report distinguishes review completion, view sampling
coverage, decisive fit rate, and field audit rate. Final holdouts also report a
95% Wilson interval. A 100% observed fit rate is not represented as certainty.

Record quota, label, status, and rule changes as hash-linked decisions rather
than silently editing history:

```bash
./bin/photo-fieldwork run decision \
  --workspace runs/my-run \
  --round-id round-02 \
  --field views.07.status \
  --before active \
  --after unsupported \
  --reason "No inspected image supported the project-specific claim." \
  --reviewer editor
```

Build a dependency-free offline review workbench from a sample:

```bash
./bin/photo-fieldwork review-build \
  --sample runs/my-run/manifests/final-holdout.csv \
  --previews runs/my-run/previews \
  --output runs/my-run/review/index.html

./bin/photo-fieldwork review-serve \
  --directory runs/my-run/review
```

The server refuses non-loopback bindings, and the generated page blocks network
connections. Review exports still belong to the private run workspace.

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Consent and rights answer: "May this image be used here, for this audience, now?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic, configurable selection engine.
- Safety holds that cannot enter the master.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Working-round samples plus untouched final holdouts and confidence intervals.
- Hash-linked, atomic run state and replayable effective final configs.
- Event-cluster caps, prior-corpus novelty floors, and explicit album lineage.
- A private offline review workbench with no external requests.
- A public-safe handoff that excludes private fields by construction.
- A fully synthetic practice run.
- Whole-library Apple Photos inventory and preview-integrity tools.
- Live read-only PhotoKit preflight and PhotoKit/AppleScript writer contracts.
- Two case studies of how visual inspection changed real workflows.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), [the threat model](docs/threat-model.md), and [the Apple Photos guide](docs/apple-photos.md) before using a private archive.

## Use it as a Codex skill

Install the bundled `curate-apple-photos` skill:

```bash
make install-skill
```

Restart Codex, open a new local chat, and invoke it with a brief such as:

```text
Use $curate-apple-photos.

Role-play as Jamie Burkart, Cyd Harrell, Sara Hendren, Abby Covert,
Hamel Husain, Vivian Gornick, and Deborah Treisman. Indicate who is
speaking and say what you think.

Using the curatorial brief below, create a new, versioned 6,000-photo
editor field from my Apple Photos library. Carry the work through local
inspection, recursive visual evaluation, safety review, a test write,
production album creation, and independent verification.

[PASTE TODAY'S BRIEF]
```

The skill integrates with a stable, permissioned local helper. Machine-specific
paths and identifiers belong in a private profile conforming to
`schemas/profile.schema.json`; `profiles/profile.example.json` contains only
synthetic values. Create one with `photo_archive_bridge.py init-profile --help`,
store it outside the repository, and run `doctor --live` before expensive work.

The reviewed helper source is retained under `integrations/jamie-photo-archive/`.
Replacing, rebuilding, or re-signing the installed app is a separate explicit
operation because macOS may treat it as a new Photos permission identity.
