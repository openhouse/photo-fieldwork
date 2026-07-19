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

The production Apple Photos scripts use Pillow for contact sheets and preview-integrity
checks. Install the declared extra in an isolated environment with `pip install -e '.[photos]'`.

## Use it with your own inventory

1. Copy `config/starter.json` and edit the views, quotas, and thresholds.
2. Declare the source with `schemas/source.schema.json`. When the brief says the whole
   Apple Photos library, use `visible-library-stills://v1`; do not silently substitute a
   prior editor album.
3. Prepare a CSV using `schemas/inventory-fields.md`. Keep retrieval hypotheses in
   `candidate_views`; after looking, record the reviewed decision in `assigned_view`.
4. Cluster local near-duplicates, run selection, and create an evaluation sample.
5. Inspect sampled images locally and record `fit`, `reject`, or `uncertain`.
6. Validate and apply structured feedback. Evaluate per view, revise weak views, and repeat.
7. Freeze the candidate, audit a genuinely unseen holdout, then fully audit every selected
   image. A targeted audit or tuning sample cannot authorize a write.
8. Generate a hash-bound catalog plan. Test ten items before any production write.
9. Verify the committed album membership independently and read-only.

```bash
./bin/photo-fieldwork select \
  --inventory path/to/inventory.csv \
  --config path/to/config.json \
  --output runs/my-run

./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --output runs/my-run/manifests/eval-sample.csv \
  --per-view 3

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
  --config path/to/config.json \
  --output runs/my-run/reports

# Before opening a final holdout, prove it is disjoint from tuning and canary evidence.
python3 skills/curate-apple-photos/scripts/audit_eval_split.py \
  --tuning runs/my-run/manifests/eval-round-01.csv \
  --tuning runs/my-run/manifests/eval-round-02.csv \
  --canary runs/my-run/manifests/regression-canaries.csv \
  --holdout runs/my-run/manifests/final-holdout.csv \
  --output runs/my-run/reports/holdout-split-audit.json

# After an interruption, inspect artifact hashes and the next incomplete phase.
./bin/photo-fieldwork state resume --workspace runs/my-run

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

- A deterministic, configurable selection engine.
- Safety holds that cannot enter the master.
- Exact, burst, and local perceptual duplicate controls.
- Named-people and visible-apparatus signals.
- An unclassified editor field for honest uncertainty.
- Stratified evaluation samples and precision thresholds.
- Per-view evaluation gates and targeted follow-up rounds.
- Reviewed assignments separated from retrieval hypotheses.
- Frozen proposal hashes, structured feedback, and full-master write authorization.
- Inventory sensitivity profiles and a conservative public-report linter.
- Resumable run state with artifact hashes.
- A fully synthetic practice run.
- Versioned source profiles, whole-library inventory support, and adapter capability checks.
- Fail-closed preview validation and WAL-aware independent verification.
- An adversarial skill-eval bank and executable holdout-leakage audit.
- Exact per-view quota enforcement with actionable scarcity diagnostics.
- Append-only, hash-chained human decision lineage with related-frame safety propagation.
- Candidate-bound release seals and receipt identity checks before catalog mutation.
- A separate, default-closed publication review after editor-field verification.
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

The skill integrates with the installed `/Applications/Jamie Photo Archive.app`, preserving its stable Photos permission identity. Its reviewed source is retained under `integrations/jamie-photo-archive/`; replacing or rebuilding the installed app is a separate, explicit operation because macOS may request Photos authorization again.
