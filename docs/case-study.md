# Case study: how looking changed a whole-library field

Photo Fieldwork was used to reduce a 603,137-item visible still-photo source into
a 4,000-photo editor field for a professional portfolio. The run remained local:
no pixels, OCR, faces, coordinates, or manifests were uploaded.

The first 7,000 candidates came from albums, existing People associations,
dates, places, labels, favorites, edits, filenames, and project retrieval
dictionaries. The first visual evaluation failed. Its decisive precision was
0.3542. Plausible metadata had again been mistaken for visible project evidence.

The system changed in response:

- 2,027 previously uninspected candidates were added rather than recycling the first field;
- visual fit and provenance predicates were tightened separately;
- automated and human-reviewed safety decisions were kept out of the master;
- project views with weak attribution lost quota instead of receiving filler;
- an unclassified editor field preserved material that did not support a project claim;
- one desired project view was omitted because no inspected candidate met the visible-evidence and provenance threshold.

Three recursive rounds produced decisive precision of 0.3542, 0.7869, and
0.8889. The final round judged all 77 sampled items, reached 1.0 coverage, and
kept every represented view at or above 0.6667 decisive precision.

The completed version contained exactly 4,000 unique stills and a disjoint
485-item safety HOLD. A ten-item write test passed before production. Sixteen
production albums and 10,898 planned memberships were then independently
verified with zero missing, unexpected, outside-source, or HOLD-overlap
memberships. An idempotence rerun resolved to the same catalog identifiers.

The most important output was a documented absence: the requested project view
that did not survive review. The run reported a retrieval gap rather than using
generic imagery as proof. Metadata constructed a field of attention; looking,
provenance, and human judgment determined what the field could responsibly say.
