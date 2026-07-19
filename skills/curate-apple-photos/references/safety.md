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

## Private derivative integrity

Create private run directories at mode `0700` and derivative files at mode
`0600`. Resolve canonical paths before use: symlinks and paths outside the run
workspace are derivative-quarantine and re-export failures, not evidence about
the underlying asset. Missing, corrupt, cross-shard duplicate, or EXIF-bearing
previews also enter derivative quarantine and re-export. A pixel-unavailable
asset enters HOLD. An over-permissioned derivative remains ineligible until its
mode is corrected and the file is reverified.

Only decoded, unique, metadata-stripped, canonically contained, correctly
permissioned previews may reach contact sheets or selection. Never persist raw
OCR or follow a symlink to recover a preview.

## Human-sensitive review

Use `needs-review` for minors, intimate domestic scenes, vulnerable people, private homes, grief, health context, protest risk, or images whose publication could change someone's safety or dignity. Do not automatically include these in an editor-facing master.

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
