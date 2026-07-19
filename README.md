# Photo Fieldwork

Photo Fieldwork is a local-first practice and production workflow for reducing a large personal photo archive into a smaller, editor-ready field of possibilities.

It does not automate taste. It helps people automate retrieval, deduplication, balancing, safety review, provenance, evaluation, and reversible handoff while keeping final editorial judgment human.

Version 0.2 binds retrieval, explicit view assignment, visual evaluation, and
catalog plans to one hashed proposal. It also adds whole-visible-library source
support, private run workspaces, WAL-aware read-only Photos verification, and a
resumable phase and artifact ledger.

The Revision H composite adds an offline human-review workbench, holdout leakage
auditing, a destination-scoped public handoff, and a mutation-resistant
evaluation-of-evaluation contract around that production spine.

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
6. Audit holdout independence before using holdout results as release evidence.
7. Generate a catalog write plan. Test ten items before any production write.
8. Verify the committed album membership independently and read-only.
9. Treat any public-use handoff as a separate human-governed release.

```bash
./bin/photo-fieldwork select \
  --inventory path/to/inventory.csv \
  --config path/to/config.json \
  --output runs/my-run

./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --config path/to/config.json \
  --output runs/my-run/manifests/eval-sample.csv \
  --round-id round-01

./bin/photo-fieldwork evaluate \
  --feedback runs/my-run/manifests/eval-sample.csv \
  --master runs/my-run/manifests/proposed-master.csv \
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
  --feedback runs/my-run/manifests/eval-sample.csv \
  --config path/to/config.json \
  --evaluation-report runs/my-run/reports/evaluation-report.json \
  --validation-report runs/my-run/reports/validation-report.json \
  --plan-id my-run-v01 \
  --source-title "Wide retrieval - do not edit" \
  --source-identifier SOURCE-ID \
  --source-count SOURCE-COUNT \
  --source-sha256 SOURCE-IDENTIFIER-SHA256 \
  --output runs/my-run/manifests/catalog-plan.json
```

Build a private offline review surface and audit the evaluation split:

```bash
./bin/photo-fieldwork build-review \
  --sample runs/my-run/manifests/eval-sample.csv \
  --previews runs/my-run/previews/evaluation \
  --output runs/my-run/review/index.html

./bin/photo-fieldwork audit-holdout \
  --tuning runs/my-run/manifests/tuning.csv \
  --canary runs/my-run/manifests/canaries.csv \
  --holdout runs/my-run/manifests/holdout.csv \
  --output runs/my-run/reports/holdout-audit.json
```

The optional `public-handoff` command emits only positively cleared,
destination-matching rows under salted opaque IDs. Its salt and blocked-row
report stay private. See [the operator runbook](docs/operator-runbook.md).

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
- Per-view evaluation gates and Wilson interval reporting.
- Proposal hashes that bind assignments, evaluation, and catalog plans.
- Private-by-default run artifacts and a resumable checksum ledger.
- A loopback-only, network-blocked review workbench.
- Direct and relation-level holdout leakage auditing.
- A public allowlist separated from private remediation evidence.
- A fully synthetic practice run.
- Album and whole-library Apple Photos source profiles.
- WAL-aware read-only inventory and verification adapters.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md),
[the safety model](docs/safety.md), [the composite design](docs/composite.md),
[the operator runbook](docs/operator-runbook.md), and
[the Apple Photos guide](docs/apple-photos.md) before using a private archive.

## Use it as a Codex skill

Install the bundled `curate-apple-photos` skill:

```bash
make install-skill
```

Before production use, copy
`skills/curate-apple-photos/references/machine-profile.example.json` to the
private path described in
`skills/curate-apple-photos/references/machine-profile.md`. The completed file
must remain outside git with mode `0600`.

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

The app path and bundle identifier are now read from the private machine
profile; the path above is an example of an existing installation, not a public
configuration default.

Read [the revision M implementation note](docs/revision-M.md) and
[the recovery guide](docs/recovery.md) before running the Apple Photos adapter.
Revision H's selective integration is documented in
[the composite implementation note](docs/revision-H.md).
