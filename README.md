# Photo Fieldwork

Photo Fieldwork is a local-first practice and production workflow for reducing a large personal photo archive into a smaller, editor-ready field of possibilities.

It does not automate taste. It helps people automate retrieval, deduplication, balancing, safety review, provenance, evaluation, and reversible handoff while keeping final editorial judgment human.

## Try it in two minutes

Requirements: Python 3.11 or newer. The practice workflow has no third-party dependencies and does not access Apple Photos.

```bash
make demo
```

This creates a synthetic inventory and source fingerprint, runs exact quota assignment, quarantines unsafe records, produces a UUID-addressed evaluation sample, applies practice feedback, and validates the result under `runs/practice/`.

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

1. Copy `config/starter.json` and edit the views, exact quotas, and evaluation gates.
2. Prepare a CSV using `schemas/inventory-fields.md`, then freeze its UUID membership in a source profile.
3. Initialize a run ledger and record phase artifacts as work completes.
4. Run the selection and create an evaluation sample.
5. Inspect sampled images locally and record UUID-keyed `fit`, `reject`, or `uncertain` decisions with visible reasons.
6. Evaluate, apply feedback, revise, and repeat until the agreed overall and per-view gates pass.
7. Generate a semantic catalog plan. Test ten items before any production write.
8. Verify exact membership, safety separation, and the source fingerprint independently and read-only.

```bash
./bin/photo-fieldwork source-profile \
  --inventory path/to/inventory.csv \
  --id visible-library-stills://v1 \
  --kind photos-query \
  --scope "visible, non-hidden, non-trashed stills" \
  --output runs/my-run/inventory/source-profile.json

./bin/photo-fieldwork init-run \
  --run runs/my-run \
  --version v01 \
  --target 4000

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

./bin/photo-fieldwork apply-feedback \
  --master runs/my-run/manifests/proposed-master.csv \
  --sample runs/my-run/manifests/eval-sample.csv \
  --feedback runs/my-run/manifests/eval-feedback.csv \
  --output runs/my-run

./bin/photo-fieldwork validate \
  --master runs/my-run/manifests/proposed-master.csv \
  --holds runs/my-run/manifests/hold-sensitive.csv \
  --config path/to/config.json \
  --output runs/my-run/reports

./bin/photo-fieldwork plan \
  --master runs/my-run/manifests/proposed-master.csv \
  --config path/to/config.json \
  --plan-id my-run-v01 \
  --source-profile runs/my-run/inventory/source-profile.json \
  --holds runs/my-run/manifests/hold-sensitive.csv \
  --output runs/my-run/manifests/catalog-plan.json

./bin/photo-fieldwork transition \
  --run runs/my-run \
  --phase validation \
  --status completed \
  --expected-revision 1 \
  --artifact runs/my-run/reports/validation-report.json

./bin/photo-fieldwork status runs/my-run
```

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic, capacity-aware selection engine that meets exact view quotas or reports why it cannot.
- Explicit safety states whose restricted lanes cannot enter the general master.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- UUID-hashed evaluation samples with separate coverage, decisive precision, fit, rejection, and uncertainty rates.
- Atomic run state, an append-only event ledger, artifact checksums, and state recovery.
- Frozen source profiles with SHA-256 membership fingerprints.
- Semantic album plans and machine-readable plus human-readable verification reports.
- A fully synthetic practice run.
- Apple Photos integration guidance and adapter contracts.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [run integrity](docs/run-integrity.md), [the safety model](docs/safety.md), and [the Apple Photos guide](docs/apple-photos.md) before using a private archive.

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

The skill integrates with the installed `/Applications/Jamie Photo Archive.app`, preserving its stable Photos permission identity. Its reviewed source is retained under `integrations/jamie-photo-archive/`; replacing or rebuilding the installed app is a separate, explicit operation because macOS may request Photos authorization again.
