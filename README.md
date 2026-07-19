# Photo Fieldwork

Photo Fieldwork is a local-first field instrument for turning a large personal photo archive into a smaller, inspectable, reversible field for human editors.

It does not automate taste. It supports retrieval, deduplication, balancing, safety holds, recursive visual evaluation, provenance, reversible catalog handoff, and independent verification while keeping editorial judgment human.

## Try it in two minutes

Requirements: Python 3.11 or newer. The practice workflow has no third-party dependencies and does not access Apple Photos.

```bash
make demo
make check
```

The demo creates synthetic records under `runs/practice/`, selects a deterministic master, isolates safety holds, evaluates the frozen field, validates executable gates, builds a membership-only plan, and generates a local review workbench.

## The central distinction

Metadata answers: "Why might this photograph be relevant?"

Visible evidence answers: "What can an editor actually see here?"

Provenance answers: "What can we responsibly claim about it?"

Consent answers: "May this be published in this context?"

Those are different questions. Photo Fieldwork keeps them different.

## Production setup

Production access is configured outside Git. Copy the example profile and replace every placeholder with local values:

```bash
mkdir -p ~/.config/photo-fieldwork
cp config/machine-profile.example.json ~/.config/photo-fieldwork/profile.json
photo-fieldwork profile check
```

Set `PHOTO_FIELDWORK_PROFILE` or pass `--profile` to use another profile. Do not commit a populated profile.

The profile identifies:

- the private run workspace;
- the local Photos database used read-only;
- the stable permissioned helper app;
- named source contracts and expected counts;
- protected root, HOLD, and audit folders.

## Receipt-backed runs

Reserve one semantic version before doing production work:

```bash
photo-fieldwork run init \
  --root ~/Documents/Photo-Fieldwork-Runs \
  --version v01-A \
  --slug portfolio-editor-field \
  --target 4000 \
  --source-identifier visible-library-stills://v1 \
  --source-count 100000 \
  --code-commit "$(git rev-parse HEAD)"
```

Record each phase with checksummed input and output artifacts:

```bash
photo-fieldwork run record \
  --workspace RUN \
  --phase preflight \
  --status pass \
  --output RUN/reports/preflight.json

photo-fieldwork run status --workspace RUN
photo-fieldwork run report --workspace RUN
photo-fieldwork run cleanup-report --workspace RUN
```

The required phase order is preflight, retrieval, inspection, review, validation, write test, production commit, and independent verification. `complete` is derived from append-only receipts; it is not a manually asserted status. Status derivation rechecks the size and SHA-256 of every recorded artifact. A missing or changed artifact blocks the run instead of trusting stale phase text.

## Select, evaluate, and validate

```bash
photo-fieldwork select \
  --inventory RUN/manifests/ready-candidates.csv \
  --config RUN/config.json \
  --output RUN

photo-fieldwork sample \
  --master RUN/manifests/proposed-master.csv \
  --output RUN/evaluations/final-field.csv \
  --per-view 3

photo-fieldwork review \
  --feedback RUN/evaluations/final-field.csv \
  --previews RUN/previews \
  --output RUN/reports/review-workbench.html

photo-fieldwork evaluate \
  --feedback RUN/evaluations/final-field.csv \
  --config RUN/config.json \
  --output RUN/reports/final-evaluation \
  --final-field

photo-fieldwork validate \
  --master RUN/manifests/proposed-master.csv \
  --holds RUN/manifests/hold-sensitive.csv \
  --config RUN/config.json \
  --evaluation-report RUN/reports/final-evaluation/evaluation-report.json \
  --final-feedback RUN/evaluations/final-field.csv \
  --output RUN/reports/final-validation
```

Validation enforces exact view quotas, evaluation coverage and precision, material-view precision, replacement review, HOLD and known-reject exclusion, event concentration, evidence lineage, and configured representation floors.

Create a release-bound membership plan only after final evaluation and validation pass:

```bash
photo-fieldwork plan \
  --master RUN/manifests/proposed-master.csv \
  --config RUN/config.json \
  --plan-id RUN-ID-production \
  --source-title "Visible library stills" \
  --source-identifier visible-library-stills://v1 \
  --source-count LIVE_SOURCE_COUNT \
  --source-membership-sha256 SOURCE_MEMBERSHIP_SHA256 \
  --evaluation-report RUN/reports/final-evaluation/evaluation-report.json \
  --validation-report RUN/reports/final-validation/validation-report.json \
  --output RUN/plans/catalog-plan.json
```

The plan carries source, proposal, master, exact evaluation-report, exact validation-report, and plan identities. Replacing an image, changing its assigned view, or changing either release report invalidates the old release evidence.

## Evaluation bank

`make evals` runs the synthetic release-contract bank, including feasible overlap assignment, explicit infeasibility, stale-evaluation rejection, receipt drift, protected states, weak-view detection, replacement audits, plan tampering, and a deterministic 4,000-item assignment. See [`evals/README.md`](evals/README.md) for the prompt bank and recursive hill-climb record.

## Apple Photos integration

The bundled `curate-apple-photos` skill and helper adapter add:

- whole-visible-library or album source contracts;
- local PhotoKit inspection with network access disabled;
- optional local Vision classification, OCR safety flags, and face counts;
- preview decode verification and a transparent local cache;
- test-first, membership-only Photos plans;
- compact WAL-aware verification evidence.

The helper source is a template. Existing signed installations should retain their stable bundle identity unless the operator deliberately accepts a new Photos permission prompt.

Install the core CLI before linking the skill:

```bash
python3 -m pip install -e .
make install-skill
```

## What is not included

- Cloud image analysis.
- Face identification.
- Aesthetic ranking across unrelated photographs.
- Direct writes to Photos SQLite.
- A general archive browser.
- A claim that an editor field is a final publication edit.

Start with [the workflow](docs/workflow.md), [the operator runbook](docs/operator-runbook.md), [the safety model](docs/safety.md), and [the architecture](docs/architecture.md).
