# Case study: whole-library fieldwork

A production run used the visible still-photo library as a frozen source field
of 603,137 assets. It freshly inspected 12,462 candidates locally, placed 424
in a disjoint automated safety HOLD, and produced an editor-ready field of
exactly 4,000 unique stills.

Five recursive visual rounds ended with 75 judgments across eleven views. The
overall decisive precision was 83.56%, while the lowest per-view result was
66.67%. That difference showed why one global metric was insufficient and led
to computed per-view gates in revision M.

The run also generated 25 run-local Python scripts totaling 3,894 lines. Those
scripts handled retrieval changes, constrained view balancing, round records,
diffs, and entrant audits. Revision M absorbs the reusable parts into explicit
retrieval, assignment, proposal, evaluation, state, and verification
contracts.

The production write passed a ten-item test, an idempotent rerun, and exact
independent verification. The verifier initially could not see the new albums
through an immutable connection because Photos still had committed state in
its WAL. Revision M therefore creates a consistent backup from a live
read-only, query-only connection before immutable verification.

No pixels, previews, OCR, faces, coordinates, or manifests left the machine.
The source, prior versions, originals, and Photos metadata were not changed.

The result remained an editor-ready field, not a final publication edit.
Album membership did not establish caption provenance, represented-person
review, rights, or publication permission.
