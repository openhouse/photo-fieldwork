# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

Initialize a private run workspace and a local machine profile. Run live,
read-only preflight before inventory or inspection. If authorization, source
count, local sample pixels, schema compatibility, or disk access fails, stop
before expensive work.

## 1. Freeze a source corpus

Give the broad retrieval corpus a stable name and count. Never alter it during a versioned run. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten.

The source may be a physical album or the virtual
`visible-library-stills://v1` scope. Derive its count from the read-only snapshot;
do not compile a previous count into source code.

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

Draw an untouched final holdout after the freeze. Report review completion,
view sampling coverage, decisive fit rate, field audit rate, and a 95% Wilson
interval. Run safety auditing separately.

## 10. Plan before writing

Produce proposed-master, hold, membership, and decision manifests before touching the catalog. Every selected stable ID needs a reason. The plan must be idempotent.

## 11. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify exact membership and rerun the test to prove idempotence. Only then create production folders and albums in moderate, resumable batches.

The preferred PhotoKit writer and explicit AppleScript fallback must consume the
same frozen plan. A backend change must be recorded and cannot be silent.

## 12. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. Report missing, unexpected, outside-source, and hold-overlap counts. Preserve receipts, configuration, scripts, and evaluation feedback with the version.

## 13. Hand off honestly

Tell editors what the system did and did not do. The result is a contact field for human editing, not the final visual narrative.

Publication is a separate reduction. Create an allowlisted projection only for
assets with scoped rights and consent states. Never derive the public handoff by
copying the private master and attempting to remove sensitive columns later.
