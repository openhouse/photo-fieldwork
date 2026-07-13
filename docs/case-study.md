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

## Whole-library production benchmark

A later production run began with 603,137 visible still photographs and created an exact 4,000-photo portfolio editor field. It freshly inspected 14,632 unique local assets across initial, delta, and targeted retrieval rounds. Five scored visual-evaluation rounds moved decisive precision from 0.2464 to 0.8831 at complete sample coverage.

That run exposed failures that now have protocol support:

- sequential view allocation lost candidates from later views;
- excluding prior editor albums removed useful retrieval indexes;
- individual classifiers missed safety meaning carried by relations;
- overall precision concealed weaker project views;
- feedback caused cascading replacements that needed inspection;
- an exact visible duplicate existed under a different asset UUID;
- multiple inspection rounds needed one logical preview and receipt index.

The release completed a ten-item write test, production write, idempotence rerun, and independent read-only membership verification. No pixels or metadata were uploaded. The aggregate benchmark is public-safe; private identities, OCR, locations, album titles, and imagery remain outside this case study.
