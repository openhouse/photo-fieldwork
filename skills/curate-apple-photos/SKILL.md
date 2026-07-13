---
name: curate-apple-photos
description: Curate a large, versioned photo corpus from Jamie Burkart's local Apple Photos library from a pasted curatorial brief. Use when asked to create a 5k, 6k, 8k, or other editor-ready Photos album or folder of albums; role-play a named peer panel; use existing People associations; locally inspect pixels through the permissioned Jamie Photo Archive app; run recursive visual evaluation; quarantine sensitive material; preserve prior versions; and commit and independently verify non-destructive album membership.
---

# Curate Apple Photos

Turn the user's brief into a locally inspected, recursively evaluated, versioned Apple Photos editor field. Carry the work through Photos commit and independent verification unless the user pauses it or a genuine permission/data blocker remains.

## Start

1. Keep requested role-play speakers visible in commentary and final discussion. Their judgments guide interpretation; scripts and receipts establish operational facts.
2. Read [machine-profile.md](references/machine-profile.md). Declare the exact active source in `source-profile.json`, then run:

```bash
python3 scripts/photo_archive_bridge.py doctor --source-profile RUN/source-profile.json
```

3. Read [brief-contract.md](references/brief-contract.md). Convert the pasted brief into:
   - `brief.md`, preserving the user's words;
   - `retrieval.json`, defining views, terms, people, albums, places, and supporting date ranges;
   - `config.json`, defining target, quotas, seed, uncertainty view, and evaluation thresholds.
4. Initialize a uniquely named run under `/Users/jburkart/Documents/Jamie-Photo-Archive-2026/` with `photo_archive_bridge.py init-run --source-profile SOURCE.json`. Never reuse or overwrite an earlier run.

## Governing invariants

- Use the source profile named by the brief. The 124,484-item wide album is the default broad source; `visible-library-stills://v1` is the whole visible-library source. Never let `doctor`, inventory, run state, inspection, or verification describe different sources.
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
  --output RUN/manifests/candidate-pool.csv \
  --report RUN/reports/retrieval-allocation.json
```

2. Aim for 1.5-2.0 times the requested master size after metadata retrieval. Reserve each view before truncating the global union. Treat prior editor albums as retrieval indexes, never factual provenance, and record any outside-prior floor.
3. Generate a local inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access must remain false. Export 1280px previews into the private run workspace; raw OCR is never written.
5. Verify every exported preview with `verify_preview_exports.py`. Merge all rounds through `photo-fieldwork inspection-ledger`; reuse only inspections whose source fingerprint, helper version, target edge, classifier policy, and safety ruleset still match.
6. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`. Keep source and inspected face counts separate and derive a conservative known count.
7. Apply a private, declarative relational safety policy with `photo-fieldwork safety` before selection. Rules may propagate HOLD or needs-review through configured album families, People associations, event clusters, labels, or exact asset decisions.

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
6. Run `photo-fieldwork evaluate`. Overall PASS requires every material view to meet its gate unless a waiver is explicit. Read all rejections and a stratified uncertainty sample.
7. Apply judgments with `photo-fieldwork apply-feedback`. Review every cascading replacement and reassignment before another validation. Keep an append-only decision ledger.
8. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately.
9. Repeat until:
   - evaluation coverage and precision meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Run `photo-fieldwork validate`. Save a PASS report.
2. Run `photo-fieldwork duplicate-audit`. Resolve every cross-UUID duplicate review item.
3. Generate test and production plans with `photo_archive_bridge.py snapshot-plans --source-profile SOURCE.json`. Generated plans are membership-only, linted, and digest-sealed.
4. Run `photo-fieldwork lint-plan` with the source profile and inspection ledger. Confirm exact source, target, quotas, inspection coverage, folder routing, HOLD separation, and plan digest.
5. Run the ten-item write test through the app. Independently verify it with `verify_photos_commit.py`.
6. Run the production plan through the app. Rerun it once. The bridge preserves the prior receipt and compares folder IDs, album IDs, and counts.
7. Independently verify every album against the plan using read-only, immutable SQLite access.
8. Update `run-state.json` after each phase. Generate the completion report with `photo-fieldwork report`; do not hand-transcribe artifact-backed numbers.

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
