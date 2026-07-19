---
name: curate-apple-photos
description: Curate a large, versioned photo corpus from Jamie Burkart's local Apple Photos library from a pasted curatorial brief. Use when asked to create a 5k, 6k, 8k, or other editor-ready Photos album or folder of albums; role-play a named peer panel; use existing People associations; locally inspect pixels through the permissioned Jamie Photo Archive app; run recursive visual evaluation; quarantine sensitive material; preserve prior versions; and commit and independently verify non-destructive album membership.
---

# Curate Apple Photos

Turn the user's brief into a locally inspected, recursively evaluated, versioned Apple Photos editor field. Carry the work through Photos commit and independent verification unless the user pauses it or a genuine permission/data blocker remains.

## Start

1. Keep requested role-play speakers visible in commentary and final discussion. Their judgments guide interpretation; scripts and receipts establish operational facts.
2. Read [machine-profile.md](references/machine-profile.md), configure the
   private machine profile outside git, freeze the source count and digest with
   `freeze_source_profile.py`, then run:

```bash
python3 scripts/photo_archive_bridge.py doctor
```

3. Read [brief-contract.md](references/brief-contract.md). Convert the pasted brief into:
   - `brief.md`, preserving the user's words;
   - `retrieval.json`, defining views, terms, people, albums, places, and supporting date ranges;
   - `config.json`, defining target, quotas, seed, uncertainty view, and evaluation thresholds.
4. Initialize a uniquely named run under the workspace root declared in the
   private machine profile with `photo_archive_bridge.py init-run`. Never reuse
   or overwrite v00, v01, v02, or another run.

## Governing invariants

- Use the frozen source declared by the private machine profile. Both an album
  source and `visible-library-stills://v1` are supported. Discover and freeze
  count plus identifier digest before work; never encode a personal count in
  reusable code.
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
  --db /private/path/from-machine-profile/inventory.sqlite \
  --retrieval RUN/retrieval.json \
  --target TARGET \
  --output RUN/manifests/candidate-pool.csv
```

2. Aim for 1.5-2.0 times the requested master size after metadata retrieval. Include named relationships, prior favorites/edits, person-free material context, and exploratory results.
3. Generate a local inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access must remain false. Export 1280px previews into the private run workspace; raw OCR is never written.
5. Run `verify_preview_exports.py`. Corrupt, missing, over-permissioned, or
   metadata-bearing previews block progress.
6. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.

## Select, look, evaluate, recurse

Read [evaluation-loop.md](references/evaluation-loop.md) before the first visual round.

1. Run the project selector:

```bash
photo-fieldwork select \
  --inventory RUN/manifests/ready-candidates.csv \
  --config RUN/config.json \
  --output RUN
```

2. Set `evaluation_sample_per_view` before selection, then create the
   deterministic score-stratified sample from every view. For the first round,
   inspect at least 3 per view and at least 36 overall. Later rounds should
   normally inspect 60-100 images across low, middle, and high scores.
3. Build contact sheets with `make_contact_sheets.py`, or build the private
   dependency-free workbench with `photo-fieldwork build-review` and serve it
   only through `photo-fieldwork serve-review`. Use `view_image` to inspect
   every contact-sheet page. Open individual previews when context or safety is unclear.
4. Speak briefly as the requested peers. If Jamie cannot review, role-play Jamie using the supplied brief and voice references, while marking the judgment as delegated editorial inference rather than eyewitness fact.
5. Record `fit`, `reject`, or `uncertain`, one visible reason, a safety state, and an error category in the evaluation CSV.
6. Run `photo-fieldwork evaluate`. Read all rejections and a stratified uncertainty sample.
7. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately.
8. Repeat until:
   - evaluation coverage and precision meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

9. Before holdout results support release, run `photo-fieldwork audit-holdout`
   across tuning, canary, and holdout manifests. Require zero canonical UUID,
   perceptual-cluster, duplicate-group, and burst-group leakage. Keep
   identifier-level remediation output private.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Run `photo-fieldwork validate`. Save a PASS report.
2. Generate test and production plans with `photo_archive_bridge.py
   snapshot-plans`, passing the final feedback, evaluation report, HOLD
   manifest, and validation report. The command routes through the core planner
   and refuses any release bundle that differs from the exact source,
   configuration, master, deterministic sample, feedback, or HOLD manifest.
3. Inspect the plans. Confirm the source count, target count, folder title, HOLD separation, and that operations are membership-only.
4. Run the ten-item write test through the app. Independently verify it with `verify_photos_commit.py`.
5. Run the production plan through the app. Rerun it once, then compare both
   receipts against the same plan and configured helper with
   `compare_receipts.py --plan ... --app-binary ... --bundle-id ... --photos-db
   ...` before claiming receipt consistency. The comparator runs independent
   read-only catalog verification for both receipts before comparing them.
6. Independently verify every folder and album, including collection types and
   parent-child relationships, against the plan. The verifier must create
   a WAL-aware consistent snapshot from a live read-only connection before it
   opens the frozen snapshot as immutable and query-only.
   Use `photo_archive_bridge.py verify-phase`; ordinary `advance` calls cannot
   complete verification phases from a supplied PASS document.
7. Update `run-state.json` after each phase and write a completion report containing exact counts, identifiers, evaluation results, privacy facts, and unresolved uncertainty.

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

If the user explicitly requests a public-use package, treat it as a separate
human-governed release. Run `photo-fieldwork public-handoff` only from a
publication-review manifest with destination-specific positive rights, consent,
claim, safety, and editorial states. Keep the salt and blocked-row report
private; inspect both outputs before publication.

## Maintain the contract

When changing this skill, run the synthetic regression bank in
[`evals/evals.json`](evals/evals.json) and follow its
[`README.md`](evals/README.md). Hill climb against observed false passes: make
the oracle more discriminating, add the smallest adversarial case that captures
the failure, and rerun every critical safety canary. Never improve a benchmark
by weakening source, human-review, privacy, publication, or verification gates.

Also run the cross-boundary bank in
[`evals/composite-evals.json`](evals/composite-evals.json) through
`make composite-evals`. Its contract must retain both positive controls and
fail-closed cases; a refusal-only or permissive-only bank is invalid.
