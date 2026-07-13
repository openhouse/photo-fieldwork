# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

## 1. Freeze a source corpus

Give the broad retrieval corpus a stable name and count. Never alter it during a versioned run. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten.

Represent the boundary as a versioned source profile. A named album and the
visible still-photo library are different profiles but must resolve to the same
contract in inventory, inspection, writing, and verification.

## 2. Build a compact inventory

Capture stable IDs, filenames, albums, existing people associations, dates, places, favorite/edit status, duplicate and burst groups, and local availability. Dates are evidence, not truth: film scans and later imports can carry misleading timestamps.

## 3. Retrieve broadly with metadata

Use albums, people, keywords, dates, places, labels, and prior attention to create candidate views. Call these retrieval hypotheses. Metadata can find possible relevance; it cannot establish what a photograph visibly proves.

Persist a structured retrieval summary, including the outside-prior fraction
when comparing with an earlier corpus, and pass it to validation. Treat excluded
album terms as asset-level exclusions, not merely suppressed labels.

## 4. Calibrate before scaling

Inspect a small score-stratified sample from every proposed view. Record visible fit, rejection, uncertainty, and a brief reason. Include obvious failure cases. If category precision is weak, change the system before processing thousands of images.

## 5. Inspect locally

After metadata has reduced the corpus, inspect local previews for technical availability, broad visible context, duplicate structure, and safety indicators. Keep raw OCR ephemeral. Never upload private pixels or metadata without explicit authorization.

## 6. Quarantine, do not erase

Potential identity documents, private correspondence, contact details, financial records, medical information, credentials, and other sensitive material belong in HOLD. A hold is not deletion. It is a protected review state that can never enter the master automatically.

## 7. Select with uncertainty

Balance high-confidence evidence, stratified diversity, and exploratory retrieval. Preserve `Unclassified / Editor Field`. A useful corpus does not need every image to support a named project claim.

People associations are first-class archive structure. Preserve named relationships already curated by the archive owner, but never identify unnamed faces or infer sensitive traits.

## 8. Evaluate and loop

Sample low, middle, and high-scoring images from each view. Measure coverage and precision. Read the rejected examples. Revise retrieval, scoring, holds, or labels, then rerun with the same seed. A metric without inspected failure cases is not enough.

Record each review and replacement in the append-only decision ledger. A
replacement must already have local pixels and a verified preview. Propagate
HOLD through true duplicate and reviewed sequence clusters before reranking.

## 9. Plan before writing

Produce proposed-master, hold, membership, and decision manifests before touching the catalog. Every selected stable ID needs a reason. The plan must be idempotent.

## 10. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify exact membership and rerun the test to prove idempotence. Only then create production folders and albums in moderate, resumable batches.

## 11. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. Report missing, unexpected, outside-source, and hold-overlap counts. Preserve receipts, configuration, scripts, and evaluation feedback with the version.

When the catalog uses SQLite WAL, capture the current state into a compact
read-only snapshot before reopening that evidence immutably. Verify folder
topology as well as album membership.

## 11.5 Reconcile and finalize

Run `photo-fieldwork run reconcile` after each durable phase. Finalization must
fail while any required phase, named gate, receipt, or independent verification
is absent. Completion reports should be generated from artifacts and hashes,
not manually inferred from filenames.

## 12. Hand off honestly

Tell editors what the system did and did not do. The result is a contact field for human editing, not the final visual narrative.
