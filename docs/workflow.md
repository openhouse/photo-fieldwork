# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

Initialize a private run workspace and a local machine profile. Run live,
read-only preflight before inventory or inspection. If authorization, source
count, local sample pixels, schema compatibility, or disk access fails, stop
before expensive work.

If the user supplies an interrupted workspace, do not initialize a replacement
run. Validate the sequence and hash linkage of `run-events.jsonl`; recover
`run-state.json` from that ledger when needed. Rehash its recorded artifacts,
plans, receipts, and lock. When a recorded artifact has drifted, append a
CAS-guarded `run invalidate` event at the earliest affected phase before repair;
do not hand-edit state or overwrite the prior event. Then resume only the next
incomplete phase with the expected ledger revision. Required phases cannot be skipped. Existing inspection rows remain part of the evidence
and of every cumulative receipt counter. A successful resume does not authorize
a write: evaluation, final freeze and holdout, and validation must still pass.
For a schema-v2 workspace created before the event ledger existed, preserve the
materialized state in one explicitly marked migration genesis event; do not
invent prior transitions.

## 1. Freeze a source corpus

Give the broad retrieval corpus a stable name and count. Never alter it during a versioned run. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten.

The source may be a physical album or the virtual
`visible-library-stills://v1` scope. Derive its count from the read-only snapshot;
do not compile a previous count into source code. Record a SHA-256 digest of the
sorted source membership. Drift in either count or membership requires a new
versioned inventory and source freeze.

## 2. Build a compact inventory

Capture stable IDs, filenames, albums, existing people associations, dates, places, favorite/edit status, duplicate and burst groups, and local availability. Dates are evidence, not truth: film scans and later imports can carry misleading timestamps.

## 3. Retrieve broadly with metadata

Use albums, people, keywords, dates, places, labels, and prior attention to create candidate views. Call these retrieval hypotheses. Metadata can find possible relevance; it cannot establish what a photograph visibly proves.

Classify album lineage explicitly. Generated fieldwork, private review, and
write-audit albums cannot silently become evidence. Report novelty outside any
prior corpus in both the candidate pool and final master.

## 4. Calibrate before scaling

Inspect a small score-stratified sample from every proposed view. Record visible
fit, rejection, uncertainty, and a brief reason. Include obvious failure cases.
If a category's decisive fit rate is weak, change the system before processing
thousands of images.

## 5. Inspect locally

After metadata has reduced the corpus, inspect local previews for technical availability, broad visible context, duplicate structure, and safety indicators. Keep raw OCR ephemeral. Never upload private pixels or metadata without explicit authorization.

## 6. Quarantine, do not erase

Potential identity documents, private correspondence, contact details, financial records, medical information, credentials, and other sensitive material belong in HOLD. A hold is not deletion. It is a protected review state that can never enter the master automatically.

## 7. Select with uncertainty

Balance high-confidence evidence, stratified diversity, and exploratory retrieval. Preserve `Unclassified / Editor Field`. A useful corpus does not need every image to support a named project claim.

Treat candidate views as hypotheses and solve overlapping assignments jointly.
Preserve exact active-view quotas and per-view event caps. Infeasibility
produces capacity diagnostics, not silent quota changes. Among feasible
solutions, maximize the deterministic total candidate benefit globally rather
than committing flexible assets by first match. Prune only provably dominated
uncapped-view edges and report graph sizes; retain the full graph for views with
event caps. Satisfy diversity floors jointly with deterministic alternating
path backtracking so an early floor choice cannot strand a later feasible one.

People associations are first-class archive structure. Preserve named relationships already curated by the archive owner, but never identify unnamed faces or infer sensitive traits.

## 8. Evaluate and loop

Sample low, middle, and high-scoring images from each view. Measure review
completion, view sampling coverage, and decisive fit rate. Read the rejected
examples. Revise retrieval, scoring, holds, or labels, then rerun with the same
seed. A metric without inspected failure cases is not enough.

These working rounds are tuning evidence. Keep them out of the final holdout.

## 9. Freeze and audit the final field

Freeze the surviving master and derive an effective final config. Preserve
intent quotas, but set effective quotas to actual counts and mark unsupported,
deferred, or deliberately empty views honestly. Hash the master, HOLD, config,
and replay validation into `run-lock.json`.

Omit unsupported production albums and retain an explicit gap report. “Not
recovered in this run” is not evidence that no relevant photograph exists.

Draw an untouched final holdout after the freeze. Report review completion,
view sampling coverage, decisive fit rate, field audit rate, and a 95% Wilson
interval. Run safety auditing separately.

Audit holdout separation from all prior tuning and canary evidence across UUID,
perceptual cluster, duplicate group, and burst group. Keep regression canaries
outside fresh coverage and precision metrics. Duplicate image-view judgments
and failed material views block release.
Offline review exports must preserve the opaque relation identifiers plus the
master and proposal identities needed to rerun that audit.

Any selected UUID, assignment, quota, or HOLD change invalidates the final lock,
holdout, evaluation, and plans. Refreeze, inspect a fresh untouched holdout, and
validate before generating replacement plans.

## 10. Plan before writing

Produce proposed-master, hold, membership, and decision manifests before touching the catalog. Every selected stable ID needs a reason. The plan must be idempotent.

Bind the catalog plan to one source, config, proposal, master, final evaluation,
relation-clean holdout report, validation, and the current workspace run lock.
Register its content digest before launch. Each writer attempt receives a
distinct nonce authorizing one exact adapter plan; post-registration mutation,
kind substitution, and copied receipts fail closed.
The bridge reads the authorized adapter once, creates the nonce-bearing runtime
plan as an exclusive private file, and passes its digest to the writer out of
band. The writer verifies that digest against one read before mutation and
records it in the receipt. Independent verification rehashes the runtime plan
against that immutable receipt, so replacing a plan pathname cannot substitute
memberships.
At registration and before every nonce, rehash the run lock and every completed
phase artifact. Validate every adapter album against a catalog membership or an
explicitly locked, candidate-derived auxiliary set. Completion receipts must
match plan ID, execution kind, folders, albums, identifiers, and counts.
Reject duplicate catalog album keys before mapping memberships. Immediately
before mutation, the bridge must reject any nonce whose registration was
invalidated or superseded.

If a registered candidate is invalidated, keep the old registration and
execution history. After governed repair, refreeze, and fresh candidate-bound
evaluation and validation, append a supersession event and atomically
materialize the replacement registration.

## 11. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify source,
topology, and exact membership independently, then record the completed
`write_test` phase with both the completed nonce receipt and a machine-readable
PASS report bound to that receipt, catalog plan, adapter plan, source, and
execution nonce, including the writer-verified runtime-plan digest. Only then
may the release ledger issue a production nonce.
Create production folders and albums in moderate, resumable batches.

The preferred PhotoKit writer and explicit AppleScript fallback must consume the
same frozen plan. A backend change must be recorded and cannot be silent.
The second production attempt must reuse the identical adapter-plan bytes;
different titles or topology do not establish idempotence.

## 12. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. Report missing, unexpected, outside-source, and hold-overlap counts. Preserve receipts, configuration, scripts, and evaluation feedback with the version.

## 13. Hand off honestly

Tell editors what the system did and did not do. The result is a contact field for human editing, not the final visual narrative.

Publication is a separate reduction. Create an allowlisted projection only for
assets with scoped rights, consent, claim, and publication states. Use salted
opaque public IDs. Never derive the public handoff by copying the private master
and attempting to remove sensitive columns later.
