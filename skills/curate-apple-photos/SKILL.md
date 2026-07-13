---
name: curate-apple-photos
description: Curate a large, versioned photo corpus from a local Apple Photos library and a pasted brief. Use existing People associations, inspect pixels locally through a permissioned helper, run recursive visual evaluation, quarantine sensitive material, preserve prior versions, and independently verify non-destructive album membership.
---

# Curate Apple Photos

Turn a brief into a locally inspected, recursively evaluated, versioned Apple Photos editor field. Carry the work through Photos commit and independent verification unless the user pauses or a genuine permission or data blocker remains.

## Start

1. Keep requested editorial lenses visible. Their judgments guide interpretation; receipts establish operational facts.
2. Read [machine-profile.md](references/machine-profile.md), then run:

```bash
photo-fieldwork profile check
python3 scripts/photo_archive_bridge.py doctor
python3 scripts/photo_archive_bridge.py probe
```

3. Read [brief-contract.md](references/brief-contract.md). Preserve the user's words in `brief.md`; derive `retrieval.json` and `config.json`.
4. Reserve one semantic version with `photo-fieldwork run init`. Never reuse a version. Put evaluation rounds and experiments inside that run.

## Governing invariants

- Verify the selected source identifier and live count before work.
- Do not alter source albums, originals, metadata, faces, favorites, dates, locations, or prior versions.
- Never write Photos SQLite.
- Do not upload pixels, previews, OCR, faces, coordinates, or manifests.
- Use existing People names only. Never identify unnamed faces or infer sensitive traits.
- Keep exact private locations and raw OCR out of reports.
- A potential sensitive item enters HOLD before ranking and cannot enter the master.
- Preserve `Unclassified / Editor Field`.
- Label project-specific views `EDITOR HYPOTHESIS` unless visible evidence plus provenance supports stronger wording.
- Use Apple aesthetic scores only inside genuine duplicate or burst clusters.
- Treat cached previews as verified cache hits, never as newly decoded pixels.

Read [safety.md](references/safety.md) whenever a brief concerns private homes, minors, health, legal strategy, financial records, identity documents, or vulnerable collaborators.

## Build the candidate field

1. Build or select the compact read-only inventory named by the profile.
2. Retrieve 1.5-2.0 times the target with `retrieve_candidates.py`. Save diagnostics and make every match explainable.
3. Create an inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run it through the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access remains false.
5. Verify every preview with `verify_preview_exports.py` before looking.
6. Use `cache_previews.py` to record newly decoded pixels, verified cache hits, and missing or corrupt previews separately.
7. Merge local inspection results with `merge_inspection.py`.

Record checksummed phase receipts with `photo-fieldwork run record` as work advances.

## Select, look, evaluate, recurse

Read [evaluation-loop.md](references/evaluation-loop.md).

1. Run `photo-fieldwork select`.
2. Sample low, middle, and high scores from every populated view.
3. Generate contact sheets and the local review workbench. Inspect actual previews, opening individual images when context or safety is unclear.
4. Record `fit`, `reject`, or `uncertain`, a visible reason, a safety state, and an error category.
5. Run `photo-fieldwork evaluate`. Read every rejection and representative uncertainty.
6. Revise retrieval, assignments, penalties, quotas, event limits, or hold rules in response to observed errors. Keep the seed fixed.
7. Persist known rejects and historical holds so they cannot return under another label.
8. Repeat until overall and material-view gates pass.
9. Audit the actual frozen field with `--final-field`, including every replacement introduced after an earlier pass.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection.

## Validate and commit

1. Run `photo-fieldwork validate` with the final evaluation report and feedback.
2. Generate test and production plans with `photo_archive_bridge.py snapshot-plans`.
3. Inspect the frozen plans, source count, target, folder title, HOLD separation, and membership-only mode.
4. Run the ten-item write test and independently verify it.
5. Run production, rerun it once for idempotence, and independently verify it through compact WAL-aware evidence.
6. Record every phase receipt and generate the completion report from receipts.

## Final response

Return:

- a short editorial discussion;
- folder and master-album names;
- exact master, HOLD, people, uncertainty, and evaluation counts;
- source and prior-version preservation;
- confirmation that no external upload occurred;
- links to the run report, master manifest, evaluation report, app receipt, compact evidence, and independent verification.

State clearly that the result is an editor-ready field, not the final publication edit.
