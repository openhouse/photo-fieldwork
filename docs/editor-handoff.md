# Editor handoff

An editor-ready field is the beginning of visual editing, not its conclusion. Preserve the broad field and add reversible downstream decisions.

## Field ladder

1. **Discovery field:** broad material and explicit uncertainty.
2. **Review packets:** 100 to 250 images organized around one editorial question.
3. **Project shortlists:** images with provenance and consent tasks visible.
4. **Narrative sequences:** small arrangements for a specific page or audience.
5. **Publication candidates:** separately reviewed for factual caption, dignity, and consent.
6. **Public derivatives:** redacted files with independent rights, consent, claim, safety, and publication approvals projected through an allowlisted manifest.

## Meaning stays plural

Keep three axes distinct:

- `retrieval_hypotheses`: why metadata surfaced an image;
- `visible_descriptions`: what a reviewer can see;
- `verified_contexts`: project or event relationships supported by provenance.

`primary_view` is a presentation choice for a packet. It is not the photograph's singular truth.

## Useful uncertainty queues

- needs project provenance;
- needs consent review;
- needs closer visual inspection;
- relationship or atmosphere, not professional proof;
- material context with no current story;
- possible misattribution;
- possible duplicate or weak frame.

Every handoff should lead with the next decision an editor can make, followed by counts, identifiers, and audit evidence.

## Public handoff

Do not convert a master manifest into website data. Prepare a separate derivative-review CSV and run:

```bash
photo-fieldwork public-handoff \
  --input private/public-derivative-review.csv \
  --output public/public-handoff.json \
  --report private/public-handoff-report.json
```

Unresolved records remain excluded. A fully cleared record proceeds, which keeps the gate from becoming a refusal-only policy. The command copies allowlisted fields into a new manifest and leaves private evidence unchanged.
