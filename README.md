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
3. Normalize retrieval hypotheses into image-view evidence and run exact constrained assignment.
4. Inspect sampled images locally and record `fit`, `reject`, or `uncertain`.
5. Evaluate, revise, and repeat until the agreed criteria pass.
6. Generate an evaluated catalog write plan, seal the release inputs, and test ten items before any production write.
7. Verify the committed album membership independently and read-only.

```bash
./bin/photo-fieldwork select \
  --inventory path/to/inventory.csv \
  --config path/to/config.json \
  --output runs/my-run

# Later rounds may provide an explicit edge manifest and cumulative feedback.
./bin/photo-fieldwork assign \
  --inventory path/to/inventory.csv \
  --edges runs/my-run/manifests/candidate-view-evidence.csv \
  --feedback runs/my-run/manifests/evaluation-ledger.csv \
  --config path/to/config.json \
  --output runs/my-run

./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --output runs/my-run/manifests/eval-sample.csv \
  --per-view 3

# Guarantee a fresh round instead of reusing previously reviewed IDs.
./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --exclude-feedback runs/my-run/manifests/evaluation-ledger.csv \
  --novel-only \
  --output runs/my-run/manifests/eval-round-02.csv \
  --per-view 3

./bin/photo-fieldwork evaluate \
  --feedback runs/my-run/manifests/eval-sample.csv \
  --config path/to/config.json \
  --output runs/my-run/reports

./bin/photo-fieldwork apply-feedback \
  --sample runs/my-run/manifests/eval-round-02.csv \
  --feedback runs/my-run/manifests/eval-round-02-decisions.csv \
  --output runs/my-run/manifests/eval-round-02-reviewed.csv \
  --ledger runs/my-run/manifests/evaluation-ledger.csv

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
  --evaluation-report runs/my-run/reports/evaluation-report.json \
  --output runs/my-run/manifests/catalog-plan.json
```

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic, overlap-aware constrained assignment engine with exact quotas.
- First-class image-view evidence and edge-specific feedback.
- Safety holds that cannot enter the master.
- A protected `needs-review` state and canonical ID comparisons.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Novel, stratified evaluation samples with overall and per-view release gates.
- Content-hashed plans, durable run state, and release seals.
- A generated local-only editor review surface with shortlist, caption, rights, consent, and public-safety fields.
- A fully synthetic practice run.
- Apple Photos integration guidance and adapter contracts.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), and [the Apple Photos guide](docs/apple-photos.md) before using a private archive.

For Apple Photos, copy `config/source-profile.example.json` to an untracked local location and pass it with `photo_archive_bridge.py --profile ...`. Machine paths, collection identifiers, and source counts belong in that local profile, not in shared workflow data.

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
