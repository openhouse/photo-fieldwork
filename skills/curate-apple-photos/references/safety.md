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

Preview-export receipts are not sufficient proof that pixels are usable. Decode every
expected preview. Missing and corrupt previews are `unavailable` and fail closed.

Store only generalized flags. Keep raw OCR ephemeral.

Label run artifacts as `private-operational`, `review-sensitive`, or `public-safe`. Run
`lint_public_report.py` before human publication review. A machine PASS is only a leak check,
not consent or publication approval.

## Human-sensitive review

Use `hold-human-sensitive` for possible minors, intimate domestic scenes, vulnerable people,
private homes, grief, health context, protest risk, or images whose publication could change
someone's safety or dignity. Machine labels trigger review; they do not establish age,
identity, or publication risk as fact. Do not automatically include these items in an
editor-facing master.

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
