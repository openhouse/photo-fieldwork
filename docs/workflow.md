# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

Initialize a private run and advance phases only with `photo_archive_bridge.py advance-run`. The append-only event ledger, not an editable status file, is the source of operational truth.

## 1. Freeze a source corpus

Give the broad retrieval corpus a stable name and count. Hash its sorted stable-ID membership so a different source with the same count cannot be substituted unnoticed. Never alter it during a versioned run. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten.

## 2. Build a compact inventory

Capture stable IDs, filenames, albums, existing people associations, dates, places, favorite/edit status, duplicate and burst groups, and local availability. Dates are evidence, not truth: film scans and later imports can carry misleading timestamps.

## 3. Retrieve broadly with metadata

Use albums, people, keywords, dates, places, labels, and prior attention to create candidate views. Call these retrieval hypotheses. Metadata can find possible relevance; it cannot establish what a photograph visibly proves.

## 4. Calibrate before scaling

Inspect a small score-stratified sample from every proposed view. Record visible fit, rejection, uncertainty, and a brief reason. Include obvious failure cases. If category precision is weak, change the system before processing thousands of images.

## 5. Inspect locally

After metadata has reduced the corpus, inspect local previews for technical availability, broad visible context, duplicate structure, and safety indicators. Keep raw OCR ephemeral. Never upload private pixels or metadata without explicit authorization.

## 6. Quarantine, do not erase

Potential identity documents, private correspondence, contact details, financial records, medical information, credentials, and other sensitive material belong in HOLD. A hold is not deletion. It is a protected review state that can never enter the master automatically.

Use distinct states for `review_required`, automatic HOLD, human HOLD, and `editor_only`. Only material explicitly clear for the editor field is selectable. None of these states grants publication consent.

Propagate unresolved holds through perceptual, duplicate, and burst relationships before ranking. Do not propagate merely because images share a person, event, date, or place. A `clear_for_editor_field` decision requires an identified human editor.

## 7. Select with uncertainty

Balance high-confidence evidence, stratified diversity, and exploratory retrieval. Preserve `Unclassified / Editor Field`. A useful corpus does not need every image to support a named project claim. Solve view quotas and named-person/person-free floors jointly; when the brief is infeasible, report capacities and deficits without silently rewriting it.

People associations are first-class archive structure. Preserve named relationships already curated by the archive owner, but never identify unnamed faces or infer sensitive traits.

## 8. Evaluate and loop

Sample low, middle, and high-scoring images from each view. Measure coverage, decisive precision, fit rate, uncertainty, and safety misses both overall and per view. Read the rejected examples. Revise retrieval, scoring, holds, or labels, then rerun with the same seed and UUIDs excluded from prior rounds. Keep known regression canaries separate: they may block release but may not improve fresh metrics. Every judgment requires a visible reason.

Before the final evaluation, audit the holdout against every tuning round. UUID, perceptual-cluster, duplicate-group, or burst-group overlap, including related frames inside the holdout itself, invalidates freshness.

## 9. Plan before writing

Produce proposed-master, hold, membership, and decision manifests before touching the catalog. Every selected stable ID needs a reason. The plan must be idempotent.

Hash the exact stable-ID membership and view assignments as well as the exact evaluation sample. The final passing evaluation and catalog plan must name the same hashes. The plan is authorized only for an editor-field release; it records `publication_clearance: false`.

## 10. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify exact membership and rerun the test to prove idempotence. Only then create production folders and albums in moderate, resumable batches.

The plan must name the required helper revision and exact source-membership SHA-256. The helper must verify both before mutation and return a fresh launch nonce plus the SHA-256 of the exact plan bytes it executed.

## 11. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. When Photos has uncheckpointed WAL state, first copy the relevant committed rows through a query-only read transaction, then open that compact snapshot immutably. Never checkpoint the live Photos database. Report missing, unexpected, outside-source, and hold-overlap counts. Preserve receipts, configuration, scripts, and evaluation feedback with the version.

## 12. Hand off honestly

Tell editors what the system did and did not do. The result is a contact field for human editing, not the final visual narrative. Any public use starts from a separate redacted derivative review and an allowlisted handoff; it never publishes the editor master directly.
