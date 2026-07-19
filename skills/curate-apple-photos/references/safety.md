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

Automated detection writes `auto-hold`; missing local inspection writes
`unavailable`; corrupt previews write `corrupt`. These are retrieval controls,
not declarations about a person.

## Human-sensitive review

Use `needs-human-review` for minors, intimate domestic scenes, vulnerable people, private homes, grief, health context, protest risk, or images whose publication could change someone's safety or dignity. Do not automatically include these in an editor-facing master.

Apply human decisions with `apply_safety_review.py`. Human review may write
`needs-human-review`, `human-added-hold`, `confirmed-sensitive`, or
`cleared-false-positive`. Every decision requires a generalized reason, actor,
and timestamp. Clearing one false positive must not weaken a detector globally.

## Public meaning

Album membership is not publication permission. Project hypotheses are not factual captions. Named People metadata is private archive structure unless separately approved for release.

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
