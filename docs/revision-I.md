# Revision I migration guide

Revision I makes the artifact that passes evaluation the artifact that can be written. It intentionally tightens several previously implicit contracts.

## Configuration schema 2

Add these fields to an existing config:

```json
{
  "schema_version": 2,
  "minimum_view_eval_precision": 0.65,
  "minimum_view_eval_sample": 2,
  "maximum_eval_uncertainty": 0.25
}
```

Each view may set `evaluation_mode` to `material` or `sparse-hypothesis`, and may override `minimum_eval_precision`. A material view can no longer inherit success from the overall metric.

## Explicit assignments

`candidate_views` remains retrieval evidence. It is never interpreted as the final assignment.

Every eligible inventory row now requires:

- `assigned_view`;
- `assignment_status`: `assigned`, `unclassified`, or `sparse-hypothesis`;
- `assignment_reason`;
- `assignment_version`.

The retrieval helper creates an initial explicit assignment from its highest metadata score. Local inspection and editorial review may revise that assignment without rewriting the retrieval hypotheses.

## Frozen proposals

Selection adds `proposal_id` and `master_sha256` to the master. Evaluation samples preserve both values. Feedback rows must preserve them as well.

`photo-fieldwork sample` accepts repeated `--exclude-feedback` files for fresh rounds and `--canaries` for a stable regression set. Canary regressions block release but do not count as fresh per-view coverage.

Use the structured feedback commands before evaluation:

```bash
photo-fieldwork feedback-validate \
  --feedback manifests/eval-feedback.csv \
  --output reports/feedback-validation.json

photo-fieldwork feedback-apply \
  --sample manifests/eval-sample.csv \
  --feedback manifests/eval-feedback.csv \
  --output manifests/eval-sample-labeled.csv
```

Catalog and Photos snapshot plans now require a passing final evaluation report. Plan generation fails if its proposal or master hash differs from the current master.

## Source snapshots and privacy profiles

The permissioned app and independent verifier accept album identifiers and `visible-library-stills://v1`.

The whole-library inventory builder accepts:

```bash
python3 skills/curate-apple-photos/scripts/build_visible_library_inventory.py \
  --output inventory/visible-library.sqlite \
  --inventory-profile retrieval \
  --expected-source-count OBSERVED_COUNT
```

`--expected-source-count` is optional during discovery and explicit during a frozen run. The builder no longer contains a machine-specific expected count, and its metadata records a SHA-256 digest of the sorted source membership so same-count drift remains detectable.

Profiles:

- `minimal`: no people, album, keyword, search-description, title, description, exact-coordinate, or source-path data;
- `retrieval`: relationship and retrieval context without exact coordinates or source paths;
- `debug`: private-operational evidence including exact coordinates and the local source path.

## Pixel and review evidence

Run `verify_preview_exports.py` before selection. Missing or corrupt pixels should enter HOLD.

Run `cluster_perceptual_duplicates.py` to add local difference hashes and `perceptual_cluster_id`. The selector reduces these clusters before filling quotas.

`make_contact_sheets.py` accepts repeated `--previews` directories and writes `contact-sheet-index.csv` with stable page, row, column, assignment, safety, and preview status.

## Reports and run state

`verify_photos_commit.py` writes valid JSON for `.json` and Markdown for `.md` or `.markdown`; other extensions fail.

`lint_public_report.py` catches exact-coordinate keys, raw OCR fields, credential-like fields, and local user or volume paths before publication review.

`photo_archive_bridge.py run-plan` records atomic `running`, `completed`, and `failed` transitions when a plan belongs to a versioned run workspace. Inspect them with:

```bash
python3 skills/curate-apple-photos/scripts/photo_archive_bridge.py status \
  --workspace RUN
```

These state transitions make interruption visible. Full batch-level resume remains a later integration milestone.
