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

## What the whole-library run exposed

A later 4,000-photo field began with a materially broader instruction: use the entire visible
Apple Photos library, not only the earlier 124,484-photo editor corpus. That use uncovered
several workflow risks which were easy to miss in a successful single run:

- the source corpus had been embedded as a machine-specific constant rather than declared;
- earlier generated editor albums could feed back into retrieval and amplify prior choices;
- a novelty percentage could displace stronger evidence if treated as a hard composition floor;
- exported-preview success had been trusted without independently decoding every file;
- immutable SQLite access could omit uncheckpointed WAL changes in a live catalog;
- aggregate evaluation could conceal a weak view;
- interruption recovery depended too much on operator memory.

Revision K turns those observations into contracts: versioned source manifests, explicit
retrieval channels and generated-album exclusions, bounded discovery, fail-closed preview
verification, WAL-aware compact verification, per-view gates, and hashed resumable state.
The transferable lesson is that operational success should be metabolized into reusable
failure checks before the next archive is larger or less familiar.
