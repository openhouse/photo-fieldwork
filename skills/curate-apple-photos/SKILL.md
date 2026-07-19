---
name: curate-apple-photos
description: Curate a large, versioned photo corpus from a local Apple Photos library and a pasted brief. Use existing People associations, inspect pixels locally through a permissioned helper, run recursive visual evaluation, quarantine sensitive material, preserve prior versions, and independently verify non-destructive album membership.
---

# Curate Apple Photos

Turn a brief into a locally inspected, recursively evaluated, versioned Apple Photos editor field. Carry the work through Photos commit and independent verification unless the user pauses or a genuine permission or data blocker remains.

## Start

1. Keep requested editorial lenses visible. Their judgments guide interpretation; they are not eyewitnesses, rights holders, consent authorities, or substitutes for an identified human decision. Receipts establish operational facts.
2. Read [machine-profile.md](references/machine-profile.md), then run:

```bash
photo-fieldwork profile check
python3 scripts/photo_archive_bridge.py doctor
python3 scripts/photo_archive_bridge.py probe
```

3. Read [brief-contract.md](references/brief-contract.md). Preserve the user's words in `brief.md`; derive `retrieval.json` and `config.json`.
4. Reserve one semantic version with `photo-fieldwork run init`. Never reuse a version. Put evaluation rounds and experiments inside that run.
5. Freeze the selected source as an exact count plus sorted-membership SHA-256. A source title or historical count is not a source identity.

When resuming, run `photo-fieldwork run status` before doing work. It rechecks both the recorded byte size and SHA-256 of every receipt artifact. If integrity is blocked, do not infer progress from filenames or advance to Photos mutation; preserve the workspace as evidence and begin an explicit recovery run with a new semantic version.

## Governing invariants

- Verify the selected source identifier and live count before work.
- Do not alter source albums, originals, metadata, faces, favorites, dates, locations, or prior versions.
- Never write Photos SQLite.
- Do not upload pixels, previews, OCR, faces, coordinates, or manifests.
- Use existing People names only. Never identify unnamed faces or infer sensitive traits.
- Keep exact private locations and raw OCR out of reports.
- A potential sensitive item enters HOLD before ranking and cannot enter the master.
- Propagate HOLD through exact duplicate, perceptual-match, and burst relations before ranking. Do not clear a related crop, edit, or sequence neighbor independently.
- Preserve `Unclassified / Editor Field`.
- Label project-specific views `EDITOR HYPOTHESIS` unless visible evidence plus provenance supports stronger wording.
- Treat `not recovered` as an evidence result, never as proof that relevant photographs do not exist. Keep hypotheses distinct from provenance.
- Use Apple aesthetic scores only inside genuine duplicate or burst clusters.
- Treat cached previews as verified cache hits, never as newly decoded pixels.
- Treat editor-field membership, consent, rights, claim support, and publication clearance as separate decisions.

Read [safety.md](references/safety.md) whenever a brief concerns private homes, minors, health, legal strategy, financial records, identity documents, or vulnerable collaborators.

## Build the candidate field

1. Build or select the compact read-only inventory named by the profile.
2. Retrieve 1.5-2.0 times the target with `retrieve_candidates.py`. Save diagnostics and make every match explainable.
3. Create an inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run it through the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access remains false.
5. Verify every preview with `verify_preview_exports.py` before looking.
6. Use `cache_previews.py` to record newly decoded pixels, verified cache hits, and missing or corrupt previews separately.
7. Merge local inspection results with `merge_inspection.py`.

Measure fresh inspection by asset and review history, not by whether a preview was copied into the current workspace. Keep declared regression controls separate from the novel evaluation sample.

Record checksummed phase receipts with `photo-fieldwork run record` as work advances.

## Select, look, evaluate, recurse

Read [evaluation-loop.md](references/evaluation-loop.md).

1. Run `photo-fieldwork select`.
2. Read the capacity report. Multi-view candidates must be assigned jointly to exact quotas. If a view has a deficit, report the gap; never pad it, silently change its quota, or coerce unrelated material.
3. Sample low, middle, and high scores from every populated view.
4. Keep tuning, canaries, and the frozen final holdout separate. Run `photo-fieldwork audit-split`; UUID or duplicate, perceptual, or burst relation leakage invalidates the holdout.
5. Generate contact sheets and the local review workbench. Inspect actual previews, opening individual images when context or safety is unclear.
6. Record `fit`, `reject`, or `uncertain`, a visible reason, a safety state, an identified human reviewer, reviewer kind, review round, and error category.
7. Run `photo-fieldwork evaluate`. Read every rejection and representative uncertainty.
8. Revise retrieval, assignments, penalties, quotas, event limits, or hold rules in response to observed errors. Keep the seed fixed.
9. Persist known rejects and historical holds so they cannot return under another label.
10. Repeat until overall and material-view gates pass.
11. Audit the actual frozen field with `--final-field`, including every replacement introduced after an earlier pass. The final report binds the exact config and feedback content.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection.

## Validate and commit

1. Run `photo-fieldwork validate` with the final evaluation report and feedback.
2. Confirm that the master, final evaluation, and validation report share one `proposal_id`, `master_sha256`, `config_sha256`, and `feedback_sha256`.
3. Generate the schema-2 release plan with `photo-fieldwork plan`. Confirm that it binds the frozen source count and membership SHA-256, proposal, master, config, feedback, final evaluation, validation, and its own `plan_sha256`. It must say `release_class: editor-field-verified` and `publication_state: publication-review-required`.
4. Generate helper test and two production-attempt plans with `photo_archive_bridge.py snapshot-plans --release-plan RELEASE_PLAN`. The bridge must reject a stale or altered release plan.
5. Inspect the frozen plans, source identity, target, folder title, HOLD separation, membership-only mode, and `plan_sha256`.
6. Run the ten-item write test and independently verify it.
7. Run both production plans. Preserve both receipts, validate each before comparing them, run `photo_archive_bridge.py compare-attempts`, and independently verify each through compact WAL-aware evidence.
8. Record every phase receipt and generate the completion report from receipts.

## Final response

Return:

- a short editorial discussion;
- folder and master-album names;
- exact master, HOLD, people, uncertainty, and evaluation counts;
- source membership, proposal, master, and plan identities;
- source and prior-version preservation;
- confirmation that no external upload occurred;
- links to the run report, master manifest, evaluation report, app receipt, compact evidence, and independent verification.

State clearly that the result is an editor-ready field, not the final publication edit.

If the user later asks to publish selected photographs, create a default-closed register with `photo-fieldwork publication scaffold` and validate item-level human decisions with `photo-fieldwork publication validate`. Never convert role-play, library ownership, or editor-field membership into publication clearance.
