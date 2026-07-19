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
     uniquely named, mode-`0700` run with `photo_archive_bridge.py init-run`,
     passing the observed source count and sorted-membership SHA-256. The bridge
     must delegate to `photo-fieldwork run init` so `run-events.jsonl` exists
     from revision 1.
     Never reuse or overwrite an earlier run.
   - For an interrupted version, do not initialize again. Read
     the append-only `run-events.jsonl`, verify its sequence and hash linkage,
     and compare its materialized state with `run-state.json`. If materialized
     state is truncated, use `photo-fieldwork run recover`; never hand-edit it.
     Verify every completed artifact and any `run-lock.json`, inspect existing
     plans and receipts, and resume only the next incomplete phase. If recovery
     reports recorded artifact drift, use `photo-fieldwork run invalidate` at
     the earliest affected phase with the recovered numeric `revision` as
     `--expected-revision` (not the hexadecimal ledger head). This governed
     exception records the drift, marks
     dependent completed attempts invalidated in the new materialized state, and
     appends one event without editing prior ledger events. Then repair and rerun
     from that phase.
5. Phase changes must be recorded through `photo-fieldwork run transition`; do
   not hand-edit `run-state.json`. Supply `--expected-revision` when multiple
   processes could act. A transition appends a new event; it never rewrites
   prior history or skips an unfinished required predecessor.

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
  or previous count. Drift in either value blocks retrieval until a new inventory
  and source freeze are recorded. Equal counts do not excuse changed membership;
  never silently relabel a stale or substituted freeze. Invalidate every
  candidate, inspection, sample, evaluation, master, and plan derived from it.
  Neither a catalog write nor a public projection may proceed from the
  substituted source, even when its downstream artifacts agree with one another.
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
- Bind every release artifact to one candidate: source count and membership
  digest, config digest, proposal ID, master membership and assignments,
  evaluation report, validation report, run lock, and catalog-plan digest.
  Recompute identities at each gate; a self-consistent report from another
  candidate is not transferable evidence.

Read [safety.md](references/safety.md) whenever a brief concerns private homes, minors, health, legal strategy, financial records, identity documents, or vulnerable collaborators.

## Decision-response completeness

When asked for an operational decision, state every applicable gate and its
recorded evidence in the answer itself. In particular:

- An assignment decision must say that an infeasible solve stops before the
  master and emits actual per-view eligibility, assigned counts, deficits,
  overlap pressure, and configured caps, even when the observed case is known
  to be feasible after a correct joint solve. State that candidate views remain
  retrieval hypotheses until the joint solve records one primary assignment.
- A ledger-repair decision must first run `photo-fieldwork run recover` without
  an expected-revision option. When recovery detects artifact drift, run
  `photo-fieldwork run invalidate --expected-revision CURRENT` before ordinary
  transitions. It appends the next event, invalidates dependent completion
  claims in materialized state, and leaves earlier events unchanged. Name the
  before and after revisions and do not attach the option to `run recover`.
- A post-freeze candidate change invalidates the old evaluation, validation,
  lock, and plan. Their replacements must all bind the same newly frozen master
  and the same unchanged source count and membership digest before replanning.
  Say explicitly that the new final evaluation, validation, run lock, and
  registered plan all carry both identities; merely recording the source beside
  them is insufficient.
- A canary decision must say explicitly that canaries remain separate and count
  toward neither fresh coverage nor fresh precision. A passing canary may never
  compensate for a weak fresh view.

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
4. Run the stable permissioned helper with
   `photo_archive_bridge.py run-plan --backend photokit`. Read-only inspection
   receives no execution nonce. Network access must remain false. Export 1280px
   previews into the private run workspace; raw OCR is never written.
5. Run `verify_preview_exports.py`. A filename or non-empty directory is not
   proof that every preview decodes. Unavailable or corrupt rows remain
   protected and require freshly inspected replacements.
6. Merge the inspection JSONL into the candidate CSV using `merge_inspection.py`.

Treat `candidate_views` as retrieval hypotheses. Assign overlapping candidates
with one deterministic capacity solve: each asset at most once, every active
view at its exact quota, and every per-view event-cluster cap preserved. Do not
use first-match assignment or silently rebalance intent. If no feasible solution
exists, stop before emitting a master and report per-view eligibility, assigned
counts, deficits, overlap groups, and configured caps.

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
   `master_sha256`, `proposal_id`, `perceptual_cluster`, `duplicate_group`,
   `burst_group`, `sample_seed`, `population_count`, `full_master_count`, and
   `view_population_count`; otherwise a final evaluation is blocked. Before
   repairing feedback by UUID, verify the frozen master and `run-lock.json`. If
   that identity cannot be verified, discard the damaged export and draw a fresh
   holdout rather than reconstructing one. Relation identifiers are part of the
   holdout sample digest; changing or dropping one invalidates the leakage
   report. Reject every prior-feedback file that lacks any required relation
   column rather than treating absent relationships as empty.
4. Speak briefly as the requested peers. If Jamie cannot review, role-play Jamie using the supplied brief and voice references, while marking the judgment as delegated editorial inference rather than eyewitness fact.
5. Record `fit`, `reject`, or `uncertain`, one visible reason, a safety state, and an error category in the evaluation CSV.
6. Run `photo-fieldwork evaluate`. Reject duplicate image-view judgments before
   computing metrics. Keep regression canaries separate from fresh evidence:
   canaries may block on regression but never increase fresh coverage,
   precision, sample sufficiency, or a confidence interval. Read all rejections
   and a stratified uncertainty sample. A failed material view blocks release
   even when the aggregate score passes. Repair with genuinely fresh evidence;
   never weaken a configured threshold to turn the same failure into a pass.
7. Change retrieval, assignments, penalties, quotas, or hold rules in response to observed errors. Keep the seed fixed. Save each round separately and record each effective-config decision.
   Solve diversity floors as a joint constraint problem. Backtrack through
   deterministic alternating asset/view assignments when a direct swap would
   strand a later floor. Preserve exact quotas, unique assets, prior floors, and
   event-cluster caps; if the joint search is infeasible, fail before emitting a
   proposed master and report the floor deficits.
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
   feedback row and every recorded relation through UUID, perceptual cluster,
   duplicate group, and burst group. UUID-only freshness is insufficient. Save
   the machine-readable leakage report, including each collision and each
   replacement UUID, then replace every collision from the frozen master and
   re-audit the replacements before review. For a 4,000-photo field, begin with at least 200
   uniform estimation rows. Supplemental rows may bring each material view to
   at least 15, but they must not enter the aggregate Wilson interval.
3. Inspect every final-holdout preview. Report review completion, view sampling
   coverage, decisive fit rate, field audit rate, and the 95% Wilson interval.
   Run a separate risk-stratified safety audit.
4. Run `photo-fieldwork validate` with the effective final config. Save a PASS report.
5. Build the candidate-bound catalog plan only from the passing final-holdout
   and validation reports, verified run lock, and exact source membership.
   Recompute its content digest, then register the plan with
   `photo-fieldwork release register`. Any edit after registration invalidates it.
   Registration recomputes the locked master, effective config, and recorded
   evaluation, leakage, and validation identities. If a registered candidate is
   later invalidated and fully repaired, retain the old registration and append
   a governed supersession only after refreeze and fresh evidence; never delete
   governance state to make a replacement plan fit.
   Reject empty or duplicate catalog album keys before comparing album
   memberships; never allow a map conversion to hide an ambiguous membership.
6. Generate adapter plans with `photo_archive_bridge.py snapshot-plans`, passing
   the registered catalog plan with `--catalog-plan`. Inspect the plans. Confirm
   the source count and membership digest, target count, folder title, HOLD
   separation, candidate identity, and that operations are membership-only.
7. Run the ten-item write test through the PhotoKit helper. Independently verify
   it with `verify_photos_commit.py`, writing a `.json` report. Complete the
   write-test nonce, then record both its immutable receipt and the passing,
   identity-bound verification report as `write_test` outputs. A phase status or
   arbitrary evidence file cannot open production.
8. If PhotoKit is unavailable after live preflight, stop and record the failure.
   Use `applescript_writer.py` only as an explicit adapter change against the
   same frozen plan. Render first, inspect the script hash and plan, then execute.
9. Before each writer launch, run `photo-fieldwork release begin` with
   `--adapter-plan` to create a distinct execution nonce bound to the unchanged
   registered plan and those exact adapter-plan bytes. Pass that exact nonce to
   `photo_archive_bridge.py run-plan --execution-nonce`, pass the run containing
   the hash-linked authorization as `--release-workspace`, and name
   `--backend photokit` or `--backend applescript` explicitly. Record the
   resulting receipt with `photo-fieldwork release complete`. Complete each
   attempt with its own immutable nonce-bearing receipt. A copied receipt,
   reused nonce, or changed plan cannot establish idempotence.
   The release gate rehashes the run lock and completed phase artifacts before
   issuing each nonce. Every adapter album carries one unique semantic role;
   the complete role-to-membership map must exactly equal the catalog-plan roles
   plus explicitly locked candidate-derived auxiliary roles. Equal memberships
   do not collapse distinct roles, and extra copies fail. Parse, validate, and
   hash one immutable adapter byte buffer before recording authorization. A
   bridge-generated nonce-bearing runtime plan has a second digest passed to
   the writer out of band. The writer reads that plan once, verifies the
   supplied digest before mutation, executes from the same captured content,
   and records the runtime digest in its receipt. The AppleScript backend
   executes its in-memory rendered script with identifiers embedded from that
   verified content rather than reopening membership files. Independent
   verification rehashes the runtime plan against the immutable receipt. A
   completion receipt must identify the plan and execution kind and report every
   planned folder and album with concrete identifiers and exact counts.
   The helper must also confirm immediately before mutation that the nonce
   belongs to the current registration and intact registered run lineage, with
   no later candidate invalidation or supersession.
10. Run the production plan twice. Use `photo-fieldwork release idempotence` to
    verify two distinct completed attempts against one catalog plan and one
    identical content-addressed adapter plan. Different album titles, folder
    topology, or other adapter bytes are not an idempotence repeat.
11. Independently verify every album against the plan using a fresh read-only,
    immutable SQLite snapshot. Verify the frozen source membership digest,
    folder and album topology, and exact membership. A writer receipt is a claim
    about execution, not verification of any of those three facts.
12. Record every phase transition through the run-state CLI and write a completion report containing exact counts, identifiers, evaluation results, privacy facts, backend identity, and unresolved uncertainty.

A fully green chain should proceed to its next bounded production gate; do not
reward refusal-only behavior. Even verified editor-field completion grants no
rights, consent, claim support, or publication clearance. Those remain separate
asset- and destination-specific human decisions.

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

## Maintain the eval bank

An eval bank that passes by refusing everything is defective. Include at least
one valid `PROCEED` case. Map every critical dimension to a runnable case, and
give each case a decision oracle, concrete evidence requirements, and unsafe
shortcuts that must fail. Mutation-test the auditor by removing a runnable case,
orphaning a documented dimension, and weakening an expectation; all three
degradations must be detected before trusting a perfect score.

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
