# Case studies: how looking changed the system

## Wide corpus: 124,484 to 8,000

This project emerged from a versioned reduction of a 124,484-photo source corpus into an 8,000-photo working field for professional editors.

The first approach relied heavily on Apple Photos metadata, people associations, dates, places, labels, favorites, edits, and project retrieval dictionaries. That produced plausible categories, but plausibility was not enough.

A 36-image calibration sample was opened and visually inspected across the proposed views. Only 10 visibly supported the category that metadata had assigned. The problem was structural: retrieval-album membership had been mistaken for visible project evidence.

The workflow changed in response:

- project views were relabeled as editor hypotheses;
- an unclassified editor field was introduced;
- visible people-plus-apparatus became distinct from generic social context;
- potential sensitive material was quarantined;
- score-stratified visual audits were repeated after revisions;
- every selected image received a reason;
- catalog writing waited until validation passed;
- an independent read-only verifier compared the final plan with Apple Photos.

The completed version contained exactly 8,000 unique stills. It preserved the source corpus, created separate versioned albums, quarantined 3,394 candidates, and produced zero missing, unexpected, outside-source, or hold-overlap memberships in final verification.

The transferable lesson is simple: metadata is excellent for constructing a field of attention. It is not a substitute for looking, provenance, or editorial judgment. A good workflow makes those differences operational.

## Whole library: 603,137 to 4,000

A later portfolio run began from every visible, non-hidden, non-trashed still in
one Apple Photos library: 603,137 assets. It retrieved 7,000 candidates, required
4,200 of them to fall outside the earlier 124,484-photo corpus, and inspected all
7,000 previews locally with network access disabled.

The first two visual rounds failed. Observed decisive fit rose from 0.34 to
0.5273, then to 0.8136 and 0.8246 after retrieval, assignment, historical hold,
consent, and event-concentration rules changed. The final editor field contained
4,000 unique stills and a disjoint private HOLD of 1,075.

One requested project view, WOWList, received no dedicated production album.
Metadata retrieved plausible candidates, but none of the inspected photographs
met the threshold for a direct project-specific visual claim. The empty slot was
reported as a retrieval gap, not evidence that no photograph exists and not an
invitation to substitute generic atmosphere.

The PhotoKit writer later encountered a macOS TCC state mismatch: System Settings
displayed access while the launched helper process reported an unusable status.
The same frozen membership plan was rendered through a fail-closed AppleScript
adapter. A ten-item write test passed, production was run twice to test
idempotence, and a separate immutable SQLite verifier confirmed 16 albums and
11,425 planned memberships with zero missing, unexpected, outside-source, or
HOLD-overlap rows. The source count remained 603,137.

### Evaluation correction

The run's final 71/71 report combined 47 surviving tuning examples with 24
hand-inspected replacements. It demonstrated that known failures had been
removed and replacements had been checked. It did not constitute an untouched
estimate of the entire 4,000-photo field.

Version 0.2 therefore distinguishes working-round diagnostics from a final
holdout, renames `coverage` to review completion, reports view sampling coverage
and field audit rate separately, and includes a 95% Wilson interval. For 71/71,
the interval's lower bound is about 0.949, not 1.0.

### Reproducibility correction

The original intent config retained a positive WOWList quota even though the
final field deliberately contained no WOWList view. A fresh replay correctly
failed that mismatch. Version 0.2 preserves both intent and an effective final
config derived from the frozen master, including explicit unsupported or empty
views, then locks the artifacts by hash.

The transferable lesson is that successful catalog verification and successful
editorial evaluation are different achievements. Both need honest, replayable
evidence.
