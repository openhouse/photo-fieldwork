# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

## 1. Freeze a source corpus

Give the broad retrieval corpus a stable name and count. Never alter it during a versioned run. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten.

Reserve the semantic version before work. Keep experiments as rounds inside one run; do not create competing authoritative folders with the same version.

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

## 7. Select with uncertainty

Balance high-confidence evidence, stratified diversity, and exploratory retrieval. Preserve `Unclassified / Editor Field`. A useful corpus does not need every image to support a named project claim.

People associations are first-class archive structure. Preserve named relationships already curated by the archive owner, but never identify unnamed faces or infer sensitive traits.

## 8. Evaluate and loop

Sample low, middle, and high-scoring images from each view. Measure coverage and precision. Read the rejected examples. Revise retrieval, scoring, holds, or labels, then rerun with the same seed. A metric without inspected failure cases is not enough.

Persist known visual rejects and historical holds so they cannot return through another label. After the field is frozen, audit the actual selection and every replacement.

## 9. Plan before writing

Produce proposed-master, hold, membership, and decision manifests before touching the catalog. Every selected stable ID needs a reason. The plan must be idempotent.

## 10. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify exact membership and rerun the test to prove idempotence. Only then create production folders and albums in moderate, resumable batches.

## 11. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. Report missing, unexpected, outside-source, and hold-overlap counts. Preserve receipts, configuration, scripts, and evaluation feedback with the version.

For WAL-backed catalogs, extract compact evidence through a WAL-aware read-only transaction before immutable verification.

## 12. Hand off honestly

Tell editors what the system did and did not do. The result is a contact field for human editing, not the final visual narrative.

Generate the status and completion report from append-only phase receipts. Do not mark a run complete by editing status text manually.
