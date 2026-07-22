# Private studio contract

Use the studio for exploratory looking before or between formal evaluation
rounds. It is a private light table, not an evaluation report, safety decision,
or publication queue.

## Inputs

The studio requires:

- a bounded field CSV with unique stable asset identifiers;
- a complete verified-preview index for that exact field;
- the private preview root used by the index;
- optionally, the exact matching private metadata JSONL produced by
  `export_private_metadata.py`.

The metadata input must match the field exactly. The studio shows an allowlist
of useful private context, including existing People, albums, dates, titles,
descriptions, keywords, places, camera details, and relationship clues. It
does not embed local source paths, original filenames, database primary keys,
or precise latitude and longitude.

## Outputs

`photo-fieldwork studio` writes one mode-0600 offline HTML file and copied
mode-0600, content-addressed review previews. Its browser-local state supports:

- three contact-sheet densities and a contained full-frame view;
- adjacent-frame navigation and side-by-side pinning;
- deterministic chance walks from the declared seed;
- provisional `Gather`, `Uncertain`, `HOLD`, and `Return later` states;
- semicolon-separated temporary piles;
- separate observation, association, question, and claim-candidate notes;
- an encounter trail recording first-seen order, visits, and the latest
  surface path;
- a private JSON notebook export.

The notebook declares `purpose: private-exploration`,
`evaluation_state: not-evaluation`, and
`publication_state: review-required`. Partial notes are valid. A resident may
stop, wander, or leave most images unclassified.

## Boundaries

- Use only verified local previews. Do not upload images, context, or notes.
- Do not load pre-existing safety holds into the studio. A resident may place
  a viewed image on studio HOLD, but only an authorized human can clear it.
- Do not treat studio states or notes as fit/reject judgments, visible factual
  provenance, rights clearance, consent, or publication approval.
- Regenerating the same exact field and preview evidence yields the same studio
  identity and browser storage key. Changed membership or preview bytes create
  a different studio.
- Photos writes still require a separately reviewed membership-only plan,
  app receipt, idempotence evidence, and independent catalog verification.

## Example

```bash
photo-fieldwork studio \
  --field RUN/manifests/encounter-01.csv \
  --preview-index RUN/manifests/verified-preview-index.csv \
  --preview-root RUN/previews/encounter-01 \
  --metadata RUN/manifests/private-candidate-metadata.jsonl \
  --title "Residency 001 / Workspace A" \
  --seed 20260722 \
  --output RUN/studio/index.html
```
