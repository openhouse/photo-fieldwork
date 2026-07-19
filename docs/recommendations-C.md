# Recommendations C: Photo Fieldwork after a whole-library production run

Date: 2026-07-13
Repository reviewed: <https://github.com/openhouse/photo-fieldwork>
Basis: close reading of `main`, the current local working tree, the test suite, and the completed `v04-C` production workflow against a 603,137-item visible Apple Photos library.

## Revision C implementation status

This document preserves the field report that motivated Revision C. The branch
implements its correctness core: source profiles, visible-library inventory,
resumable lifecycle reconciliation, append-only decision events, deterministic
review rounds, explicit selection semantics, named validation gates, preview
QA, WAL-aware frozen verification, plan/manifest hash binding, schemas,
synthetic regression fixtures, and CI. The larger local review interface and
additional catalog adapters remain appropriate follow-on releases rather than
hidden requirements of this one.

## Executive recommendation

Photo Fieldwork has the right governing idea: retrieval, visible evidence, provenance, safety, and publication permission are different things. The production run showed that this idea survives contact with a very large, private archive.

The next version should concentrate on making the successful field improvisations into supported product behavior. Before adding more adapters or a polished review UI, stabilize five contracts:

1. a resumable run state machine;
2. an append-only decision and provenance ledger;
3. a first-class recursive evaluation and replacement engine;
4. WAL-aware, independently frozen Photos verification;
5. release gates that encode every promise made by the skill documentation.

The project should remain local-first and editor-centered. It should not become an automated taste engine.

## What worked

- The separation between metadata retrieval, local pixel inspection, and factual provenance prevented attractive but unsupported project claims.
- HOLD remained disjoint from the master and gave ambiguous or sensitive material a protected destination.
- `Unclassified / Editor Field` prevented taxonomy from consuming the archive.
- A fixed seed and versioned artifacts made iterative selection intelligible.
- Actual visual review changed the system: overall decisive precision improved from 0.3542 in the first round to 0.9315 in the fifth.
- The permissioned PhotoKit app kept catalog writes narrow: create folders/albums and add existing membership only.
- Test-first writing and exact set verification caught operational boundaries that count-only checks would miss.
- The final plan was idempotent and independently verifiable.

## What the run exposed

### Workflow orchestration lived outside the product

The run needed retrieval expansions, inspection deltas, five evaluation rounds, replacement audits, sequence-HOLD propagation, screen controls, human-sensitive controls, portrait controls, unclassified controls, plan generation, a write test, production, an idempotence rerun, and several independent audits.

Most of those steps required run-specific scripts. Meanwhile, `run-state.json` remained `initialized` until completion documentation was manually reconciled. The artifacts were stronger than the state model describing them.

### Direct immutable verification can be stale

Immediately after the write test, PhotoKit returned a valid ten-item receipt, but `Photos.sqlite?mode=ro&immutable=1` could not see the new album because its current state was still in the WAL. A normal read-only connection could see it.

The successful workaround was:

1. open the live Photos database `mode=ro` with `query_only`;
2. copy only the source fields, receipt albums, and memberships into a compact snapshot;
3. close the snapshot;
4. reopen that snapshot with `mode=ro&immutable=1` and `query_only`;
5. run exact set verification against the frozen artifact.

That should be the supported verification path, not an emergency technique.

### The prose gates are stronger than the validator

The documentation requires more than `validate()` currently checks. The core validator confirms target count, UUID uniqueness, HOLD separation, selection reasons, and represented views. It does not currently enforce all of the following:

- still-photo media kind;
- local pixel availability;
- preview presence and decodability;
- candidate freshness or whole-library retrieval floors;
- named-association and genuinely person-free floors;
- unresolved `needs-review` states;
- per-view evaluation thresholds;
- known-regression absence;
- source and prior-version preservation;
- project-hypothesis labeling when provenance remains incomplete;
- plan/manifest hashes;
- exact Photos folder topology.

### Configuration semantics are not yet fully honest

- View `quota` behaves more like an aspiration than an invariant when a view is sparse or diversity floors cause replacements.
- `minimum_person_free_fraction` currently means “no named People association,” not “no person visible.” Those are materially different.
- `uncertain_count` is derived from evidence-confidence fields, not necessarily from human evaluation uncertainty.
- `exploratory_fraction` appears in the schema but is not applied by the core selector.
- The skill's default source is the 124,484-item wide album, while whole-library work required a new source profile and local implementation changes.

These are fixable, but they should be fixed in the contracts rather than explained away in reports.

### Decisions were repeatedly materialized by rewriting CSVs

CSV is excellent for editor handoff, but weaker as the authoritative history of a recursive run. The production workspace accumulated successive candidate, ready, controlled, reviewed, and proposed-master files. It remained possible to reconstruct what happened, but only by reading filenames, scripts, and modification order together.

The source of truth should be an append-only decision ledger. CSV manifests should become reproducible projections of it.

## Priority 0: correctness and reproducibility

### 1. Add a real run state machine

Add commands such as:

```text
photo-fieldwork run init
photo-fieldwork run status
photo-fieldwork run reconcile
photo-fieldwork run advance
photo-fieldwork run finalize
```

Each phase should declare:

- required inputs;
- expected outputs;
- artifact hashes;
- completion criteria;
- privacy boundary;
- resumability behavior;
- predecessor phase;
- whether catalog mutation is possible.

`reconcile` should infer status from receipts and validated artifacts without silently declaring success. `finalize` should refuse to complete while a required gate is absent or stale.

Acceptance criteria:

- Interrupting and resuming any long inspection does not require a bespoke script.
- `run-state.json` cannot say `initialized` after validated production receipts exist.
- Every phase transition records timestamp, command version, config hash, input hashes, and output hashes.
- Completion reports are generated from state and receipts, not manually retyped.

### 2. Introduce an append-only decision ledger

Use SQLite or JSONL as the authoritative local record. A decision event should contain:

- stable asset UUID;
- run and round IDs;
- decision type;
- previous and new state;
- retrieval reasons;
- visible reason;
- provenance strength;
- safety state;
- reviewer lens or automation source;
- uncertainty;
- timestamp;
- config, code, and inspection-profile hashes.

Suggested event types:

```text
retrieved
inspected
assigned-view
reviewed-fit
reviewed-reject
reviewed-uncertain
placed-on-hold
hold-propagated
replaced
rerouted
selected
committed
verified
```

Generate `candidate-pool.csv`, `proposed-master.csv`, HOLD manifests, evaluation CSVs, and reports as materialized views.

Acceptance criteria:

- Every selected item can answer “why retrieved, what was seen, what was inferred, who or what decided, and what changed later?”
- No history is lost when an assignment or safety state changes.
- Rebuilding manifests from the ledger is deterministic.

### 3. Make recursive evaluation a first-class engine

The current CLI can sample and evaluate, but it does not own the full correction loop. Add a round model:

```text
photo-fieldwork round create
photo-fieldwork round render
photo-fieldwork round evaluate
photo-fieldwork round apply
photo-fieldwork round replacements
photo-fieldwork round convergence
```

The engine should support:

- score-stratified sampling within every view;
- known regressions and prior false positives;
- all new replacements since the previous frozen master;
- low, middle, and high score bands;
- uncertainty samples;
- rejection and HOLD propagation through duplicate, burst, and sequence clusters;
- deterministic replacement from eligible candidates;
- explicit system changes between rounds;
- a convergence report across rounds.

Acceptance criteria:

- A rejected or newly held selected item cannot be replaced by an uninspected item.
- Every replacement receives visual review or an explicit approved exception.
- The report shows precision trajectory, error-category trajectory, changed rules, and master delta.
- The system stops only when configured gates pass or a genuine blocker is recorded.

### 4. Ship WAL-aware frozen verification

Add a supported command:

```text
photo-fieldwork photos snapshot-verification \
  --plan PLAN \
  --receipt RECEIPT \
  --photos-db Photos.sqlite \
  --output verification.sqlite
```

The command should read the live database with `mode=ro` and `query_only`, include current WAL state, copy only the minimum necessary rows, close the output, checksum it, and then reopen it immutably for verification.

Verification should cover:

- exact album set equality;
- source membership and source count;
- HOLD/master disjointness;
- album titles and identifiers;
- folder-parent topology;
- plan and receipt agreement;
- idempotent-rerun identity agreement;
- prior protected album counts;
- unexpected, missing, and outside-source members.

Acceptance criteria:

- A just-created PhotoKit album can be verified without waiting for an uncontrolled SQLite checkpoint.
- The verifier never writes to the Photos library.
- The frozen snapshot is small, checksummed, and sufficient to rerun verification later.
- A synthetic WAL fixture reproduces the stale-immutable failure in CI.

### 5. Encode the full release contract

Expand `validate` into named gates with machine-readable results:

```text
target
uniqueness
still-only
pixels-local
previews-decodable
safety-disjoint
needs-review-resolved
view-coverage
evaluation-overall
evaluation-per-view
named-associations
visible-person-free
fresh-candidate-share
selection-reasons
hypothesis-labeling
source-preservation
prior-version-preservation
plan-frozen
```

Each gate should report `PASS`, `FAIL`, or `WAIVED`, with evidence and a waiver reason. Avoid one undifferentiated pass boolean.

Acceptance criteria:

- Every invariant promised in `SKILL.md` has a corresponding executable gate or is explicitly labeled as human review.
- A low-precision material view cannot hide behind a passing overall precision score.
- Sparse or hypothesis-only views can use a documented policy rather than silently lowering the threshold.

### 6. Promote source profiles to a stable contract

Replace scattered constants with source profiles:

```json
{
  "id": "visible-library-stills://v1",
  "reader": "apple-photos",
  "media_kind": "still",
  "hidden": false,
  "trashed": false,
  "primary_scope": true,
  "expected_count_policy": "snapshot",
  "inventory": "whole-library-visible-stills.sqlite"
}
```

Support at least:

- a named immutable album;
- all visible stills;
- a filesystem inventory for non-Photos testing.

Remove hardcoded live counts such as `603137` from inventory builders. Store observed counts and source fingerprints in receipts, then require the run to decide whether a count change invalidates or refreshes the snapshot.

Acceptance criteria:

- `doctor`, inventory building, inspection, planning, writing, and verification resolve the same source-profile contract.
- PhotoKit and SQLite source predicates have a tested equivalence check.
- A normal library addition produces a clear “source changed” workflow rather than a code edit.

## Priority 1: editorial quality and safety

### 7. Separate safety, consent, and publication states

Replace a binary `clear`/`hold` model with orthogonal fields:

```text
automated_safety: clear | flagged
human_safety: clear | hold | needs-review
consent: unknown | internal-only | editor-review | approved
publication: not-assessed | restricted | eligible
```

An identity-document flag, an intimate domestic photograph, a protest image, and an ordinary portrait of a collaborator do not present the same problem. They should not be collapsed into one state.

Preserve the rule that anything potentially sensitive enters a protected state before ranking.

### 8. Define quota semantics explicitly

Give each view configurable constraints:

```json
{
  "id": "04",
  "target": 500,
  "minimum": 300,
  "maximum": 700,
  "material": true,
  "hypothesis": true,
  "minimum_precision": 0.8
}
```

Then report whether the selector met the target, minimum, or only the fallback. Do not require quotas to sum to the target if they are not hard allocations.

### 9. Correct people-field semantics

Distinguish:

- `has_named_association`: existing Apple People metadata;
- `detected_face_count`: local face detection without identification;
- `visible_people`: human-reviewed or controlled visible-context label;
- `person_free`: no detected or visibly reviewed person;
- `consent_state`: separate from all of the above.

Rename `minimum_person_free_fraction` if it continues to mean “no named association.” Prefer enforcing actual person-free context after inspection.

### 10. Add event and sequence controls

The production run needed repeated workday, subject-day, and duplicate-sequence controls beyond Apple burst metadata. Add configurable event clustering using coarse time, album provenance, visual labels, and duplicate links.

Support:

- per-event and per-sequence caps;
- one-representative policies;
- HOLD propagation across near-duplicate sequences;
- provenance-preserving exceptions;
- a sequence contact sheet for human review.

### 11. Make inspection reuse trustworthy

Fresh inspection should mean evidence is current, not necessarily that identical pixels must be decoded repeatedly. Add a content-addressed inspection cache keyed by:

- asset UUID;
- asset modification fingerprint;
- requested image dimensions;
- inspector and OS/Vision versions;
- OCR/classification/face-detection settings;
- safety ruleset version.

The run should report `fresh`, `verified-cache-hit`, or `stale-reinspected`. This would reduce large recursive runs without disguising reused evidence as new inspection.

### 12. Integrate preview QA into the gate

The working tree already contains useful movement here: corrupt previews are rendered explicitly on contact sheets, and a preview-decoding verifier exists. Finish the integration:

- add a CLI command;
- emit a structured report;
- fail local-inspection completion when required previews are missing or corrupt;
- distinguish source-unavailable, export-failed, zero-byte, and decode-failed;
- automatically queue recoverable failures for re-export.

## Priority 2: productization

### 13. Add a local review surface

Build a small static or localhost-only review interface over the ledger and previews. It should support keyboard decisions, side-by-side near duplicates, view reassignment, HOLD, uncertainty, and reason capture.

Do not begin with a large DAM interface. The first surface should make the existing contact-sheet and CSV loop faster while preserving inspectable exports.

Required properties:

- no network requests;
- no embedded exact location or raw OCR;
- stable asset labels;
- undo implemented as a new ledger event;
- review progress and unreviewed replacement queues;
- export back to ordinary CSV and JSON.

### 14. Split generic engine from private machine profile

The reusable method and Jamie-specific integration are currently close together. Keep both, but make the boundary explicit:

- generic engine and schemas;
- adapter protocol;
- Apple Photos adapter;
- local private profile containing paths, protected identifiers, source profiles, and permissioned-app identity.

Public tests and examples should use synthetic fixtures. Private machine profiles should be validated locally and excluded from distributable reports.

### 15. Add public-safe export and artifact classification

Label run artifacts:

```text
public
private-editorial
sensitive
ephemeral
```

Provide `photo-fieldwork export public-report` that omits absolute paths, People names, raw manifests, exact places, preview locations, and sensitive HOLD reasons while retaining aggregate methods and results.

### 16. Version schemas and support migrations

Add JSON Schemas for:

- run state;
- source profiles;
- inspection plans and receipts;
- snapshot membership plans and receipts;
- decision events;
- evaluation rounds;
- validation reports;
- verification reports.

Every artifact should include `schema_version`. Provide migrations or explicit incompatibility errors rather than accepting subtly different fields.

### 17. Add performance observability

Large runs need predictable operational feedback:

- stage progress and throughput;
- resume position;
- estimated time and disk use;
- candidate and preview cache hit rates;
- inspection failure categories;
- retrieval contribution by signal;
- memory-bounded joins and batch sizes;
- deterministic sharding and merge verification.

Store generalized operational metrics, never private OCR or exact locations.

## Testing and repository practice

The current `make check` passes all eight tests. That is a sound seed, but the production-critical surface is much larger than the tested surface. There is currently no visible GitHub issue or pull-request backlog and no checked-in CI workflow.

### Recommended test layers

1. **Core unit tests**
   - quota semantics;
   - diversity floors;
   - `needs-review` exclusion;
   - actual person-free semantics;
   - event caps and sequence propagation;
   - per-view evaluation gates;
   - unused or unknown configuration fields.

2. **Synthetic SQLite adapter fixtures**
   - named album and whole-library sources;
   - WAL-visible but immutable-stale album creation;
   - parent-folder topology;
   - missing and extra memberships;
   - prior-version drift;
   - Photos schema capability probing.

3. **Plan/receipt contract tests**
   - idempotent rerun returns the same identifiers;
   - title collisions are parent-scoped;
   - plan hashes match frozen manifests;
   - add-only writers never remove membership;
   - changed selections require a new version, not mutation of a committed album.

4. **Inspection and preview tests**
   - corrupt and absent previews;
   - resumed inspections;
   - cache freshness;
   - raw OCR non-persistence;
   - network-disabled receipts;
   - optional Vision operations.

5. **End-to-end synthetic run**
   - initialize;
   - retrieve;
   - inspect fixture pixels;
   - evaluate two rounds;
   - reject and replace;
   - validate;
   - test write against a fake adapter;
   - production write;
   - idempotence rerun;
   - frozen independent verification;
   - finalize completion report.

Add CI for Python 3.11 through the newest supported version. Keep the standard-library core dependency-free, but declare an explicit `apple` or `review` extra for Pillow and other adapter-only dependencies.

## Suggested pull-request sequence

Keep changes reviewable. Do not merge the entire production learning as one large patch.

### PR 1: Integrate current whole-library and preview work

- Commit the existing source-profile support, visible-library inventory builder, preview decoder, corrupt-preview rendering, full Vision labels, and optional inspection operations.
- Remove the hardcoded source count.
- Add synthetic tests for every new path.

### PR 2: Frozen Photos verification

- Add compact WAL-aware snapshot creation.
- Verify membership, source, topology, and prior protected counts.
- Add the WAL regression fixture.

### PR 3: Run lifecycle and artifact schemas

- Introduce run-state transitions, reconciliation, hashes, and generated completion reports.
- Add schemas and validation for plans and receipts.

### PR 4: Decision ledger and round engine

- Add append-only events.
- Materialize current CSV outputs from the ledger.
- Support rejection, HOLD, rerouting, deterministic replacement, and convergence reporting.

### PR 5: Full release gates

- Encode all documented invariants.
- Add per-view policies and explicit waivers.
- Correct people and uncertainty semantics.

### PR 6: Local review surface

- Build only after the ledger and round contracts are stable.

## Recommended near-term issues

1. Immutable Photos verifier misses uncheckpointed WAL state.
2. Run state does not reconcile automatically from receipts.
3. `validate` does not encode all skill release gates.
4. View quota semantics conflict with fallback and diversity behavior.
5. `minimum_person_free_fraction` does not mean visibly person-free.
6. `exploratory_fraction` is configured but not enforced.
7. Recursive replacement review requires bespoke scripts.
8. Whole-library source support is not yet integrated into `main` as a tested profile.
9. Preview-decoding QA is not part of phase completion.
10. Production plan verification does not check folder topology.
11. Inventory builder hardcodes a live library count.
12. Apple adapter and machine-specific profile need a clearer boundary.

## What not to do yet

- Do not add cloud vision or remote review as the solution to local workflow friction.
- Do not train or market a global aesthetic score.
- Do not collapse safety review into consent or publication permission.
- Do not replace editor-visible manifests with an opaque database-only workflow.
- Do not make role-played editorial judgment look like eyewitness provenance.
- Do not build a large UI before the decision, round, and verification contracts stabilize.
- Do not mutate a committed album to “fix” a later selection; create a new version.

## Product position

The strongest future for Photo Fieldwork is not “AI picks your best photographs.” It is:

> A local-first, evidence-aware system for turning a very large personal archive into an editor-ready field whose retrieval, visual review, uncertainty, safety decisions, and catalog commit can all be inspected and independently verified.

That promise is narrower than automated curation and much more defensible. The production run suggests it is also genuinely useful.
