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

The bundled skill also has a compact adversarial eval bank covering source
identity, safety, resumability, per-view quality, mutation verification, privacy,
and publication boundaries. See
[skill evals](skills/curate-apple-photos/evals/README.md).
The mutations and convergence rule are recorded in the
[eval hill climb](docs/eval-hill-climb.md).

The production workflow now also includes a resumable run state, append-only
decision ledger, inspected replacement rounds, named validation gates, source
profiles, preview decoding QA, and WAL-aware frozen Apple Photos verification.

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
  --manifest runs/my-run/manifests/eval-sample-manifest.json \
  --per-view 3

./bin/photo-fieldwork evaluate \
  --master runs/my-run/manifests/proposed-master.csv \
  --feedback runs/my-run/manifests/eval-sample.csv \
  --sample-manifest runs/my-run/manifests/eval-sample-manifest.json \
  --config path/to/config.json \
  --output runs/my-run/reports

./bin/photo-fieldwork validate \
  --master runs/my-run/manifests/proposed-master.csv \
  --holds runs/my-run/manifests/hold-sensitive.csv \
  --config path/to/config.json \
  --evaluation-report runs/my-run/reports/evaluation-report.json \
  --output runs/my-run/reports

./bin/photo-fieldwork plan \
  --master runs/my-run/manifests/proposed-master.csv \
  --holds runs/my-run/manifests/hold-sensitive.csv \
  --config path/to/config.json \
  --source-membership runs/my-run/manifests/frozen-source-membership.csv \
  --evaluation-report runs/my-run/reports/evaluation-report.json \
  --validation-report runs/my-run/reports/validation-report.json \
  --plan-id my-run-v01 \
  --source-title "Wide retrieval - do not edit" \
  --source-identifier SOURCE-ID \
  --output runs/my-run/manifests/catalog-plan.json
```

## Resume and audit a run

Initialize a durable workspace and append editorial decisions without rewriting
history:

```bash
SOURCE_COUNT=REPLACE_WITH_CURRENT_SOURCE_COUNT
photo-fieldwork run init \
  --workspace runs/v01 \
  --run-id v01 \
  --version v01 \
  --target 4000 \
  --source-identifier visible-library-stills://v1 \
  --source-count "$SOURCE_COUNT" \
  --config path/to/config.json \
  --code-version 0.2.0

photo-fieldwork ledger init --ledger runs/v01/decisions.sqlite
photo-fieldwork ledger append \
  --ledger runs/v01/decisions.sqlite \
  --run-id v01 \
  --round-id round-01 \
  --asset-uuid ASSET-UUID \
  --event-type reviewed-fit \
  --actor editor \
  --new-state fit \
  --reason "Visible apparatus and working context"

photo-fieldwork run reconcile --workspace runs/v01 --expected-revision 1
```

The sample manifest binds feedback to the exact master that was sampled. A
changed master requires a fresh sample. If a completed phase gains a reviewed
replacement artifact, accept that transition explicitly with
`--allow-phase-update PHASE` and the current expected revision.

Apply reviewed feedback only when replacement candidates have local pixels and
decodable previews:

```bash
photo-fieldwork round apply \
  --master runs/v01/manifests/proposed-master.csv \
  --inventory runs/v01/manifests/ready-candidates.csv \
  --feedback runs/v01/reports/round-01-feedback.csv \
  --prior-feedback runs/v01/reports/round-00-feedback.csv \
  --round-id round-01 \
  --ledger runs/v01/decisions.sqlite \
  --run-id v01 \
  --output runs/v01/manifests/proposed-master-round-02.csv
```

When `--ledger` is present, prior `reviewed-reject` image-view edges are loaded
from it automatically. `--prior-feedback` is useful when importing older review
history that has not yet been materialized in the ledger.

See [run lifecycle](docs/run-lifecycle.md) and
[decision ledger](docs/decision-ledger.md).

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic, configurable selection engine.
- Safety holds that cannot enter the master.
- Duplicate and burst controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Stratified evaluation samples and precision thresholds.
- A fully synthetic practice run.
- Apple Photos integration guidance and adapter contracts.
- WAL-aware compact snapshots for immutable post-write verification.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), and [the Apple Photos guide](docs/apple-photos.md) before using a private archive.

The production lessons and implementation sequence are recorded in
[Recommendations C](docs/recommendations-C.md).

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
