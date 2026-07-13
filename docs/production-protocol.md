# Production protocol

This protocol turns a curatorial brief into a resumable, auditable editor field while preserving human authority over taste, consent, and public meaning.

## Artifact chain

1. `brief.md` preserves editorial authority verbatim.
2. `source-profile.json` freezes source identity, count, predicate, and permissions.
3. `retrieval.json` defines view hypotheses and balanced candidate reserves.
4. `candidate-pool.csv` records retrieval traces and provisional assignments.
5. `inspection-ledger.jsonl` records policy-fingerprinted local inspection without raw OCR.
6. `safety-decisions.jsonl` records generalized relational safety decisions.
7. `proposed-master.csv` and `hold-sensitive.csv` remain disjoint.
8. `round-NN.csv` records visible judgments and error categories.
9. `decision-ledger.jsonl` and `replacement-review.csv` close the feedback loop.
10. `duplicate-review.csv` surfaces unresolved cross-UUID matches.
11. `catalog-plan.json` is linted, membership-only, and digest-sealed.
12. Writer receipts preserve exact catalog objects and counts.
13. Independent verification compares actual membership read-only.
14. `completion-report.md` is derived from the artifacts above.

## Quality boundary

A release is blocked by any of the following:

- source identifier, fingerprint, or count disagreement;
- missing or stale required inspection;
- raw OCR in a durable artifact;
- master and HOLD overlap;
- movie rows in a still-photo field;
- duplicate UUIDs or unresolved duplicate review;
- unmet exact target or view quota without a waiver;
- a failed material-view evaluation gate;
- a known safety regression;
- a pending cascading replacement review;
- an unlinted, unsealed, or modified catalog plan;
- write-test, idempotence, or independent-verification mismatch.

## Resumption

Use `photo-fieldwork state` to append evidence-backed phase transitions. Use the bridge `release-status` command to report the first incomplete phase. Completed phases cannot move backward. Repeating a catalog plan preserves the previous receipt and must reproduce stable folder identifiers, album identifiers, and counts.

## Privacy boundary

Pixels and metadata stay local. Raw OCR is ephemeral. Reports contain generalized safety reasons, coarsened context, and aggregate counts. Named People associations remain private archive structure. An editor-field album is not publication permission.
