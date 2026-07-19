# Turning a curatorial brief into a run

The brief is editorial authority. Preserve it verbatim in `brief.md`, then derive two machine-readable files.

## retrieval.json

```json
{
  "seed": 20260710,
  "candidate_multiplier": 1.75,
  "unclassified_view": "00",
  "excluded_album_terms": ["prior export", "contact sheet"],
  "prior_corpus_album_title": "",
  "minimum_outside_prior_fraction": 0.0,
  "people_floor": 0.35,
  "person_free_floor": 0.20,
  "views": [
    {
      "id": "01",
      "label": "People / Presence",
      "quota": 1200,
      "terms": ["meeting", "workshop"],
      "people": ["Jamie Burkart"],
      "albums": [],
      "places": [],
      "year_start": null,
      "year_end": null
    }
  ]
}
```

Terms should include literal project names, alternate spellings, visible objects, actions, rooms, interfaces, buildings, and public event language. Dates are supporting constraints and should not be used alone to retrieve imported film.

Use People names only when they already exist in Apple Photos or the brief names them as relevant. Do not infer identities.

## config.json

Follow `/Volumes/16TB_SSD/Sites/photo-fieldwork/schemas/config.schema.json`.

- Quotas must sum exactly to the requested target.
- Reserve 8-12% for `Unclassified / Editor Field` unless the brief gives a reason not to.
- Preserve both a named-people field and a meaningful person-free field.
- Project views should say `Editor Hypothesis` until validated.
- Default evaluation minimums: 0.80 precision and 0.90 coverage.
- Default per-view minimum: 0.65 decisive precision with at least 3 decisive judgments per view. Raise the count for large or high-risk views.
- Default selection floors: `minimum_named_people_fraction` 0.35 and `minimum_person_free_fraction` 0.20, adjusted when the brief genuinely calls for a different balance.
- Keep the random seed fixed for the run.

## Peer panel

The user may request admired peers. Use them as distinct lenses rather than a consensus costume:

- information architecture and labels;
- civic or service legibility;
- technical credibility and evaluation;
- consent and accessibility;
- visual rhythm, typography, or material culture;
- narrative compression and emotional truth;
- Jamie's own agency and voice.

Speaker comments should identify what is visibly observed, what is inferred, and what change follows. The role-play cannot create factual provenance that the archive does not contain.
