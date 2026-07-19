# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

## 1. Freeze a source corpus

Resolve the source through a versioned source adapter and write a validated `source-manifest.json` containing its stable identifier, observed count, membership digest, predicate version, adapter, and fingerprint. A source may be an album or the visible still-photo library. Never alter it during a versioned run. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten.

## 2. Build a compact inventory

Capture only the fields the run needs. The default retrieval profile omits exact coordinates and machine-specific source paths. Capture stable IDs, filenames, albums, existing people associations, dates, coarse places, favorite/edit status, duplicate and burst groups, and local availability. Dates are evidence, not truth: film scans and later imports can carry misleading timestamps.

## 3. Retrieve broadly with metadata

Use albums, people, keywords, dates, places, labels, and prior attention to create candidate views. Call these retrieval hypotheses. Metadata can find possible relevance; it cannot establish what a photograph visibly proves.

## 4. Calibrate before scaling

Inspect a small score-stratified sample from every proposed view. Record visible fit, rejection, uncertainty, and a brief reason. Include obvious failure cases. If category precision is weak, change the system before processing thousands of images.

## 5. Inspect locally

After metadata has reduced the corpus, inspect local previews for technical availability, broad visible context, duplicate structure, and safety indicators. Verify that every expected preview decodes. Cluster exact, burst, and perceptual near-duplicates before quota selection. Keep raw OCR ephemeral. Never upload private pixels or metadata without explicit authorization.

## 6. Quarantine, do not erase

Potential identity documents, private correspondence, contact details, financial records, medical information, credentials, and other sensitive material belong in HOLD. Human-sensitive material may enter `needs-human-review`. Neither state can enter the master unless the configuration explicitly recognizes a later human clearance state. A hold is not deletion or a declaration about a person.

## 7. Select with uncertainty

Balance high-confidence evidence, stratified diversity, and exploratory retrieval. Preserve `candidate_views` as retrieval hypotheses and record the reviewed decision separately as `assigned_view`. Preserve `Unclassified / Editor Field`. A useful corpus does not need every image to support a named project claim.

Configured view quotas are exact. If a view lacks enough eligible assignments, report its structured deficit and widen retrieval or revise the brief explicitly. Do not pad it from another view. A direct HOLD propagates through connected duplicate and burst relations before selection.

People associations are first-class archive structure. Preserve named relationships already curated by the archive owner, but never identify unnamed faces or infer sensitive traits.

## 8. Evaluate and loop

Sample fresh low, middle, and high-scoring images from each view, plus regression canaries. Measure fresh sample completion, fresh decisive precision, uncertainty, sample sufficiency, master review fraction, and per-view results. Report canaries separately so known positives cannot improve fresh precision. Read the rejected examples. Revise retrieval, scoring, holds, or labels, then rerun with the same seed.

Declare an evaluation scope: `learning-sample`, `final-stratified-sample`, `full-master`, or `publication-shortlist`. A 60-image sample is never 100 percent master review.

## 9. Plan before writing

Produce proposed-master, hold, membership, and append-only decision manifests before touching the catalog. Every selected stable ID needs a reason. Freeze the final master after its last change and require a passing evaluation bound to its `master_sha256`, `sample_sha256`, and source fingerprint. The plan also binds the hold set and exact plan contents. The plan must be idempotent.

## 10. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify exact membership and rerun the test to prove idempotence. Only then create production folders and albums in moderate batches. Record every phase transition atomically so an interruption remains visible and recoverable.

Run state has a monotonically increasing revision and an append-only hash-linked event ledger. Multi-operator transitions should supply the observed revision; stale writers stop and reconcile. If a crash appends an event before replacing `run-state.json`, the next locked transition restores the recorded state before continuing.

## 11. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. Recompute source membership, verify the plan and receipt hash chain, and report missing, unexpected, outside-source, and hold-overlap counts. Preserve receipts, configuration, scripts, and evaluation feedback with the version.

## 12. Hand off honestly

Tell editors what the system did and did not do. `editor-field-verified`, `master-human-reviewed`, and `publication-ready` are separate release classes. The default result is a contact field for human editing, not the final visual narrative.
