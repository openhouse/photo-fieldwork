# Safety and consent

Automated flags are conservative retrieval controls, not declarations about a person or document.

## Automated states

- identity documents;
- passwords, API keys, account or routing numbers;
- private contact details or exact home addresses;
- medical, therapy, legal-review, resident, guest, customer, donor, or subscriber records;
- private correspondence or coalition strategy;
- payment requests, invoices, and financial screens;
- hidden, trashed, missing, corrupt, or unavailable assets.

These become `hold-automated`. A clean automated pass becomes `clear-automated`, which is eligible for an editor field but is never publication approval.

Store only generalized flags. Keep raw OCR ephemeral.

## Human-sensitive review

Use `needs-human-review` for minors, intimate domestic scenes, vulnerable people, private homes, grief, health context, protest risk, or images whose publication could change someone's safety or dignity. It is structurally ineligible until a person records `cleared-human` for the declared purpose or `hold-human`.

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
