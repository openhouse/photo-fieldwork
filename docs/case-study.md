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

## Whole-library revision

A later v04-I run expanded the source to 603,137 visible still photographs. It retrieved and locally inspected 7,000 fresh candidates, produced an exact 4,000-photo editor field, kept 1,982 holds disjoint from the master, performed a ten-photo write test, reran the production write idempotently, and independently verified exact album membership with no missing, unexpected, or out-of-source assets.

The larger run exposed additional system failures that were not visible at the earlier scale:

- term-by-term wildcard retrieval became an operational bottleneck;
- candidate hypotheses could leak back into final view assignment;
- overall precision could pass while individual views remained weak;
- run-specific feedback scripts could lose required judgment fields;
- metadata duplicate groups missed near-identical and cross-format images;
- exact coordinates and machine paths needed structural redaction rather than policy alone;
- the final evaluated master needed a verifiable identity carried into write plans.

Revision I turns those observations into contracts: explicit assignments, per-view release gates, structured feedback, local perceptual clustering, privacy-aware source inventories, proposal hashes, hash-bound plans, typed reports, and atomic run-state transitions.
