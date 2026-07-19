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
5. Initialize `RUN/decisions.sqlite`. Record review, HOLD, replacement, rerouting,
   commit, and verification decisions as append-only events.

## Governing invariants

- Use the existing 124,484-item wide album as the default immutable source, or
  an explicit versioned source profile when the brief requires the whole visible
  still-photo library. Verify the profile identifier, observed count, and
  inventory fingerprint before work. Equal counts do not establish equal
  membership; any identifier or fingerprint drift requires a new freeze.
- Do not alter source albums, originals, metadata, faces, favorite status, dates, locations, or prior versions.
- Never write Photos SQLite. The permissioned app may only inspect locally or create folders/albums and add existing membership.
- Do not upload pixels, previews, OCR, faces, coordinates, or manifests.
- Use existing People names. Never identify unnamed faces or infer sensitive traits.
- Keep exact private locations and raw OCR out of reports.
- Treat only recognized clear states (`clear`, `clear-automated`, and identified-
  human `clear-human-reviewed`) as eligible. `needs-review`, `unavailable`,
  unknown states, hidden, missing, and HOLD assets are excluded before ranking
  and from every replacement path.
- Preserve an automated concern when a human clears a false positive: append the
  actor, generalized reason, prior signal, and decision without rewriting history.
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
  --summary RUN/reports/candidate-summary.json
```

2. Aim for 1.5-2.0 times the requested master size after metadata retrieval. Include named relationships, prior favorites/edits, person-free material context, and exploratory results. Album exclusions remove assets rather than merely suppressing their matching labels. Pass the structured candidate summary to final validation.
3. Generate a local inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access must remain false. Export 1280px previews into the private run workspace; raw OCR is never written.
5. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.
6. Run `verify_preview_exports.py`. Missing or corrupt required previews block
   phase completion and enter the re-export queue.

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
7. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately.
   Apply reviewed rejections with `photo-fieldwork round apply`; replacements
   must already be locally inspected, previewed, and explicitly clear. Key
   feedback to stable UUID plus view; a rejected image-view edge cannot re-enter
   through reranking or fallback.
8. Repeat until:
   - evaluation coverage and precision meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Validate and commit

1. Run `photo-fieldwork validate` with the latest evaluation report and candidate
   summary. Save the named-gate PASS report and read every waiver.
2. Generate test and production plans with `photo_archive_bridge.py snapshot-plans`.
3. Inspect the plans. Confirm the source count, target count, folder title, HOLD separation, and that operations are membership-only.
4. Run the ten-item write test through the app. Build a compact WAL-aware
   verification snapshot, then independently verify it with
   `verify_photos_commit.py`.
5. Run the production plan through the app. Rerun it once to confirm idempotence.
6. Independently verify every album, source boundary, HOLD overlap, and parent
   folder against the plan using the frozen read-only, immutable snapshot. Pass
   the exact master, HOLD, and config manifests to the verifier so their hashes
   are checked against the approved plan.
7. Run `photo-fieldwork run reconcile` after every durable phase. Finalize only
   after all artifact-backed phases pass; generate the completion report from
   state, hashes, receipts, evaluation results, privacy facts, and unresolved
   uncertainty. Structured JSON status and bound hashes authorize phases;
   filenames and prose Markdown reports never do.

Run the adversarial cases in [evals/evals.json](evals/evals.json) when changing
source, safety, evaluation, state, mutation, verification, or reporting behavior.
Follow [the eval hill-climb protocol](evals/README.md) and treat any failed
safety, mutation, verification, privacy, or publication expectation as blocking.

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
Safety clearance and exact catalog verification do not establish consent,
rights, factual caption provenance, or publication permission. Those require a
separate item-level human decision whose default is not cleared.
