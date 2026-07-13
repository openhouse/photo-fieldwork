# Case study: v04-N whole-library field

`v04-N` tested Photo Fieldwork against 603,137 visible Apple Photos stills rather than the earlier 124,484-item wide album.

The run retrieved and locally inspected 16,000 candidates, produced an 8,000-image editor field, and placed 1,915 items in safety HOLD with zero master overlap. It completed a ten-item write test, an identical production rerun, and independent verification of 17 albums and 22,229 memberships. No pixels or manifests were uploaded.

## What failed usefully

The first preview corpus contained systematic decode failures. The run stopped and freshly exported the final 8,000 previews in bounded shards; all 8,000 then decoded. Preview verification is now a blocking gate rather than an optional diagnostic.

The first write-test plan used relative receipt and log paths. Photos membership was created, but the bridge could not find the expected receipt. Generated plans now use absolute paths constrained to the run workspace.

The live Photos database retained recent writes in its WAL. Opening the live database immutably did not expose that state. The verifier now uses a query-only live transaction to copy relevant committed rows into a compact snapshot, then opens the snapshot immutably. It never writes or checkpoints Photos.

Visual review removed misattributed project material, private domestic images, relationship-event photographs, screenshots, identifiable children requiring consent review, and other weak or sensitive frames. Project-specific albums remained editor hypotheses unless visible evidence and provenance supported stronger wording.

## Reading the final metric

The final sample contained 61 fit, 1 reject, and 9 uncertain judgments. `61 / (61 + 1)` is 98.39 percent decisive precision. It does not mean 98.39 percent of all 8,000 images were proven good. Fit among all judged examples was 85.92 percent, and uncertainty was 12.68 percent. Current reports name and display these measures separately.

The result remained an editor-ready discovery field, not a final publication edit. Album membership did not establish consent or a factual caption.
