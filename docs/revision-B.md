# Revision B migration guide

Revision B makes the source, evaluation scope, safety state, helper build, plan, receipt, and verification part of one release contract. It intentionally rejects workflows that Revision I could still describe ambiguously.

## Install review dependencies

The core remains standard-library Python. Apple Photos review scripts use Pillow:

```bash
python3 -m pip install -e '.[review]'
```

## Create a local profile

Copy `config/local-profile.example.json` to `config/local-profile.json` and add private machine paths and protected folder identifiers. The real profile is gitignored. Do not commit it.

## Freeze a source manifest

Every production run requires a schema-version-1 source manifest. A whole-visible-library inventory creates one automatically:

```bash
python3 skills/curate-apple-photos/scripts/build_visible_library_inventory.py \
  --output PRIVATE/source.sqlite \
  --source-manifest PRIVATE/source-manifest.json \
  --inventory-profile retrieval
```

The manifest binds adapter, identifier, predicate version, observed count, membership digest, and source fingerprint. Same-count membership drift now blocks independent verification.

## Update configuration

Add these Revision B fields:

```json
{
  "required_release_class": "editor-field-verified",
  "evaluation_scope": "final-stratified-sample",
  "eligible_safety_states": ["clear", "clear-automated", "cleared-human"]
}
```

The supported release classes are:

- `editor-field-verified`: a source-bound, master-bound final stratified sample may qualify;
- `master-human-reviewed`: requires `full-master` scope and every master row judged;
- `publication-ready`: requires a complete `publication-shortlist` plus rights, consent, caption, and accessibility clearance.

## Migrate safety states

Legacy values remain readable, but new runs should use:

- `clear-automated`;
- `needs-human-review`;
- `cleared-human`;
- `hold-automated`;
- `hold-human`.

Only configured eligible states may enter selection. Hidden, missing, held, and unresolved review rows enter the private hold output before ranking.

## Migrate evaluation

Evaluation now requires the exact master and source manifest:

```bash
bin/photo-fieldwork evaluate \
  --feedback RUN/manifests/eval-sample-labeled.csv \
  --master RUN/manifests/proposed-master.csv \
  --source-manifest RUN/manifests/source-manifest.json \
  --scope final-stratified-sample \
  --config RUN/config.json \
  --output RUN/reports/final-evaluation
```

New samples carry `sample_sha256` and `master_count`. Feedback must preserve `sample_sha256`. Duplicate UUID judgments are rejected.

`fresh_sample_completion` replaces ambiguous use of coverage. `master_review_fraction` has a separate denominator. Canary judgments are reported separately and never improve fresh precision.

## Migrate plan generation

Core plan generation now requires holds and the source manifest:

```bash
bin/photo-fieldwork plan \
  --master RUN/manifests/proposed-master.csv \
  --holds RUN/manifests/hold-sensitive.csv \
  --source-manifest RUN/manifests/source-manifest.json \
  --evaluation-report RUN/reports/final-evaluation/evaluation-report.json \
  --config RUN/config.json \
  --plan-id RUN-ID \
  --output RUN/manifests/catalog-plan.json
```

Schema-version-2 plans bind:

- `source_fingerprint`;
- `config_sha256` for the evaluated thresholds, safety states, views, and release policy;
- `proposal_id` and `master_sha256`;
- `hold_sha256`;
- evaluation `sample_sha256`, scope, and release class;
- exact `plan_sha256`;
- required helper revision for Apple Photos plans.

Revision I plan schema 1 is intentionally rejected by the Revision B helper.

## Install the reviewed helper before production

Revision B helper source reports app version 3.0, helper revision `revision-B`, and inspection/snapshot schema 2. Rebuild or install it through the existing explicit permission-preserving process, then run:

```bash
python3 skills/curate-apple-photos/scripts/photo_archive_bridge.py doctor \
  --profile config/local-profile.json \
  --source-manifest RUN/manifests/source-manifest.json
```

Do not run a Revision B production plan when capability checks fail.

## Resume and verify

`run-state.json` now preserves phase records, attempts, plan paths, receipts, and next actions. An interrupted recorded app plan can be resumed:

```bash
python3 skills/curate-apple-photos/scripts/photo_archive_bridge.py resume \
  --workspace RUN \
  --profile config/local-profile.json
```

Inspection resume receipts recompute pixel, preview, hold, and unavailable totals from existing validated rows. Duplicate or corrupt checkpoint rows fail loudly.

Independent verification now recomputes source membership and compares plan, helper receipt, album membership, configuration, master, holds, release class, and plan hash.

## Rollback

Revision B does not rename or mutate prior Photos versions. If migration is incomplete, preserve the run as interrupted and continue using the prior helper only with its matching prior-schema plan. Never send a schema-2 plan to an unverified helper and never rewrite a prior receipt.
