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
3. Run the selection and create an evaluation sample.
4. Inspect sampled images locally and record `fit`, `reject`, or `uncertain`.
5. Evaluate, revise, and repeat until the agreed criteria pass.
6. Generate a digest-bound catalog write plan. Test ten items before any production write.
7. Verify the committed album membership independently and read-only.

```bash
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
  --source-members path/to/source-members.csv \
  --output runs/my-run/manifests/catalog-plan.json
```

The selector uses deterministic capacity flow so overlapping candidate views can satisfy exact quotas when the candidate graph is feasible. Infeasible configurations report deficient views and candidate reach instead of silently backfilling another category.

## Resume a private production run

Keep machine paths and real catalog identifiers in a gitignored local profile based on `config/local-profile.example.json`.

```bash
./bin/photo-fieldwork run \
  --workspace /private/path/to/runs/v05 \
  --brief brief.md \
  --profile /private/path/to/.photo-fieldwork.local.json \
  --version v05 \
  --target 4000

./bin/photo-fieldwork checkpoint \
  --workspace /private/path/to/runs/v05 \
  --phase doctor \
  --artifact /private/path/to/runs/v05/reports/doctor.json
```

Run state stores artifact digests, not the local profile. Repeating an identical checkpoint is safe; changing an artifact behind a completed checkpoint is rejected.

## Review locally

Build a static review instrument that opens with `file://` and starts no server:

```bash
./bin/photo-fieldwork review-pack \
  --sample runs/v05/manifests/eval-sample.csv \
  --previews runs/v05/previews/round-01 \
  --round-id round-01 \
  --reviewer-lens "delegated editorial review" \
  --output runs/v05/contact-sheets/review-round-01.html
```

The review separates visible category fit, safety, public suitability, and provenance. Its export feeds `photo-fieldwork evaluate` and `photo-fieldwork apply-feedback`.

## Hand off visual corroboration safely

`photo-fieldwork evidence-handoff` converts reviewed, operator-authored summaries into a public-safe Markdown note. It rejects asset IDs, filenames, local paths, People associations, coordinates, raw OCR, email addresses, and real catalog identifiers. The generated note says explicitly that photographs do not establish authorship, causation, outcomes, endorsement, consent, credit, or publication rights.

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic, configurable selection engine.
- Feasibility-aware exact-quota assignment with actionable diagnostics.
- Safety holds that cannot enter the master.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Stratified evaluation samples and precision thresholds.
- Wilson intervals, small-sample warnings, and separated review dimensions.
- Resumable phase checkpoints and version-comparison reports.
- Source, plan, album, and master membership digests.
- A static offline review workspace and public-safe evidence handoff.
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

The skill integrates with the permissioned app declared in the private local profile, preserving its stable Photos permission identity. Reviewed helper source is retained under `integrations/jamie-photo-archive/`; replacing or rebuilding the installed app is a separate, explicit operation because macOS may request Photos authorization again.
