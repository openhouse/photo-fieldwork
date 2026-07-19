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

- Select a source profile deliberately: `album://LOCAL_IDENTIFIER` or `visible-library-stills://v1`. Freeze both its current count and sorted-membership SHA-256 into the run; equal counts do not prove equal membership.
- Do not alter source albums, originals, metadata, faces, favorite status, dates, locations, or prior versions.
- Never write Photos SQLite. The permissioned app may only inspect locally or create folders/albums and add existing membership.
- Do not upload pixels, previews, OCR, faces, coordinates, or manifests.
- Use existing People names. Never identify unnamed faces or infer sensitive traits.
- Keep exact private locations and raw OCR out of reports.
- A potential sensitive item enters HOLD before ranking and cannot enter the master.
- `needs-review` is protected like HOLD until an explicit human clearance record changes it to `clear`.
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
   For a whole-library run, first build a fresh immutable inventory with `build_visible_library_inventory.py`; do not hardcode a historical library count.
3. Generate a local inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access must remain false. Export 1280px previews into the private run workspace; raw OCR is never written.
5. Verify every exported preview with `verify_preview_exports.py`, producing `preview-index.csv`. Missing, corrupt, or duplicate previews block contact-sheet preparation.
6. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.

## Select, look, evaluate, recurse

Read [evaluation-loop.md](references/evaluation-loop.md) before the first visual round.

1. Normalize project hypotheses into `candidate-view-evidence.csv`, then run exact assignment:

```bash
/Volumes/16TB_SSD/Sites/photo-fieldwork/bin/photo-fieldwork assign \
  --inventory RUN/manifests/ready-candidates.csv \
  --config RUN/config.json \
  --output RUN
```

2. Create a score-stratified sample from every view. For the first round, inspect at least 3 per view and at least 36 overall. Later rounds should normally inspect 60-100 fresh images across low, middle, and high scores, plus stable regression canaries.
   After round one, pass every prior ledger with `--exclude-feedback --novel-only`. Tag reused canaries separately: they may block release but cannot inflate fresh coverage, precision, or per-view sample size.
3. Build contact sheets from the verified preview index with `make_contact_sheets.py`. Use `view_image` to inspect every page. Open individual previews when context or safety is unclear.
   For a human editor handoff, generate the local-only `build_review_surface.py` interface. Keep it in the private run workspace and export decisions back to the feedback ledger.
4. Speak briefly as the requested peers. If Jamie cannot review, role-play Jamie using the supplied brief and voice references, while marking the judgment as delegated editorial inference rather than eyewitness fact.
5. Record `fit`, `reject`, or `uncertain`, one visible reason, a safety state, and an error category in the evaluation CSV.
6. Run `photo-fieldwork apply-feedback`, then `evaluate`. Read all rejections and a stratified uncertainty sample.
7. Feed the cumulative ledger back into `assign`. Change retrieval, evidence edges, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately.
8. Repeat until:
   - evaluation coverage and precision meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.
9. Freeze the candidate and config, then create a final holdout with `photo-fieldwork holdout`. Exclude every tuning-ledger UUID. Before opening judgments, run `audit_eval_split.py` against all tuning rows and canaries. Exact UUID, perceptual-cluster, duplicate-group, or burst-group overlap blocks the final evaluation.
10. Evaluate the final holdout once with `photo-fieldwork evaluate --split-audit SPLIT-AUDIT.json`. The audit's holdout-UUID digest must match the exact sample. Use `final-holdout-estimate` rows for aggregate metrics; per-view supplemental rows may satisfy view gates but cannot improve the aggregate estimate. Reopening selection or config after seeing holdout results creates a new candidate and requires a new holdout.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Run `photo-fieldwork validate`. Save a PASS report.
2. Generate test and production plans with `photo_archive_bridge.py snapshot-plans --config RUN/config.json --evaluation-report FINAL-EVALUATION.json`. Plan generation must fail unless the report is passing and its proposal, master, config, and evaluation-sample hashes match the exact frozen candidate.
3. Inspect the plans. Confirm the source count, target count, folder title, HOLD separation, and that operations are membership-only.
4. Mark completed phases with `photo_archive_bridge.py set-phase`, then seal the master, HOLD, uncertainty, feedback, config, evaluation, and both plans with `photo_archive_bridge.py seal`.
5. Run the ten-item write test through the app. Independently verify it with `verify_photos_commit.py`.
6. Run the production plan through the app. Rerun it once to confirm idempotence.
7. Independently verify every album against the plan using read-only, immutable SQLite access. The verifier must match the plan digest recorded by the app receipt.
8. Read `photo_archive_bridge.py status` and write a completion report containing exact counts, identifiers, evaluation results, privacy facts, and unresolved uncertainty.
9. Before sharing any report publicly, run `lint_public_report.py`. Treat a lint PASS as a data-minimization check, not publication permission.
10. For a public shortlist, record rights, consent, factual-claim support, public safety, and publication-for-specific-use as separate human decisions in the local review surface. Run `photo-fieldwork handoff` to create a salted-ID, allowlisted projection. Never publish the salt or the private input manifest.

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
