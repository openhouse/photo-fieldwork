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

1. Copy `config/starter.json` and edit the views, quotas, safety states, release class, and thresholds.
2. Freeze a source manifest using `schemas/source-manifest.schema.json`.
3. Prepare a CSV using `schemas/inventory-fields.md`. Keep retrieval hypotheses in `candidate_views` and put the reviewed editorial decision in `assigned_view`.
4. Run the selection and create an evaluation sample.
5. Inspect sampled images locally and record `fit`, `reject`, or `uncertain`.
6. Validate and apply structured feedback, then evaluate, revise, and repeat until overall and per-view criteria pass.
7. Bind the final evaluation to the exact master and source. Generate a catalog plan only after the requested release class passes.
8. Test ten items before production, then verify the committed membership independently and read-only.

```bash
./bin/photo-fieldwork select \
  --inventory path/to/inventory.csv \
  --config path/to/config.json \
  --output runs/my-run

./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --output runs/my-run/manifests/eval-sample.csv \
  --per-view 3 \
  --exclude-feedback runs/prior-round/manifests/eval-feedback.csv \
  --canaries path/to/regression-canaries.csv

./bin/photo-fieldwork feedback-validate \
  --feedback runs/my-run/manifests/eval-feedback.csv \
  --output runs/my-run/reports/feedback-validation.json

./bin/photo-fieldwork feedback-apply \
  --sample runs/my-run/manifests/eval-sample.csv \
  --feedback runs/my-run/manifests/eval-feedback.csv \
  --output runs/my-run/manifests/eval-sample-labeled.csv

./bin/photo-fieldwork evaluate \
  --feedback runs/my-run/manifests/eval-sample-labeled.csv \
  --master runs/my-run/manifests/proposed-master.csv \
  --source-manifest runs/my-run/manifests/source-manifest.json \
  --scope final-stratified-sample \
  --config path/to/config.json \
  --output runs/my-run/reports

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
  --source-manifest runs/my-run/manifests/source-manifest.json \
  --evaluation-report runs/my-run/reports/evaluation-report.json \
  --output runs/my-run/manifests/catalog-plan.json
```

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Those are different questions. Photo Fieldwork keeps them different.

## What is included

- A deterministic, configurable selection engine.
- Safety holds that cannot enter the master.
- Exact, burst, and local perceptual duplicate controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Frozen proposal hashes, structured feedback, and overall plus per-view evaluation gates.
- Explicit evaluation scopes and release classes that distinguish sampled field verification from full-master and publication review.
- Versioned album and whole-visible-library source contracts.
- Source, configuration, master, hold, plan, helper, receipt, and verification provenance hashes.
- Resumable run-state transitions and independently typed JSON/Markdown verification reports.
- A fully synthetic practice run.
- Apple Photos integration guidance and adapter contracts.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), and [the Apple Photos guide](docs/apple-photos.md) before using a private archive. Existing configurations should read the [Revision B migration guide](docs/revision-B.md). Product rationale and sequenced follow-ons are preserved in [recommendations-B.md](recommendations-B.md).

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

Install the local review dependency before using contact sheets or perceptual clustering:

```bash
python3 -m pip install -e '.[review]'
```

## Evaluate the skill safely

The bundled skill includes sixteen synthetic decision drills covering source drift, interruption, safety, evaluation leakage, unsupported views, helper compatibility, preview integrity, publication boundaries, public-report privacy, topology, People context, configuration drift, circular evidence, uncertain dates, and conflicting feedback. The control case confirms that a fully evidenced editor field can complete instead of being reflexively blocked.

Validate the bank without accessing Apple Photos:

```bash
python3 skills/curate-apple-photos/scripts/validate_skill_evals.py \
  --evals skills/curate-apple-photos/evals/evals.json
```

See [the eval methodology and hill-climb results](skills/curate-apple-photos/evals/README.md).
