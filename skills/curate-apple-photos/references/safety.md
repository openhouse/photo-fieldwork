# Safety and consent

Automated flags are conservative retrieval controls, not declarations about a person or document.

## Automatic HOLD

- identity documents;
- passwords, API keys, account or routing numbers;
- private contact details or exact home addresses;
- medical, therapy, legal-review, resident, guest, customer, donor, or subscriber records;
- private correspondence or coalition strategy;
- payment requests, invoices, and financial screens;
- hidden, trashed, missing, corrupt, or unavailable assets.

Store only generalized flags. Keep raw OCR ephemeral.

## Human-sensitive review

Use `needs-review` for minors, intimate domestic scenes, vulnerable people, private homes, grief, health context, protest risk, or images whose publication could change someone's safety or dignity. Do not automatically include these in an editor-facing master.

## Public meaning

Album membership is not publication permission. Project hypotheses are not factual captions. Named People metadata is private archive structure unless separately approved for release.

Keep these states distinct:

- `automatic-hold` or `hold`: excluded before ranking;
- `clear-automated`: local configured detectors found no HOLD trigger;
- `human-needs-review`: an editor must assess dignity, context, and risk;
- `human-cleared-for-editor-field`: eligible for private editorial review;
- `publication-review-required`: default for every selected item;
- `publication-approved` or `publication-denied`: explicit later decisions.

Automated clear never means publication approved. A later HOLD release must
preserve the original flag, reviewer, reason, and time.

## Mutation boundary

Permitted:

- local read-only inspection;
- private preview export;
- creation of new version folders and albums;
- addition of existing assets to those albums.

Prohibited:

- deletion or removal;
- metadata, date, location, face, favorite, or image edits;
- direct Photos database writes;
- cloud analysis or external upload;
- replacing or renaming prior versions.
