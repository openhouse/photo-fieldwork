# Case study: how looking changed the system

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

## v04-G: whole-library fieldwork

The next production run widened the source from a pre-existing album to 603,137 visible, non-hidden, non-trashed still photographs. It required a fresh read-only inventory, multi-batch preview inspection, five substantial visual rounds, and overlap-aware assignment for an exact 4,000-photo editor field.

Decisive precision improved from 0.1282 in the first inspected round to 0.8000 in the final round. The committed version contained 4,000 unique master IDs, 1,752 protected HOLD IDs, and two explicit uncertainties. A ten-item write test preceded production; an idempotent rerun and independent immutable SQLite verification found zero missing, unexpected, outside-source, or HOLD-overlap memberships.

That run exposed the next architectural need: relevance belongs between an image and a view. The same photograph can fail one project hypothesis while remaining valuable elsewhere. This revision turns that lesson into first-class evidence edges, exact constrained assignment, cumulative feedback, protected uncertainty, and content-hashed release state.
