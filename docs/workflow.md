# Workflow

Photo Fieldwork treats a large archive reduction as a sequence of inspectable decisions.

## 0. State the boundary

Write down what may be read, what may be created, where outputs live, and which mutations are prohibited. Default catalog mutation is limited to creating albums and adding existing assets to them.

## 1. Freeze and fingerprint a source corpus

Give the broad retrieval corpus a stable source-profile ID, scope, count, and SHA-256 fingerprint of sorted UUID membership. Count alone cannot detect one removed asset and one added asset. Never alter the source during a versioned run. Preserve v00, v01, and later runs as separate folders so selection logic can be compared rather than overwritten.

Initialize `events.jsonl` before retrieval. Record each phase transition with a unique attempt ID and compare-and-swap revision checks. A completed phase requires an existing artifact and checksum; every later transition rechecks prior artifacts. Reconstruct `run-state.json` from the ledger after interruption.

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

## 7. Select with uncertainty and exact capacity

Balance high-confidence evidence, stratified diversity, and exploratory retrieval. Preserve `Unclassified / Editor Field`. A useful corpus does not need every image to support a named project claim.

People associations are first-class archive structure. Preserve named relationships already curated by the archive owner, but never identify unnamed faces or infer sensitive traits.

Rows may support several views. Assign the exact configured quotas with deterministic, capacity-aware matching. Keep secondary relevance. If the candidate field cannot satisfy a quota, stop with per-view capacity diagnostics rather than silently filling from another view.

## 8. Evaluate and loop

Sample low, middle, and high-scoring images from each view. Bind feedback to UUIDs and the sample-manifest hash. Measure coverage, decisive precision, fit rate, reject rate, and uncertainty rate separately overall and by view. Read the rejected examples. Revise retrieval, scoring, holds, or labels, then rerun with the same seed. A metric without inspected failure cases is not enough.

Before the final evaluation, audit holdout UUIDs plus perceptual, duplicate, and burst clusters against all tuning rounds and regression canaries. Keep raw overlap identifiers private by default.

## 9. Plan before writing

Produce proposed-master, hold, membership, and decision manifests before touching the catalog. Every selected stable ID needs a reason. Each album needs a key, role, visibility, parent-folder key, and exact asset identifiers. Bind the plan to the passing evaluation and the installed helper's bundle, binary digest, capabilities, and supported schema.

## 10. Commit narrowly

Write ten non-sensitive items to a uniquely named test album. Verify exact membership. Only then create production folders and albums in moderate, resumable batches. Run production twice with distinct launch nonces; copied receipts do not prove idempotence.

## 11. Verify independently

Use a read-only mechanism distinct from the writer to compare planned and actual membership. First verify each receipt against the exact plan bytes, authorized helper, source, and folder/album topology. Then report missing, unexpected, outside-source, and hold-overlap counts. Preserve both execution receipts, configuration, scripts, and evaluation feedback with the version.

## 12. Hand off honestly

Tell editors what the system did and did not do. The result is a contact field for human editing, not the final visual narrative. When a public projection is requested, create it separately through an allowlist with opaque IDs and explicit rights, consent, claim, and publication states. Catalog membership is never publication clearance.
