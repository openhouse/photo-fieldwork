# Photo Fieldwork

Photo Fieldwork is a local-first practice and production workflow for reducing a large personal photo archive into a smaller, editor-ready field of possibilities.

It does not automate taste. It helps people automate retrieval, deduplication, balancing, safety review, provenance, evaluation, and reversible handoff while keeping final editorial judgment human.

The production protocol treats a run as a chain of typed, auditable artifacts: active source profile, balanced retrieval allocation, local inspection ledger, relational safety decisions, recursive evaluation rounds, feedback and replacement review, sealed catalog plans, writer receipts, independent verification, and an artifact-derived completion report.

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
6. Generate a catalog write plan. Test ten items before any production write.
7. Verify the committed album membership independently and read-only.

Validate and fingerprint the exact source before retrieval:

```bash
./bin/photo-fieldwork source-check \
  --source-profile config/source-profile.example.json
```

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

Production runs can also use:

```bash
./bin/photo-fieldwork safety --inventory INPUT.csv --policy POLICY.json \
  --output SAFE.csv --decisions decisions.jsonl

./bin/photo-fieldwork inspection-ledger --batch-manifest BATCHES.json \
  --output inspections.jsonl --report inspection-report.json

./bin/photo-fieldwork apply-feedback --master MASTER.csv --candidates CANDIDATES.csv \
  --feedback ROUND.csv --config CONFIG.json --output RUN

./bin/photo-fieldwork duplicate-audit --inventory MASTER.csv \
  --output duplicate-review.csv --report duplicate-report.json

./bin/photo-fieldwork lint-plan --plan PLAN.json --master MASTER.csv \
  --holds HOLDS.csv --config CONFIG.json --source-profile SOURCE.json \
  --inspection-ledger inspections.jsonl --output plan-lint.json

./bin/photo-fieldwork report --run RUN --output RUN/reports/completion-report.md
```

All CLI commands accept `--format json` before the subcommand for automation. Quality gates return a nonzero status while still writing diagnostic artifacts.

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic, configurable selection engine.
- Source profiles that bind a run to one immutable source identity and count.
- View-order-independent candidate reservation before global truncation.
- Typed retrieval, visible-evidence, provenance, and editor-hypothesis fields.
- Relational safety rules and append-only decisions.
- Content-addressed inspection and preview ledgers.
- Safety holds that cannot enter the master.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Stratified evaluation samples and precision thresholds.
- Overall and per-view evaluation gates.
- Explicit feedback application and cascading replacement review.
- Cross-UUID duplicate audits.
- Sealed plans, resumable run state, idempotence receipts, and derived reports.
- A fully synthetic practice run.
- Apple Photos integration guidance and adapter contracts.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.
- Publication clearance inferred from private album membership.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), and [the Apple Photos guide](docs/apple-photos.md) before using a private archive.
The [production protocol](docs/production-protocol.md) gives the end-to-end artifact and release contract.
[Revision H](docs/revision-H.md) maps the whole-library findings to implemented guarantees and deliberate boundaries.

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
