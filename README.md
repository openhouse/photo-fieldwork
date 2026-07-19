# Photo Fieldwork

Photo Fieldwork is a local-first practice and production workflow for reducing a large personal photo archive into a smaller, editor-ready field of possibilities.

It does not automate taste. It helps people automate retrieval, deduplication, balancing, safety review, provenance, evaluation, and reversible handoff while keeping final editorial judgment human.

The Revision I composite binds source, retrieval policy, exact view assignment,
fresh visual evaluation, catalog plans, execution receipts, and live
verification to one candidate. It also adds whole-visible-library source
support, private run workspaces, WAL-aware read-only Photos verification,
regression canaries, and a destination-scoped public handoff.

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
2. Prepare a CSV using `schemas/inventory-fields.md`. Keep retrieval hypotheses in `candidate_views` and put the reviewed editorial decision in `assigned_view`.
3. Run the selection and create an evaluation sample.
4. Inspect sampled images locally and record `fit`, `reject`, or `uncertain`.
5. Validate and apply structured feedback, then evaluate, revise, and repeat until overall and per-view criteria pass.
6. Freeze and fully evaluate the final master. Generate a catalog write plan bound to that evaluation by `master_sha256`. Test ten items before any production write.
7. Verify the committed album membership independently and read-only.

```bash
./bin/photo-fieldwork select \
  --inventory path/to/inventory.csv \
  --config path/to/config.json \
  --output runs/my-run

./bin/photo-fieldwork sample \
  --master runs/my-run/manifests/proposed-master.csv \
  --config path/to/config.json \
  --output runs/my-run/manifests/eval-sample.csv \
  --round-id round-02 \
  --sampling-history runs/my-run/manifests/sampling-history.json

./bin/photo-fieldwork evaluate \
  --feedback runs/my-run/manifests/eval-sample.csv \
  --master runs/my-run/manifests/proposed-master.csv \
  --config path/to/config.json \
  --sampling-history runs/my-run/manifests/sampling-history.json \
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

The sampling history has exactly two arrays: prior ordinary review IDs in
`excluded_ids`, and stable regression examples in `canary_ids`. Pass the same
file to `sample` and `evaluate`; its digest becomes part of the candidate.

An editor field is not a publication shortlist. After independent human
rights, consent, claim, and destination review, create a separate allowlisted
derivative with `photo-fieldwork public-handoff`. See the
[Revision I composite guide](docs/revision-I.md) for the gated command.

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
- Per-view evaluation gates and Wilson interval reporting.
- Proposal hashes that bind assignments, evaluation, and catalog plans.
- Fresh-round sampling with separately scored regression canaries.
- Private-by-default run artifacts and a resumable checksum ledger.
- A fully synthetic practice run.
- Album and whole-library Apple Photos source profiles.
- WAL-aware read-only inventory and verification adapters.
- A destination-scoped, allowlisted public-handoff derivative.
- A case study of how visual inspection changed a real workflow.

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A claim that the generated corpus is the final edit.

Read [the workflow](docs/workflow.md), [the architecture](docs/architecture.md), [the safety model](docs/safety.md), and [the Apple Photos guide](docs/apple-photos.md) before using a private archive. Existing configurations should also read the [Revision I composite guide](docs/revision-I.md). The observed product rationale is preserved in [recommendations-I.md](recommendations-I.md).

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
