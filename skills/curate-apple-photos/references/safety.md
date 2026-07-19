# Safety and consent

Automated flags are conservative retrieval controls, not declarations about a person or document.

## Safety states

- `clear_automated`: no automated hold signal; not a public-clearance decision.
- `hold_automated`: automatically quarantined before ranking.
- `review_sensitive`: requires protected human review and cannot enter the general master.
- `cleared_editor_private`: human-cleared for the private editor field only.
- `cleared_public_candidate`: human-cleared as a candidate for a later public edit.
- `restricted_private`: retained privately and excluded from general editor and public-candidate fields.

Automated logic may move an item toward greater restriction. Only a human editor may grant either clearance state. Editorial relevance and safety state are separate judgments.

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

Use `review_sensitive` for minors, intimate domestic scenes, vulnerable people, private homes, grief, health context, protest risk, or images whose publication could change someone's safety or dignity. Do not automatically include these in an editor-facing master.

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
