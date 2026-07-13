---
name: curate-apple-photos
description: Curate a large, versioned photo corpus from Jamie Burkart's local Apple Photos library from a pasted curatorial brief. Use when asked to create a 5k, 6k, 8k, or other editor-ready Photos album or folder of albums; role-play a named peer panel; use existing People associations; locally inspect pixels through the permissioned Jamie Photo Archive app; run recursive visual evaluation; quarantine sensitive material; preserve prior versions; and commit and independently verify non-destructive album membership.
---

# Curate Apple Photos

Turn the user's brief into a locally inspected, recursively evaluated, versioned Apple Photos editor field. Carry the work through Photos commit and independent verification unless the user pauses it or a genuine permission/data blocker remains.

## Start

1. Keep requested role-play speakers visible in commentary and final discussion. Their judgments guide interpretation; scripts and receipts establish operational facts.
2. Read [machine-profile.md](references/machine-profile.md), then run:

```bash
python3 scripts/photo_archive_bridge.py doctor
```

Pass the intended source identifier and exact observed count to `doctor`. Treat any failed helper identity, inventory integrity, live source count, or free-space check as a blocker.

3. Read [brief-contract.md](references/brief-contract.md). Convert the pasted brief into:
   - `brief.md`, preserving the user's words;
   - `retrieval.json`, defining views, terms, people, albums, places, and supporting date ranges;
   - `config.json`, defining target, quotas, seed, uncertainty view, and evaluation thresholds.
4. Initialize a uniquely named run under `/Users/jburkart/Documents/Jamie-Photo-Archive-2026/` with `photo_archive_bridge.py init-run`. Never reuse or overwrite v00, v01, v02, or another run.
5. Preserve `run-state.json`. Advance it one phase at a time with `photo-fieldwork run-advance`, attaching the files that prove each phase. Use `run-verify` before resuming an interrupted run.

## Governing invariants

- Match the source to the brief. Use the existing wide album for bounded retrieval; use `visible-library-stills://v1` when the user asks for the whole visible library. Verify the identifier and live count before work.
- Do not alter source albums, originals, metadata, faces, favorite status, dates, locations, or prior versions.
- Never write Photos SQLite. The permissioned app may only inspect locally or create folders/albums and add existing membership.
- Do not upload pixels, previews, OCR, faces, coordinates, or manifests.
- Use existing People names. Never identify unnamed faces or infer sensitive traits.
- Keep exact private locations and raw OCR out of reports.
- A potential sensitive item enters HOLD before ranking and cannot enter the master.
- Preserve `Unclassified / Editor Field`. Do not force every photograph into a project story.
- Label project-specific views `EDITOR HYPOTHESIS` unless visible evidence plus provenance supports stronger wording.
- Apple aesthetic scores may break ties only inside true duplicate or burst clusters.
- Dates support retrieval but are not narrative authority; imported film and scans may be misdated.

Read [safety.md](references/safety.md) whenever a brief concerns private homes, minors, health, legal strategy, financial records, identity documents, or vulnerable collaborators.

## Build the candidate field

1. Query the shared read-only inventory:

```bash
python3 scripts/retrieve_candidates.py \
  --db /Users/jburkart/Documents/Jamie-Photo-Archive-2026/shared/wide-corpus.sqlite \
  --retrieval RUN/retrieval.json \
  --target TARGET \
  --output RUN/manifests/candidate-pool.csv
```

For a whole-library run, first create a new immutable inventory with `build_visible_library_inventory.py`. Never overwrite an earlier inventory. Use its `retrieval` profile unless exact coordinates or source paths are explicitly required; those values are omitted by default.

2. Aim for 1.5-2.0 times the requested master size after metadata retrieval. Include named relationships, prior favorites/edits, person-free material context, and exploratory results.
3. Generate a local inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access must remain false. Export 1280px previews into the private run workspace; raw OCR is never written.
5. Run `verify_preview_exports.py`. Missing or corrupt previews are not visually reviewed and must be repaired, re-exported, or held.
6. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.

Use `photo-fieldwork candidate-union`, `candidate-subtract`, and `inspection-merge` instead of run-specific merge scripts. Preserve `retrieval_provenance_json`; it records why an item entered the candidate field without claiming that the hypothesis is true.

## Select, look, evaluate, recurse

Read [evaluation-loop.md](references/evaluation-loop.md) before the first visual round.

1. Run the project selector:

```bash
/Volumes/16TB_SSD/Sites/photo-fieldwork/bin/photo-fieldwork select \
  --inventory RUN/manifests/ready-candidates.csv \
  --config RUN/config.json \
  --output RUN
```

2. Create a score-stratified sample from every view. For the first round, inspect at least 3 per view and at least 36 overall. Later rounds should normally inspect 60-100 images across low, middle, and high scores.
3. Build the offline review surface with `photo-fieldwork review` and contact sheets with `make_contact_sheets.py`. Use `view_image` to inspect every sheet. Open individual previews when context or safety is unclear.
4. Speak briefly as the requested peers. If Jamie cannot review, role-play Jamie using the supplied brief and voice references, while marking the judgment as delegated editorial inference rather than eyewitness fact.
5. Record `fit`, `reject`, or `uncertain`, one visible reason, a safety state, provenance state, reviewer actor/lens, and error category in the evaluation CSV.
6. Append feedback with `photo-fieldwork decisions-append`, then apply the ledger to the next candidate field with `decisions-apply`. A rejected item/view pair must not silently reenter; safety holds propagate through duplicate and burst clusters.
7. Run `photo-fieldwork evaluate`. Read all rejections and a stratified uncertainty sample. Overall averages cannot hide a weak view: every configured view needs enough decisive judgments and must meet its precision threshold.
8. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately.
9. Repeat until:
   - evaluation coverage and precision meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

Before validation, run `photo-fieldwork replacement-audit` against all evaluation rounds. Review every final entrant absent from earlier evaluation records.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Run `photo-fieldwork validate`. Save a PASS report.
2. Generate test and production plans with `photo_archive_bridge.py snapshot-plans`.
3. Inspect the plans. Confirm the source count, target count, folder title, HOLD separation, and that operations are membership-only.
4. Run the ten-item write test through the app. Independently verify it with `verify_photos_commit.py`.
5. Run the production plan through the app. Rerun it once to confirm idempotence.
6. Independently verify every album against the plan using read-only, immutable SQLite access.
7. Register the completed version manifest and verification receipt with `photo-fieldwork version-register`; run `version-verify` before declaring completion.
8. Generate an uncleared `publication-clearance.csv` with `publication-scaffold`. Editor-field membership is not publication permission. Only rows with rights, consent, caption provenance, credit, accessibility, sensitive-context review, destination, and review date may pass `publication-validate`.
9. Update `run-state.json` after each phase and write a completion report containing exact counts, identifiers, review-state counts, evaluation results, privacy facts, and unresolved uncertainty.

The helper invocation may require a Codex permission approval for `open -W`; request a reusable approval scoped to `/Applications/Jamie Photo Archive.app`. The app's Photos permission itself should persist under its stable bundle identity.

## Final response

Return:

- a short role-play discussion;
- the Photos folder and master-album names;
- exact master, HOLD, people, uncertainty, and evaluation counts;
- confirmation that source and prior versions remain unchanged;
- confirmation that no external upload occurred;
- links to the run README, master manifest, evaluation report, app receipt, and independent verification.

State clearly that this is an editor-ready field, not the final publication edit.
