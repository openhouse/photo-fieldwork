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

1. Copy `config/starter.json` and edit the views, quotas, and thresholds.
2. Prepare a CSV using `schemas/inventory-fields.md`.
3. Freeze exact source membership, then run selection and create an evaluation sample.
4. Build the offline review surface, inspect sampled images locally, and record `fit`, `reject`, or `uncertain`.
5. Append feedback to the decision ledger, apply it to candidates, and repeat until every view passes.
6. Audit tuning/final/canary separation and run a candidate-bound final evaluation.
7. Generate a sealed catalog plan from the unchanged source, candidate, evaluation, and validation artifacts. Test ten items before production.
8. Verify helper receipts, idempotence, and committed membership against a private WAL-visible read-only snapshot.

```bash
./bin/photo-fieldwork select \
  --inventory path/to/inventory.csv \
  --config path/to/config.json \
  --output runs/my-run

./bin/photo-fieldwork source-freeze \
  --inventory path/to/inventory.csv \
  --source-adapter apple-photos \
  --source-identifier SOURCE-ID \
  --predicate-version visible-stills-v1 \
  --output runs/my-run/manifests/source-manifest.json

./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --output runs/my-run/manifests/eval-sample.csv \
  --per-view 3

./bin/photo-fieldwork review \
  --sample runs/my-run/manifests/eval-sample.csv \
  --previews runs/my-run/previews \
  --output runs/my-run/review

./bin/photo-fieldwork audit-evaluation-splits \
  --tuning runs/my-run/manifests/tuning-feedback.csv \
  --final-holdout runs/my-run/manifests/eval-sample.csv \
  --canaries runs/my-run/manifests/regression-canaries.csv \
  --output runs/my-run/reports/evaluation-split-audit.json

./bin/photo-fieldwork evaluate \
  --feedback runs/my-run/manifests/eval-sample.csv \
  --master runs/my-run/manifests/proposed-master.csv \
  --source-manifest runs/my-run/manifests/source-manifest.json \
  --scope final-holdout \
  --config path/to/config.json \
  --output runs/my-run/reports

./bin/photo-fieldwork decisions-append \
  --feedback runs/my-run/manifests/eval-sample.csv \
  --ledger runs/my-run/manifests/editorial-decisions.csv \
  --round-id round-01

./bin/photo-fieldwork validate \
  --master runs/my-run/manifests/proposed-master.csv \
  --holds runs/my-run/manifests/hold-sensitive.csv \
  --config path/to/config.json \
  --output runs/my-run/reports

./bin/photo-fieldwork plan \
  --master runs/my-run/manifests/proposed-master.csv \
  --holds runs/my-run/manifests/hold-sensitive.csv \
  --config path/to/config.json \
  --plan-id my-run-v01 \
  --source-inventory path/to/inventory.csv \
  --source-manifest runs/my-run/manifests/source-manifest.json \
  --evaluation-sample runs/my-run/manifests/eval-sample.csv \
  --tuning-sample runs/my-run/manifests/tuning-feedback.csv \
  --evaluation-report runs/my-run/reports/evaluation-report.json \
  --validation-report runs/my-run/reports/validation-report.json \
  --split-audit-report runs/my-run/reports/evaluation-split-audit.json \
  --output runs/my-run/manifests/catalog-plan.json
```

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic, configurable selection engine.
- Exact multi-view quota assignment with named-people and person-free floors solved together.
- Safety holds that cannot enter the master.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Stratified evaluation samples with enforced overall and per-view evidence gates.
- An append-only editorial decision ledger and replacement-entry audit.
- A hash-chained append-only run ledger, atomic recovery, revision checks, and unique write attempts.
- Frozen source manifests and content-addressed release candidates that bind every write authorization input.
- Relationship-level final-holdout audits and canaries that cannot inflate final quality metrics.
- Capability-negotiated helper receipts and WAL-visible frozen independent verification snapshots.
- Conflict-safe candidate and inspection batch utilities.
- An offline local review surface that downloads compact feedback CSV.
- Prior-version integrity registration and publication-clearance manifests.
- A whole-visible-library Apple Photos inventory adapter.
- A fully synthetic practice run.
- Fourteen adversarial skill-behavior evals with a deterministic evidence-closure grader and repeatable agent runner.
- Apple Photos integration guidance and adapter contracts.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the composite design](docs/composite-revision-e.md), [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), and [the Apple Photos guide](docs/apple-photos.md) before using a private archive.

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
