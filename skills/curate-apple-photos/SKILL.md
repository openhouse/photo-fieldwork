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
   - `config.json`, defining target, quotas, seed, uncertainty view, per-view evaluation modes, and thresholds.
4. Initialize a uniquely named run under `/Users/jburkart/Documents/Jamie-Photo-Archive-2026/` with `photo_archive_bridge.py init-run`. Never reuse or overwrite v00, v01, v02, or another run.

## Governing invariants

- Resolve the source through a versioned source manifest. Use an explicitly named album or `visible-library-stills://v1`; verify its observed count and fingerprint before work.
- Do not alter source albums, originals, metadata, faces, favorite status, dates, locations, or prior versions.
- Never write Photos SQLite. The permissioned app may only inspect locally or create folders/albums and add existing membership.
- Do not upload pixels, previews, OCR, faces, coordinates, or manifests.
- Use existing People names. Never identify unnamed faces or infer sensitive traits.
- Keep exact private locations and raw OCR out of reports.
- Use the `retrieval` inventory profile by default. Exact coordinates and source paths are allowed only in explicitly private `debug` artifacts.
- A potential sensitive item enters HOLD before ranking and cannot enter the master.
- Preserve `Unclassified / Editor Field`. Do not force every photograph into a project story.
- Label project-specific views `EDITOR HYPOTHESIS` unless visible evidence plus provenance supports stronger wording.
- Apple aesthetic scores may break ties only inside true duplicate or burst clusters.
- Dates support retrieval but are not narrative authority; imported film and scans may be misdated.

Read [safety.md](references/safety.md) whenever a brief concerns private homes, minors, health, legal strategy, financial records, identity documents, or vulnerable collaborators.

## Fail-closed decisions

Before resuming a run or advancing a release phase, compare the durable identities and receipts involved. Stop at the first unresolved mismatch.

- **Source drift:** if the observed count or membership digest differs from the accepted source manifest, preserve that manifest as historical evidence. Block retrieval, evaluation reuse, and Photos writes until a new source version is deliberately created and accepted.
- **Interrupted state:** if state and a receipt disagree, preserve every attempt and reconcile the receipt independently. Record the reconciliation as a new atomic event or legal transition; never infer completion from filenames or blindly rerun an ambiguous write.
- **Failed material view:** a passing aggregate cannot override a failed material view. Block plan generation, return unsupported assignments to unclassified or label the view `sparse-hypothesis`, and run a new full final-master audit after any change. Do not lower the threshold to manufacture a pass.
- **Evaluated artifact drift:** if the proposal, master, configuration, or source identity differs from what passed evaluation, the evaluation is stale. Freeze a new proposal identity and repeat the full final audit before plan generation, even when counts still match.
- **Unavailable pixels:** a missing or corrupt preview is unavailable evidence, not a visually inspected candidate. Put the asset in HOLD or `needs-review`; use bounded re-export plus independent decode verification before ranking it.
- **Protected states:** exclude HOLD and unresolved `needs-review` assets before ranking. Only an identified human reviewer may clear one `needs-review` item with an item-specific decision and generalized reason; the decision cannot weaken the detector or clear a class. HOLD remains held. Editor-field membership never confers publication consent or clearance.
- **Unsupported project view:** visible resemblance without provenance cannot become project proof. Preserve useful material as unclassified or an editor hypothesis and report that supporting evidence was not recovered, never that it did not exist.
- **Public report failure:** if lint or review finds private operational data, preserve the private source unchanged and unpublished. Create a separate redacted derivative, rerun lint, and require human publication review before release.

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
5. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.
6. Run `verify_preview_exports.py`. Unavailable or corrupt previews enter HOLD before selection.
7. Run `cluster_perceptual_duplicates.py` over the exported previews. Keep all candidate rows, but assign near-identical frames a shared `perceptual_cluster_id` before quota selection.
8. Treat `candidate_views` as immutable retrieval hypotheses. Every row entering selection must have an explicit `assigned_view`, `assignment_status`, `assignment_reason`, and `assignment_version` derived from the inspected evidence.

## Select, look, evaluate, recurse

Read [evaluation-loop.md](references/evaluation-loop.md) before the first visual round.

1. Run the project selector:

```bash
/Volumes/16TB_SSD/Sites/photo-fieldwork/bin/photo-fieldwork select \
  --inventory RUN/manifests/ready-candidates.csv \
  --config RUN/config.json \
  --output RUN
```

2. Create a score-stratified sample from every view. For the first round, inspect at least 3 per view and at least 36 overall. Inspect every item in a view smaller than the configured sample floor. Later rounds should normally inspect 60-100 fresh images across low, middle, and high scores, plus stable regression canaries.
3. Build contact sheets with `make_contact_sheets.py`. Preserve its page/row/column index. Use `view_image` to inspect every page. Open individual previews when context or safety is unclear.
4. Speak briefly as the requested peers. If Jamie cannot review, role-play Jamie using the supplied brief and voice references, while marking the judgment as delegated editorial inference rather than eyewitness fact.
5. Record `fit`, `reject`, or `uncertain`, one visible reason, a safety state, and an error category in a versioned feedback CSV. Validate and apply it with `photo-fieldwork feedback-validate` and `photo-fieldwork feedback-apply`.
6. Run `photo-fieldwork evaluate`. Overall precision cannot override a failed material view. Read all rejections and a stratified uncertainty sample.
7. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately.
8. Repeat until:
   - evaluation coverage and precision meet `config.json`;
   - every material view meets its own decisive precision, coverage, sample-size, and uncertainty gates;
   - weak project evidence has been explicitly relabeled `sparse-hypothesis` or returned to unclassified rather than quota-filled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Freeze the final master after the last selection change, run a full final audit, and save its PASS evaluation report. A targeted edge audit may supplement but cannot replace this final audit.
2. Run `photo-fieldwork validate`. Save a PASS report and confirm its `proposal_id` and `master_sha256` match the final evaluation.
3. Generate test and production plans with `photo_archive_bridge.py snapshot-plans --evaluation-report FINAL-EVALUATION.json`. Plan generation must fail if the evaluated hash differs from the master.
4. Inspect the plans. Confirm the source count, target count, folder title, proposal hash, HOLD separation, and that operations are membership-only.
5. Run the ten-item write test through the app. Independently verify it with `verify_photos_commit.py`.
6. Run the production plan through the app. Rerun it once to confirm idempotence.
7. Independently verify every album against the plan using read-only, immutable SQLite access.
8. Use `photo_archive_bridge.py status` to inspect atomic phase transitions. Write a structured completion report containing exact counts, identifiers, evaluation results, privacy facts, and unresolved uncertainty.
9. Before sharing any report publicly, run `lint_public_report.py`. A PASS does not replace human review.

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
