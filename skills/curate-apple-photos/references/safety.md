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

Propagate HOLD through exact duplicate, perceptual-match, and burst relations before ranking. A crop, edit, or neighboring burst frame cannot be cleared merely because its own detector result is empty.

## Human-sensitive review

Use `needs-review` for minors, intimate domestic scenes, vulnerable people, private homes, grief, health context, protest risk, or images whose publication could change someone's safety or dignity. Do not automatically include these in an editor-facing master.

A false-positive clearance applies to one asset only after its known relations have been reviewed. Record an identified human reviewer, timestamp, and generalized reason. Do not weaken the detector or reinterpret that decision as publication permission. HOLD remains protected for the run.

## Public meaning

Album membership is not publication permission. Project hypotheses are not factual captions. Named People metadata is private archive structure unless separately approved for release.

Role-play and expert lenses are editorial counsel. They do not create eyewitness evidence, rights, consent, collaborator approval, or publication authority.

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
