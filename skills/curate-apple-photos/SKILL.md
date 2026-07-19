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
6. Read [release-gates.md](references/release-gates.md). Before any resume, plan, write, completion, or publication claim, classify the requested transition as `BLOCKED`, `READY_FOR_NEXT_PHASE`, or `EDITOR_FIELD_VERIFIED` and cite the evidence that closes or blocks it.

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
- Do not reconstruct state from filenames, remembered counts, or prose claims. Verify receipts and bind downstream artifacts to one unchanged source, config, master, HOLD set, and plan.
- Treat an editor-field decision and a publication decision as separate, destination-specific states.

Read [safety.md](references/safety.md) whenever a brief concerns private homes, minors, health, legal strategy, financial records, identity documents, or vulnerable collaborators.

## Decision contract

Use the active gate's exact identifier in structured output: `run_integrity`, `source_freshness`, `helper_capability`, `preview_integrity`, `assignment_feasibility`, `hypothesis_resolution`, `final_evaluation`, `replacement_audit`, `validation_binding`, `test_write`, `production_verification`, `completion`, or `publication_clearance`.

- Scope `BLOCKED` to the requested transition. Keep `editor_field_status` independent: a repairable field may remain `in-progress`, and a verified field remains `verified` when publication is blocked.
- For an unsupported optional view, use `hypothesis_resolution`, `UNSUPPORTED_PROJECT_VIEW`, and `NOT_RECOVERED_ANTI_CLAIM`; omit or unclassify the view and return `READY_FOR_NEXT_PHASE` when the remaining field is feasible.
- For a requested public set containing any uncleared item, use `publication_clearance`, `EDITOR_FIELD_NOT_PUBLICATION_PERMISSION`, `PUBLICATION_CLEARANCE_INCOMPLETE`, and `PRIVATE_FIELD_REDACTION_REQUIRED`; block the set without silently narrowing it.
- For verified completion, cite source, final evaluation, validation, sealed plan, test verification, production receipt, independent verification, and version registry. Use `EDITOR_FIELD_VERIFICATION_SUPPORTED` and `PUBLICATION_SEPARATE`; publication is `not-assessed` when no destination clearance was evaluated.

For the remaining gates, the canonical blocker pairs are `RECEIPT_HASH_MISMATCH` / `RUN_STATE_UNVERIFIED`, `SOURCE_COUNT_MISMATCH` / `FRESH_INVENTORY_REQUIRED`, `PREVIEW_MISSING` / `PREVIEW_CORRUPT` / `NOT_VISUALLY_REVIEWED`, `VIEW_QUOTA_SCARCITY` / `DIVERSITY_FLOOR_SCARCITY`, `VIEW_GATE_FAILED` / `HOLDOUT_CONTAMINATED`, and `UNEVALUATED_FINAL_ENTRANT` / `REJECTED_VIEW_REENTRY` / `HELD_CLUSTER_IN_MASTER`.

Use canonical codes exactly, without asset-specific suffixes. Put item details in evidence references and required actions. Every supported or inferential claim must cite the artifacts that justify it. When `not-assessed` follows only from the absence of an evaluated scope, report it as status rather than inventing an uncited factual claim.

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

Before validation, run `photo-fieldwork replacement-audit` against all evaluation rounds. Review every final entrant absent from earlier evaluation records. Freeze the resulting master, then inspect an untouched final holdout that excludes every tuning-feedback row. A targeted edge audit may supplement but cannot replace the final holdout and separate risk-stratified safety audit.

An unsupported optional project view need not block the rest of a defensible field. Omit it or return uncertain material to `Unclassified / Editor Field`, emit a gap report, and say `not recovered in this run` rather than claiming the evidence does not exist.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Run `photo-fieldwork validate`. Save a PASS report and confirm it names the same frozen master, source, config, HOLD set, and evaluation candidate.
2. Generate test and production plans with `photo_archive_bridge.py snapshot-plans`.
3. Inspect the plans. Confirm the source count and hash, target, folder title, master and HOLD hashes, evaluation identity, and membership-only operations.
4. Run the ten-item write test through the app. Independently verify it with `verify_photos_commit.py`, then rerun the test to prove idempotence.
5. Run the production plan through the app. Rerun it once to confirm idempotence.
6. Independently verify every album against the same sealed plan using read-only, immutable SQLite access. Require zero missing, unexpected, outside-source, and HOLD-overlap items.
7. Register the completed version manifest and verification receipt with `photo-fieldwork version-register`; run `version-verify` before declaring completion. Cite the complete evidence chain when using `EDITOR_FIELD_VERIFIED`.
8. Generate an uncleared `publication-clearance.csv` with `publication-scaffold`. Editor-field membership is not publication permission. Only rows with rights, consent, caption provenance, credit, accessibility, sensitive-context review, destination, and review date may pass `publication-validate`.
9. Build any public handoff as an allowlisted projection. Exclude archive UUIDs, People associations, albums, local paths, raw OCR, exact locations, HOLD membership, and private safety reasons.
10. Update `run-state.json` after each phase and write a completion report containing exact counts, identifiers, review-state counts, evaluation results, privacy facts, unresolved uncertainty, active gate, and disposition.

The helper invocation may require a Codex permission approval for `open -W`; request a reusable approval scoped to `/Applications/Jamie Photo Archive.app`. The app's Photos permission itself should persist under its stable bundle identity.

## Final response

Return:

- a short role-play discussion;
- the Photos folder and master-album names;
- exact master, HOLD, people, uncertainty, and evaluation counts;
- confirmation that source and prior versions remain unchanged;
- confirmation that no external upload occurred;
- links to the run README, master manifest, evaluation report, app receipt, and independent verification.

State the active disposition, gate, editor-field status, and publication status separately. State clearly that this is an editor-ready field, not the final publication edit. Do not turn missing publication evidence into a completion blocker when publication was not part of the evaluated request.
