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

3. Read [brief-contract.md](references/brief-contract.md). Convert the pasted brief into:
   - `brief.md`, preserving the user's words;
   - `retrieval.json`, defining views, terms, people, albums, places, and supporting date ranges;
   - `config.json`, defining target, quotas, seed, uncertainty view, and evaluation thresholds.
4. Initialize a uniquely named run under `/Users/jburkart/Documents/Jamie-Photo-Archive-2026/` with `photo_archive_bridge.py init-run`. Never reuse or overwrite v00, v01, v02, or another run.

## Governing invariants

- Use either the verified wide album or `visible-library-stills://v1` as an explicit immutable source. Whole-library work must build a fresh read-only inventory quality report. Freeze the chosen source identifier, current count, and sorted-UUID membership SHA-256 before work; a matching count alone cannot prove source identity.
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

2. Aim for 1.5-2.0 times the requested master size after metadata retrieval. Include named relationships, prior favorites/edits, person-free material context, and exploratory results.
3. Generate a local inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access must remain false. Export 1280px previews into the private run workspace; raw OCR is never written.
5. Run `verify_preview_exports.py` after every shard. Any missing, duplicate, or undecodable required preview blocks contact-sheet review and selection.
6. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.

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
3. Build contact sheets with `make_contact_sheets.py`. Use `view_image` to inspect every page. Open individual previews when context or safety is unclear.
4. Speak briefly as the requested peers. If Jamie cannot review, role-play Jamie using the supplied brief and voice references, while marking the judgment as delegated editorial inference rather than eyewitness fact.
5. Record `fit`, `reject`, or `uncertain`, one visible reason, a safety state, and an error category in the evaluation CSV.
6. Run `photo-fieldwork evaluate`. Treat the overall metric as diagnostic: every material view must independently meet coverage, decisive-sample, precision, uncertainty, and safety gates. A sparse hypothesis requires an explicit written waiver that remains visible in the report and plan.
7. For every recursive round after the first, pass the prior feedback to `photo-fieldwork sample --exclude-feedback PRIOR.csv --novel-only`. The command must report zero prior UUID overlap; if a view lacks enough fresh candidates, expand retrieval instead of recycling evidence.
8. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately. The evaluation sample hash must remain unchanged between sampling and evaluation.
9. Repeat until:
   - evaluation coverage, decisive precision, and maximum uncertainty meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

Selection must meet each configured view quota exactly. If overlap makes the brief infeasible, preserve the requested quotas and report capacities and deficits; never silently rebalance the field.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Run `photo-fieldwork validate`. Save a PASS report.
2. Generate test and production plans with `photo_archive_bridge.py snapshot-plans --evaluation-report ... --source-membership-sha256 ...`, using the digest from the frozen inventory quality report. The report must pass and match the exact master and evaluation-sample hashes. Keep the release class `editor-field`; publication clearance remains false.
3. Inspect the plans. Confirm the source count, target count, folder title, HOLD separation, and that operations are membership-only.
4. Run the ten-item write test through the app. Independently verify it with `verify_photos_commit.py`.
5. Run the production plan through the app. Rerun it once to confirm idempotence.
6. Capture a compact verification database with `snapshot_photos_verification.py`. It reads the live database in a query-only transaction so committed WAL state is visible, never checkpoints Photos, and writes only a separate snapshot.
7. Independently verify every album against that snapshot using read-only, immutable SQLite access.
8. Update `run-state.json` after each phase. Use `photo_archive_bridge.py status --workspace RUN` to report the next incomplete phase. Write a completion report containing exact counts, identifiers, evaluation results, privacy facts, and unresolved uncertainty.

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

## Maintain the skill

Run `make evals` before and after changing the workflow. Use the adversarial prompt bank in `evals/evals.json` against both the candidate and the previous skill snapshot. Add every newly discovered regression as a permanent case; do not remove a difficult eval merely to improve the score.
