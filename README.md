# Photo Fieldwork

Photo Fieldwork is a local-first practice and production workflow for reducing a large personal photo archive into a smaller, editor-ready field of possibilities.

It does not automate taste. It helps people automate retrieval, deduplication, balancing, safety review, provenance, evaluation, and reversible handoff while keeping final editorial judgment human.

## Try it in two minutes

Requirements: Python 3.11 or newer. The practice workflow has no third-party dependencies and does not access Apple Photos.

The local contact-sheet and preview-verification tools require the optional
review dependency: `pip install 'photo-fieldwork[review]'`.

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

The synthetic [skill evaluation bank](evals/README.md) covers recovery,
fresh-evidence discipline, source and artifact identity, stratified quality,
safety and consent, catalog verification, privacy-safe handoff, and epistemic
provenance. It includes adversarial shortcuts so an agreeable but unsafe answer
does not count as a pass.

The latest [evaluation hill climb](docs/eval-hillclimb.md) records how weak
assertions were challenged and promoted into executable regressions.

## Use it with your own inventory

1. Copy `config/starter.json` and edit the views, quotas, and thresholds.
2. Prepare a CSV using `schemas/inventory-fields.md`.
3. Run the selection and create an evaluation sample.
4. Inspect sampled images locally and record `fit`, `reject`, or `uncertain`.
5. Evaluate, revise, and repeat until the agreed criteria pass.
6. Generate a catalog write plan. Test ten items before any production write.
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
  --output runs/my-run/manifests/catalog-plan.json
```

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## Freeze the source and preserve run state

Version `0.2.0` distinguishes a dynamic source query from the immutable snapshot
used by one run. Freeze source membership before selection:

```bash
./bin/photo-fieldwork source-snapshot \
  --inventory path/to/inventory.csv \
  --query-id "filesystem-stills://v1" \
  --output runs/my-run/source-snapshot.json

./bin/photo-fieldwork run-init \
  --workspace runs/my-run \
  --run-id my-run \
  --target-count 4000 \
  --source-snapshot runs/my-run/source-snapshot.json

./bin/photo-fieldwork run-record \
  --workspace runs/my-run \
  --phase brief \
  --status completed

./bin/photo-fieldwork run-status --workspace runs/my-run
```

`events.jsonl` is append-only. `run-state.json` is derived from it and should
not be edited by hand.

## What is included

- A deterministic, configurable selection engine.
- Safety holds that cannot enter the master.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Stratified evaluation samples and precision thresholds.
- Enforced overall, per-view, coverage, decisive-sample, and uncertainty gates.
- Frozen source membership digests and append-only run events.
- Provenance-aware safety states and explicit human review.
- A fully synthetic practice run.
- Apple Photos integration guidance and adapter contracts.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), [the Apple Photos guide](docs/apple-photos.md), and [the roadmap](docs/roadmap.md) before using a private archive.

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

Production plans are content-addressed. The helper archives every execution as a
separate attempt receipt, and the independent verifier checks exact membership,
source digest, folder topology, plan integrity, and master/HOLD disjointness.
