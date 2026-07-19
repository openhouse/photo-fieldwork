# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

## 1. Freeze a source corpus

Give the broad retrieval corpus a stable name, count, and membership SHA-256. Never alter it during a versioned run. A count alone cannot detect equal-count substitutions. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten.

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

Sample low, middle, and high-scoring images from each view. Measure coverage and precision with denominators and small-sample warnings. Keep category fit, safety, public suitability, and provenance separate. Read the rejected examples, apply them as hard negatives, revise retrieval, scoring, holds, or labels, then rerun with the same seed. A metric without inspected failure cases is not enough.

## 9. Record decisions and reserve a holdout

Freeze the post-inspection, pre-clearance safety manifest before changing any safety state. Store material evaluation, editorial, safety, and publication-review decisions as hash-chained events whose `run_id` equals the catalog plan `plan_id`. A ledger preserves who decided what, under which authority, and why; it does not turn automation into an editor. A safety clearance must identify the exact asset and transition from its frozen baseline state to `clear`. Safety clearance and publication approval remain human-only events.

Keep a final holdout outside tuning samples and regression canaries. Audit both canonical UUID overlap and shared duplicate, perceptual, or burst clusters. Report only counts and digests so the audit artifact is safe to inspect without exposing private identifiers.

## 10. Plan and seal before writing

Produce proposed-master, hold, membership, and decision manifests before touching the catalog. Every selected stable ID needs a reason. Bind the plan to source, master membership, exact view and safety assignments, and per-album membership digests. The plan must be idempotent.

Recompute evaluation and validation from the candidate inputs. Verify the run-bound decision chain, reconcile human safety clearances against the frozen pre-clearance baseline, recompute the holdout audit, and verify the catalog plan before creating a deterministic editor-field release seal. The seal identifies exactly what passed. It is not a cryptographic signature, a rights clearance, or publication approval.

## 11. Commit narrowly

Generate Apple Photos plans only from the still-matching config, catalog plan, master, HOLD, source snapshot, and release seal. Write ten non-sensitive items to a uniquely named test album. Verify exact membership and rerun the test to prove idempotence. Only then create production folders and albums in moderate, resumable batches.

## 12. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. Recompute source and destination digests. Require the plan, writer receipt, supplied release seal, and verifier receipt to agree on the release candidate, release seal, catalog plan, and master-assignment digests. Report missing, unexpected, outside-source, and hold-overlap counts. Preserve receipts, configuration, scripts, decision history, and evaluation feedback with the version.

## 13. Hand off honestly

Tell editors what the system did and did not do. The result is a contact field for human editing, not the final visual narrative.

## 14. Checkpoint and project carefully

Checkpoint every completed phase with artifact digests so the run can resume without trusting ambient state. Keep the private editor handoff separate from any public-safe visual corroboration note. Neither one makes an image publication-approved by default.

Revision D checkpoints store a workspace-relative path, byte size, and SHA-256 for every artifact, and revalidate the complete prior chain before advancing. Run-state schema 3 adds a required `release_audit` phase before `write_test`. Older states and receipts cannot satisfy the strengthened chain implicitly and therefore fail closed. Start a new run, or migrate only after independently locating and verifying every recorded artifact; never infer a legacy artifact from its filename alone.
