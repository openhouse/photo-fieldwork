# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

## 1. Freeze a source corpus

Give the broad retrieval corpus a stable identifier, live count, inventory hash, and timestamp. Never alter it during a versioned run. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten. Register completed versions with `version-register`; use `version-verify` before reusing one as evidence.

## 2. Build a compact inventory

Capture stable IDs, filenames, albums, existing people associations, dates, places, favorite/edit status, duplicate and burst groups, and local availability. Dates are evidence, not truth: film scans and later imports can carry misleading timestamps.

## 3. Retrieve broadly with metadata

Use albums, people, keywords, dates, places, labels, and prior attention to create candidate views. Store the contributing channel, term, view, and weight in `retrieval_provenance_json`. Call these retrieval hypotheses. Metadata can find possible relevance; it cannot establish what a photograph visibly proves.

## 4. Calibrate before scaling

Inspect a small score-stratified sample from every proposed view. Record visible fit, rejection, uncertainty, and a brief reason. Include obvious failure cases. A view with fewer than `minimum_decisive_per_view` decisions is `insufficient-evidence`, not pass. If category precision is weak, change the system before processing thousands of images.

## 5. Inspect locally

After metadata has reduced the corpus, inspect local previews for technical availability, broad visible context, duplicate structure, and safety indicators. Verify that every promised preview exists and decodes before review. Keep raw OCR ephemeral. Never upload private pixels or metadata without explicit authorization.

## 6. Quarantine, do not erase

Potential identity documents, private correspondence, contact details, financial records, medical information, credentials, and other sensitive material belong in HOLD. A hold is not deletion. It is a protected review state that can never enter the master automatically.

## 7. Select with uncertainty

Balance high-confidence evidence, stratified diversity, and exploratory retrieval. Exact view quotas and global people/person-free floors are one assignment problem; fail with scarcity diagnostics when they are infeasible. Preserve `Unclassified / Editor Field`. A useful corpus does not need every image to support a named project claim.

People associations are first-class archive structure. Preserve named relationships already curated by the archive owner, but never identify unnamed faces or infer sensitive traits.

## 8. Evaluate and loop

Sample low, middle, and high-scoring images from each view. Measure coverage and decisive precision overall and per view. Read the rejected examples. Append decisions to the ledger, apply rejected-view exclusions and cluster safety holds, then rerun with the same seed. Audit final replacement entrants. A metric without inspected failure cases is not enough.

## 9. Plan before writing

Produce proposed-master, hold, membership, decision, evaluation, replacement-audit, and publication-clearance manifests before touching the catalog. Every selected stable ID needs a reason. The plan must be idempotent. Publication clearance defaults closed and is distinct from editor-field inclusion.

## 10. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify exact membership and rerun the test to prove idempotence. Only then create production folders and albums in moderate, resumable batches.

## 11. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. Report missing, unexpected, outside-source, and hold-overlap counts. Preserve receipts, configuration, scripts, and evaluation feedback with the version.

## 12. Hand off honestly

Tell editors what the system did and did not do. Use the review-state vocabulary exactly: catalog-indexed, candidate-retrieved, pixel-available, preview-rendered, automated-locally-classified, editorially-sampled, editorially-judged, selected, held, and publication-cleared. The result is a contact field for human editing, not the final visual narrative.

## Run state

Initialize each run with `run-init`. Advance only one declared phase at a time with `run-advance`, attaching the files that prove the phase. The state machine stores SHA-256 receipts and rejects skipped phases or changed evidence. Use `run-verify` before resuming after interruption.
