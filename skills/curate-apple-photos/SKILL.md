---
name: curate-apple-photos
description: Curate or safely resume a large, versioned photo corpus from Jamie Burkart's local Apple Photos library from a pasted curatorial brief. Use when asked to create a 5k, 6k, 8k, or other editor-ready Photos album or folder of albums; role-play a named peer panel; use existing People associations; locally inspect pixels through the permissioned Jamie Photo Archive app; run recursive visual evaluation; quarantine sensitive material; preserve prior versions; produce a cleared public projection; and commit and independently verify non-destructive album membership.
---

# Curate Apple Photos

Turn the user's brief into a locally inspected, recursively evaluated, versioned Apple Photos editor field. Carry the work through Photos commit and independent verification unless the user pauses it or a genuine permission/data blocker remains.

## Start

1. Keep requested role-play speakers visible in commentary and final discussion. Their judgments guide interpretation; scripts and receipts establish operational facts.
2. Read [machine-profile.md](references/machine-profile.md). Verify the private
   profile, then run the live, read-only helper probe before expensive work:

```bash
python3 scripts/photo_archive_bridge.py doctor --profile PRIVATE_PROFILE --live
```

Stop if the helper process cannot see authorization, resolve the intended
source, match its frozen count, or fetch one local sample with network disabled.

3. Read [brief-contract.md](references/brief-contract.md). Convert the pasted brief into:
   - `brief.md`, preserving the user's words;
   - `retrieval.json`, defining views, terms, people, albums, places, and supporting date ranges;
   - `config.json`, defining target, quotas, seed, uncertainty view, and evaluation thresholds.
4. Route explicitly:
   - For a fresh version, create a new private inventory and initialize a
     uniquely named, mode-`0700` run with `photo_archive_bridge.py init-run`.
     Never reuse or overwrite an earlier run.
   - For an interrupted version, do not initialize again. Read
     `run-state.json`, verify recorded artifact hashes and any `run-lock.json`,
     inspect existing plans and receipts, and resume only the next incomplete phase.
5. Phase changes must be recorded through `photo-fieldwork run transition`; do
   not hand-edit `run-state.json`.

When resuming inspection, validate every existing JSONL row and its membership
before appending only missing identifiers. Final receipt counters are cumulative:
initialize pixel, preview, HOLD, and unavailable counts from valid prior rows,
then add new rows. A receipt that counts only the resumed batch is invalid.
Catalog writing remains blocked until resumed inspection is complete, evaluation
and the final holdout pass, the master is frozen, and validation passes.

## Governing invariants

- Choose source scope from the brief. The existing wide album is a useful
  default; explicit whole-library work uses `visible-library-stills://v1`.
  Every fresh version receives a new versioned inventory. Derive and freeze the
  observed count and sorted-membership SHA-256 rather than relying on a compiled
  or previous count. Source-count drift blocks retrieval until a new inventory
  and source freeze are recorded; never silently relabel a stale freeze.
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
- Generated fieldwork, private review, and write-audit albums may not become
  source evidence. Explicitly exclude all three lineages during retrieval, not
  only the album that triggered the concern. Report final novelty outside prior
  corpora.
- Keep source eligibility, visible evidence, sensitivity, rights, consent,
  claim support, and publication readiness as separate states.
- Keep the release dependency strict: verified source, complete inspection,
  passing evaluation, final freeze and lock, untouched final holdout, passing
  validation, sealed plans, ten-item test, production, independent verification.
  A later gate never compensates for a missing earlier gate.
- Any selected UUID, assignment, quota, or HOLD change after final freeze
  invalidates the lock, final evaluation, and catalog plans. Refreeze, draw and
  inspect a fresh untouched final holdout, validate, and only then create new plans.

Read [safety.md](references/safety.md) whenever a brief concerns private homes, minors, health, legal strategy, financial records, identity documents, or vulnerable collaborators.

## Build the candidate field

1. Query the shared read-only inventory. For large whole-library scans, use the
   bounded streaming retriever:

```bash
python3 scripts/retrieve_candidates.py \
  --db PROFILE_INVENTORY.sqlite \
  --retrieval RUN/retrieval.json \
  --target TARGET \
  --output RUN/manifests/candidate-pool.csv

python3 scripts/retrieve_candidates_stream.py \
  --db WHOLE_LIBRARY.sqlite \
  --retrieval RUN/retrieval.json \
  --target TARGET \
  --output RUN/manifests/candidate-pool.csv
```

2. Aim for 1.5-2.0 times the requested master size after metadata retrieval. Include named relationships, prior favorites/edits, person-free material context, and exploratory results.
3. Generate a local inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. Network access must remain false. Export 1280px previews into the private run workspace; raw OCR is never written.
5. Run `verify_preview_exports.py`. A filename or non-empty directory is not
   proof that every preview decodes. Unavailable or corrupt rows remain
   protected and require freshly inspected replacements.
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

2. Create a score-stratified sample from every view. For the first round, inspect at least 3 per view and at least 36 overall. Later rounds should normally inspect 60-100 images across low, middle, and high scores.
3. Build contact sheets with `make_contact_sheets.py`. Use `view_image` to inspect every page. Open individual previews when context or safety is unclear.
   For larger rounds, build the offline workbench with
   `photo-fieldwork review-build`; it must remain private and make no external
   requests. The workbench copies only sampled previews into its private served
   root. Its export must preserve `sample_role`, `estimate_included`,
   `sample_seed`, `population_count`, `full_master_count`, and
   `view_population_count`; otherwise a final evaluation is blocked. Before
   repairing feedback by UUID, verify the frozen master and `run-lock.json`. If
   that identity cannot be verified, discard the damaged export and draw a fresh
   holdout rather than reconstructing one.
4. Speak briefly as the requested peers. If Jamie cannot review, role-play Jamie using the supplied brief and voice references, while marking the judgment as delegated editorial inference rather than eyewitness fact.
5. Record `fit`, `reject`, or `uncertain`, one visible reason, a safety state, and an error category in the evaluation CSV.
6. Run `photo-fieldwork evaluate`. Read all rejections and a stratified uncertainty sample.
7. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately and record each effective-config decision.
   Recheck event-cluster caps during every diversity-floor swap. Prefer a
   compatible incoming/donor pair deterministically; if caps and floors are
   jointly infeasible, fail before emitting a proposed master.
8. Repeat until:
   - review completion, view sampling coverage, and decisive fit rate meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

Working rounds discover and repair errors. They are not an independent estimate
of the field they helped create.

## Validate and commit

1. Freeze the surviving master with `photo-fieldwork freeze-final`. This writes
   `effective-final-config.json`, replay validation, and `run-lock.json`. Preserve
   intent quotas and mark unsupported or deliberately empty views honestly.
   Omit unsupported production albums and preserve
   `unsupported-view-gaps.json`. State that qualifying evidence was not
   recovered in this run, not that no relevant photograph exists. Any quota
   reallocation must be an explicit hash-linked config decision replayed before
   the freeze.
2. Draw a new `final-holdout` sample after the freeze. Exclude every prior
   feedback row. For a 4,000-photo field, begin with at least 200 uniform
   estimation rows. Supplemental rows may bring each material view to at least
   15, but they must not enter the aggregate Wilson interval.
3. Inspect every final-holdout preview. Report review completion, view sampling
   coverage, decisive fit rate, field audit rate, and the 95% Wilson interval.
   Run a separate risk-stratified safety audit.
4. Run `photo-fieldwork validate` with the effective final config. Save a PASS report.
5. Generate test and production plans with `photo_archive_bridge.py snapshot-plans`.
6. Inspect the plans. Confirm the source count, target count, folder title, HOLD separation, and that operations are membership-only.
7. Run the ten-item write test through the PhotoKit helper. Independently verify it with `verify_photos_commit.py`.
8. If PhotoKit is unavailable after live preflight, stop and record the failure.
   Use `applescript_writer.py` only as an explicit adapter change against the
   same frozen plan. Render first, inspect the script hash and plan, then execute.
9. Run the production plan. Rerun it once to confirm idempotence.
10. Independently verify every album against the plan using read-only, immutable SQLite access.
11. Record each phase transition automatically and write a completion report containing exact counts, identifiers, evaluation results, privacy facts, backend identity, and unresolved uncertainty.

Helper or AppleScript invocation may require a Codex permission approval. Scope
approval to the reviewed app or exact writer command. Never rebuild, clone,
rename, or re-sign the helper as an unrecorded attempt to work around TCC.

## Public projection

An editor field is private research, not a publication manifest. Never hand the
private master directly to a public site. Run `photo-fieldwork handoff` only
after asset-specific rights, consent, claim, and publication states are cleared
for the named use.

The handoff is an allowlisted projection with salted opaque public IDs. Exclude
archive UUIDs, People associations, paths, exact or named private places, OCR,
HOLD membership, safety reasons, raw evidence, and every field not in the public
schema. Unknown clearance excludes a row; it does not become a warning attached
to a public row.

## Final response

Return:

- a short role-play discussion;
- the Photos folder and master-album names;
- exact master, HOLD, people, uncertainty, and evaluation counts;
- confirmation that source and prior versions remain unchanged;
- confirmation that no external upload occurred;
- the writer backend and final Wilson interval;
- links to the run README, master manifest, evaluation report, app receipt, and independent verification.

State clearly that this is an editor-ready field, not the final publication edit.
