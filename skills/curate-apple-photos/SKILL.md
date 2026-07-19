---
name: curate-apple-photos
description: Curate a large, versioned photo corpus from Jamie Burkart's local Apple Photos library from a pasted curatorial brief. Use when asked to create a 5k, 6k, 8k, or other editor-ready Photos album or folder of albums; role-play a named peer panel; use existing People associations; locally inspect pixels through the permissioned Jamie Photo Archive app; run recursive visual evaluation; quarantine sensitive material; preserve prior versions; and commit and independently verify non-destructive album membership.
---

# Curate Apple Photos

Turn the user's brief into a locally inspected, recursively evaluated, versioned Apple Photos editor field. Carry the work through Photos commit and independent verification unless the user pauses it or a genuine permission/data blocker remains.

## Start

1. Keep requested role-play speakers visible in commentary and final discussion. Their judgments guide interpretation; scripts and receipts establish operational facts.
2. Read [machine-profile.md](references/machine-profile.md). Declare the requested source
   with `source.json`, then run:

```bash
python3 scripts/photo_archive_bridge.py doctor --source-manifest RUN/source.json
```

3. Read [brief-contract.md](references/brief-contract.md). Convert the pasted brief into:
   - `brief.md`, preserving the user's words;
   - `retrieval.json`, defining views, terms, people, albums, places, and supporting date ranges;
   - `config.json`, defining target, quotas, seed, uncertainty view, and evaluation thresholds.
4. Initialize a uniquely named run under `/Users/jburkart/Documents/Jamie-Photo-Archive-2026/` with `photo_archive_bridge.py init-run`. Never reuse or overwrite another run. Use `photo-fieldwork state resume --workspace RUN` after any interruption.
5. For a new workflow release, read [evals/README.md](evals/README.md) and run its
   adversarial cases without live Photos mutation. Preserve the previous accepted skill as
   the baseline and retain failed runs.

## Governing invariants

- Treat the brief as authoritative about scope. A whole-library request uses the versioned
  `visible-library-stills://v1` source and inventory; a named-album request uses an album
  source. Never silently substitute the existing 124,484-item wide album.
- Do not alter source albums, originals, metadata, faces, favorite status, dates, locations, or prior versions.
- Never write Photos SQLite. The permissioned app may only inspect locally or create folders/albums and add existing membership.
- Do not upload pixels, previews, OCR, faces, coordinates, or manifests.
- Use existing People names. Never identify unnamed faces or infer sensitive traits.
- Keep exact private locations and raw OCR out of reports.
- Use `minimal` or `retrieval` inventory profiles by default. Exact coordinates and source
  paths are allowed only in explicitly private debug artifacts.
- A potential sensitive item enters HOLD before ranking and cannot enter the master.
- Automation, an AI assistant, and role-play cannot clear a protected safety state. An
  identified authorized human must record the bounded reason and decision while preserving
  the original flag.
- A missing, corrupt, or undecodable preview is `unavailable` and cannot enter the master.
- Preserve `Unclassified / Editor Field`. Do not force every photograph into a project story.
- Label project-specific views `EDITOR HYPOTHESIS` unless visible evidence plus provenance supports stronger wording.
- Apple aesthetic scores may break ties only inside true duplicate or burst clusters.
- Dates support retrieval but are not narrative authority; imported film and scans may be misdated.
- Editor-field membership is not publication permission. Keep rights or license, consent,
  provenance, factual-claim support, contextual risk, and publication approval as separate
  human-reviewed states that default closed when unresolved.

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
   Keep retrieval channels in the manifest. Exclude generated Photo Fieldwork albums from
   ordinary album search, and treat prior corpora as context rather than the source universe.
   `outside_prior_discovery_fraction` is a bounded discovery budget, not a forced composition floor.
3. Generate a local inspection plan with `photo_archive_bridge.py inspection-plan`.
4. Run the stable permissioned helper with `photo_archive_bridge.py run-plan`. The bridge
   must pass the capability probe before execution. Network access must remain false. Export
   1280px previews into the private run workspace; raw OCR is never written. The bridge
   independently decodes all expected previews and fails closed on missing or corrupt files.
5. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.
6. Run `cluster_perceptual_duplicates.py` over the verified previews. Keep every candidate
   row, but assign near-identical frames a shared `perceptual_cluster_id` before selection.
7. Treat `candidate_views` as immutable retrieval hypotheses. After looking, record an
   explicit `assigned_view`, `assignment_status`, and `assignment_reason` for every row that
   may enter selection. The selector must fail rather than derive an assignment from retrieval.

## Select, look, evaluate, recurse

Read [evaluation-loop.md](references/evaluation-loop.md) before the first visual round.

1. Run the project selector:

```bash
/Volumes/16TB_SSD/Sites/photo-fieldwork/bin/photo-fieldwork select \
  --inventory RUN/manifests/ready-candidates.csv \
  --config RUN/config.json \
  --output RUN
```

2. Create a score-stratified sample from every view. For the first round, inspect at least 3 per view and at least 36 overall. Later rounds should normally inspect 60-100 images across low, middle, and high scores. Use `--view` and a new `--round-id` for targeted follow-up on failed views.
3. Build contact sheets with `make_contact_sheets.py`. Preserve its page/row/column index.
   Use `view_image` to inspect every page. Open individual previews when context or safety is unclear.
4. Speak briefly as the requested peers. If Jamie cannot review, role-play Jamie using the supplied brief and voice references, while marking the judgment as delegated editorial inference rather than eyewitness fact.
5. Record `fit`, `reject`, or `uncertain`, one visible reason, a safety state, and an error
   category in a separate versioned feedback CSV. Validate it with `feedback-validate` and
   apply it with `feedback-apply`.
6. Run `photo-fieldwork evaluate`. Read all rejections and a stratified uncertainty sample.
7. Read global and per-view gates. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately.
   Preserve known failures as regression canaries, but do not count reused canaries or tuning
   examples as fresh evidence of quality.
8. Repeat until:
   - evaluation coverage and precision meet `config.json`;
   - every view has been visually sampled;
   - known safety regressions are absent;
   - generic social context is not standing in for professional evidence;
   - people and collective context remain meaningfully represented;
   - uncertainty is explicit;
   - the exact requested target is met with unique still-photo IDs.

Do not claim success from Vision labels or metadata alone. The recursive loop requires actual preview inspection in the chat.

## Freeze an independent assessment

1. After tuning, freeze the source, configuration, candidate assignments, master membership,
   and proposal identity. Any candidate-affecting change invalidates later assessment and
   write artifacts.
2. Draw a final quality holdout that excludes tuning examples, targeted per-view supplements,
   and regression canaries. Do not change retrieval, assignment, scoring, quotas, or hold
   rules after reading it; a change starts a new candidate and requires a new holdout.
   Before opening it, run `scripts/audit_eval_split.py` against every tuning round, the
   canary manifest, and the proposed holdout. Require `PASS`; UUID, perceptual-cluster,
   duplicate-group, or burst leakage invalidates the holdout.
3. Report holdout quality separately from targeted diagnostics. An overall pass cannot hide
   a failed material view or an unsupported requested view.
4. After the holdout decision, inspect every selected row for the separate full-master audit.
   The full-master audit authorizes this exact candidate for a membership plan; it is not an
   unbiased estimate of generalization.

## Validate and commit

1. Freeze the final master after its last change. Create a full-master audit that includes every
   selected row, inspect it, and save a passing report with `full_master_audit: true`.
   Run `photo-fieldwork evaluate --master FINAL-MASTER.csv`; targeted audits may supplement
   but cannot replace this final audit.
2. Run `photo-fieldwork validate`. Confirm its `proposal_id` and `master_sha256` match the final evaluation.
3. Generate test and production plans with `photo_archive_bridge.py snapshot-plans --evaluation-report FINAL-EVALUATION.json`. Generation must fail on hash drift.
4. Inspect the plans. Confirm source fingerprint and count, target, proposal hash, HOLD
   separation, and membership-only operations.
5. Run the ten-item write test through the app. Independently verify it with `verify_photos_commit.py`.
6. Run the production plan through the app. Rerun it once to confirm idempotence.
7. Independently verify every album against the plan using the WAL-aware compact verifier.
   Do not open a live, changing Photos database as immutable. The verifier must clean its
   temporary snapshot and report missing, unexpected, outside-source, and HOLD overlap counts.
   A helper receipt or a visually complete album is not completion evidence when independent
   verification disagrees. Preserve the failed report, repair from a new bounded plan, and
   verify again.
8. Mark each phase complete with the hashes of its supporting artifacts and run
   `photo-fieldwork state audit --workspace RUN`. Write a completion report containing exact
   counts, identifiers, evaluation results, privacy facts, and unresolved uncertainty.
9. Label completion artifacts by sensitivity. Before any public share, run
   `lint_public_report.py`; its PASS does not replace human privacy, rights, consent, claim,
   and contextual review. Publish from an allowlisted public handoff, never the private run
   directory.

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
