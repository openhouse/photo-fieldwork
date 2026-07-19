---
name: curate-apple-photos
description: Curate or resume a large, versioned photo corpus from Jamie Burkart's local Apple Photos library from a pasted curatorial brief. Use whenever asked to create a 4k, 5k, 6k, 8k, whole-library, or other editor-ready Photos field; role-play a named peer panel; use existing People associations; freeze source membership; locally inspect fresh pixels through the permissioned Jamie Photo Archive app; run recursive per-view evaluation; review sensitive material with provenance-aware safety states; preserve prior versions and run events; and commit, rerun, and independently verify non-destructive album membership.
---

# Curate Apple Photos

Turn the user's brief into a locally inspected, recursively evaluated, versioned Apple Photos editor field. Carry the work through Photos commit and independent verification unless the user pauses it or a genuine permission/data blocker remains.

## Start

1. Keep requested role-play speakers visible in commentary and final discussion. Their judgments guide interpretation; scripts and receipts establish operational facts.
2. Read [machine-profile.md](references/machine-profile.md), then run:

```bash
python3 scripts/photo_archive_bridge.py doctor
```

3. Choose and freeze a source profile before retrieval:
   - use the stable 124,484-item wide album for normal portfolio work;
   - use `visible-library-stills://v1` only when the brief explicitly requires the whole visible still library;
   - write `source-snapshot.json` with count and sorted-membership SHA-256 using `inventory_source_snapshot.py` or `build_visible_library_inventory.py --snapshot-output`.
4. Read [brief-contract.md](references/brief-contract.md). Convert the pasted brief into:
   - `brief.md`, preserving the user's words;
   - `retrieval.json`, defining views, terms, people, albums, places, and supporting date ranges;
   - `config.json`, defining target, quotas, seed, uncertainty view, and evaluation thresholds.
5. Initialize a uniquely named run under `/Users/jburkart/Documents/Jamie-Photo-Archive-2026/` with `photo_archive_bridge.py init-run --source-snapshot SOURCE-SNAPSHOT`. Never reuse or overwrite another run. The command creates an append-only `events.jsonl`; derive status from it with `photo-fieldwork run-status`.

## Governing invariants

- Use the existing 124,484-item wide album as the default source profile. Treat a source query as dynamic and its per-run count plus membership digest as immutable.
- Do not alter source albums, originals, metadata, faces, favorite status, dates, locations, or prior versions.
- Never write Photos SQLite. The permissioned app may only inspect locally or create folders/albums and add existing membership.
- Do not upload pixels, previews, OCR, faces, coordinates, or manifests.
- Use existing People names. Never identify unnamed faces or infer sensitive traits.
- Keep exact private locations and raw OCR out of reports.
- A potential sensitive item enters HOLD before ranking and cannot enter the master.
- Keep automated, unavailable, human-added, confirmed, and cleared safety states distinct. A cleared false positive requires an explicit human review record.
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
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access must remain false. Export 1280px previews into the private run workspace; raw OCR is never written. A successful helper run archives an immutable attempt receipt and records its phase automatically when the run ledger is present.
5. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.
6. Before a corrective round, use `inspection_delta.py` to request candidates not already inspected in the run. Combine compatible ledgers with `combine_inspections.py`; conflicting evidence must stop the merge.
7. Record phase completion with `photo-fieldwork run-record`, including the output path, digest, counts, and attempt ID in a details JSON file.

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
6. Run `photo-fieldwork evaluate`. Read all rejections and a stratified uncertainty sample.
   Read release thresholds from the exact run's `config.json`. A documented
   production default is guidance, not the active gate. If the run config is
   unavailable, name the visible failure but do not invent a numeric threshold.
7. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately.
8. Repeat until:
   - evaluation coverage and precision meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

Before the final holdout is judged, run `photo-fieldwork split-audit` against
all tuning rounds, the holdout, and stable canaries. The split must be disjoint
across UUID, perceptual-cluster, duplicate-group, and burst-group identity.
Keep private identifiers in the run workspace; the ordinary report contains
only counts and digests.

The CLI enforces overall precision, coverage, per-view precision, minimum decisive samples per view, and maximum uncertainty when those values are configured. A documented threshold that is not represented in `config.json` is not a release gate.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Freeze the final master after the last selection change. Save the passing fresh final evaluation and a PASS `photo-fieldwork validate` report.
2. Run `photo-fieldwork release-seal`. The seal binds the exact source snapshot, master rows and assignments, HOLD rows, config, evaluation, and validation. Any later change makes the seal stale and blocks planning.
3. Generate test and production plans with `photo_archive_bridge.py snapshot-plans`, passing the config, source snapshot, evaluation, validation, and release seal. The plans must carry the seal fingerprint.
4. Inspect the plans. Confirm the source identity, target count, folder title, HOLD separation, release seal, and membership-only mutation boundary.
5. Run the ten-item write test through the app. Independently verify its archived attempt receipt with `verify_photos_commit.py --attempt-receipt`, saving both Markdown and JSON verification reports.
6. Run the production plan. Verify that attempt independently, then rerun the unchanged plan once and verify the second archived attempt independently.
7. Run `photo-fieldwork idempotence-audit` over both distinct attempt receipts and both verification JSON files. Different filenames or timestamps do not count as distinct executions; helper-attested nonces, the plan identity, app bundle and binary identity, stable bindings, and per-attempt verification must agree.
8. Record each completed phase in `events.jsonl` with `photo-fieldwork run-record`. Do not edit `run-state.json`; it is derived. Write a completion report containing exact counts, identifiers, evaluation results, privacy facts, and unresolved uncertainty.
9. If photographs are being considered for public use, run `photo-fieldwork publication-scaffold`. It starts every master UUID at `publication_cleared=false`. Validate destination-specific rights, consent, collaborator and artwork review, caption provenance, credit, crop, alt text, sensitive context, and review date separately. Editor-field completion never clears publication.

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
