# Photo Fieldwork

Photo Fieldwork is a local-first practice and production workflow for reducing a large personal photo archive into a smaller, editor-ready field of possibilities.

It does not automate taste. It helps people automate retrieval, deduplication, balancing, safety review, provenance, evaluation, and reversible handoff while keeping final editorial judgment human.

## Try it in two minutes

Requirements: Python 3.11 or newer. The practice workflow has no third-party dependencies and does not access Apple Photos.

The Apple Photos preview and contact-sheet tools use the optional `apple-photos` extra:

```bash
python3 -m pip install -e '.[apple-photos]'
```

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
make evals
```

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

# Later rounds must use newly inspected UUIDs.
./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --exclude-feedback runs/my-run/manifests/eval-sample.csv \
  --novel-only \
  --output runs/my-run/manifests/eval-round-02.csv \
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
  --evaluation-report runs/my-run/reports/evaluation-report.json \
  --plan-id my-run-v01 \
  --source-title "Wide retrieval - do not edit" \
  --source-identifier SOURCE-ID \
  --output runs/my-run/manifests/catalog-plan.json

./bin/photo-fieldwork ledger \
  --master runs/my-run/manifests/proposed-master.csv \
  --holds runs/my-run/manifests/hold-sensitive.csv \
  --feedback runs/my-run/manifests/eval-sample.csv \
  --output runs/my-run/manifests/decision-ledger.jsonl

./bin/photo-fieldwork audit-holdout \
  --tuning runs/my-run/manifests/all-tuning-feedback.csv \
  --holdout runs/my-run/manifests/final-holdout.csv \
  --output runs/my-run/reports/final-holdout-audit.json

./bin/photo-fieldwork public-handoff \
  --input runs/my-run/manifests/public-derivative-review.csv \
  --output runs/my-run/public/public-handoff.json \
  --report runs/my-run/reports/public-handoff-report.json
```

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic capacity network that jointly meets exact view quotas and people-diversity floors or reports deficits.
- Fail-closed safety states with transitive duplicate, perceptual-cluster, and burst HOLD propagation.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Hash-bound fresh samples, separately scored regression canaries, novel-only recursive rounds, and per-view precision thresholds.
- Relationship-aware final-holdout audits that reject tuning leakage and internal duplicate evidence.
- Explicit decisive-precision, fit-rate, uncertainty, and population-weighted evaluation measures.
- Exact master and evaluation-sample hashes that bind editor-field evaluation to catalog plans.
- A public-safe adversarial skill eval bank and recursive hill-climb record.
- A fully synthetic practice run.
- Apple Photos integration guidance and adapter contracts.
- Whole-visible-library inventory, preview-integrity, and WAL-safe verification tools.
- Append-only, artifact-hashed run state with revision conflicts, legal phase order, and deterministic recovery.
- Nonce-bound Python/Swift helper receipts that identify the exact plan bytes, helper revision, and source membership executed.
- An allowlisted public-derivative handoff with independent rights, consent, claim, safety, and publication gates.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), [the Apple Photos guide](docs/apple-photos.md), and [the editor handoff](docs/editor-handoff.md) before using a private archive. The [v04-N case study](docs/case-study-v04-n.md) records the failures that shaped the current gates, the [Revision N composite](docs/revision-composite-N.md) identifies the contracts adopted from A-N, and the [recursive eval hill climb](docs/eval-hill-climb.md) records how those gates were challenged.

Before publishing changes to this public repository, run:

```bash
./bin/photo-fieldwork audit-public --root .
```

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
