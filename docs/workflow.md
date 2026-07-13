# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

## 1. Declare and freeze a source corpus

Give the broad retrieval corpus a versioned source profile, stable identifier, predicate,
and snapshot count. A named album and the visible whole library are different source
kinds. If the brief requests the whole library, use the whole-library adapter rather than
an earlier editor field. Never alter the source during a versioned run.

## 2. Build a compact inventory

Use the `minimal` or `retrieval` inventory profile unless private debugging requires more.
Capture stable IDs, filenames, albums, existing people associations, dates, coarse places,
favorite/edit status, duplicate and burst groups, and local availability. Exact coordinates
and source paths belong only in explicitly private debug artifacts.

## 3. Retrieve broadly with metadata

Use albums, people, keywords, dates, places, labels, and prior attention to create candidate
views. Record each contributing channel. Treat earlier editor fields as contextual evidence,
not as the search universe. Reserve a bounded discovery budget outside prior corpora, but
never evict stronger contextual evidence merely to satisfy an arbitrary novelty floor.

## 4. Calibrate before scaling

Inspect a small score-stratified sample from every proposed view. Record visible fit, rejection, uncertainty, and a brief reason. Include obvious failure cases. If category precision is weak, change the system before processing thousands of images.

## 5. Inspect locally

After metadata has reduced the corpus, inspect local previews for technical availability,
broad visible context, duplicate structure, and safety indicators. Decode every expected
preview before selection. Missing or corrupt pixels become `unavailable` and cannot enter
the master. Cluster local perceptual near-duplicates before quota selection. Keep raw OCR ephemeral.

## 6. Quarantine, do not erase

Potential identity documents, private correspondence, contact details, financial records, medical information, credentials, and other sensitive material belong in HOLD. A hold is not deletion. It is a protected review state that can never enter the master automatically.

## 7. Select with uncertainty

Keep `candidate_views` as immutable retrieval hypotheses. After pixel inspection, record a
separate `assigned_view`, assignment status, and visible or provenance-based reason. The
selector fails when that reviewed assignment is absent. Preserve `Unclassified / Editor Field`.

People associations are first-class archive structure. Preserve named relationships already curated by the archive owner, but never identify unnamed faces or infer sensitive traits.

## 8. Evaluate and loop

Sample low, middle, and high-scoring images from each view. Measure coverage, decisive
precision, and uncertainty both globally and per view. A strong aggregate cannot hide a
weak category. Generate a targeted follow-up round for failed views, read the rejected
examples, revise, and rerun with the same seed.

Validate feedback as a separate artifact before applying it. Targeted rounds diagnose weak
views; they do not replace the final audit.

## 9. Plan before writing

Freeze the final master after its last change. Fully audit every selected row, then bind the
passing evaluation to exact membership and assignments with `master_sha256` and `proposal_id`.
Plan generation fails on a targeted-only audit or any post-evaluation drift.

## 10. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify exact membership and
rerun the test to prove idempotence. Only then create production folders and albums in
moderate, resumable batches. Mark each phase with its supporting artifact hashes so an
interruption can be audited before work resumes.

## 11. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership.
For a live SQLite catalog, do not use immutable mode until after taking a WAL-aware bounded
snapshot. Report missing, unexpected, outside-source, and hold-overlap counts.

## 12. Hand off honestly

Tell editors what the system did and did not do. The result is a contact field for human editing, not the final visual narrative.
Label artifacts `private-operational`, `review-sensitive`, or `public-safe`. Run the
public-report linter before human publication review; its PASS is not publication approval.
