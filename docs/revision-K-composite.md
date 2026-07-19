# Revision K composite

This update composes selected contracts from the refreshed `feature/revision-*` family into
Revision K. It is a deliberate implementation, not a mechanical branch merge. The parallel
branches remain independent design evidence.

## Composition decisions

| Family strength | Composite decision |
| --- | --- |
| A and B: release identity and evidence-chain integrity | Add one release seal that binds the source, config, exact master assignments, full evaluation, validation, and plan by content digest. |
| C and E: durable human decisions | Add an append-only, hash-chained JSONL decision ledger with explicit supersession and deterministic materialization. |
| D and N: exact assignment and actionable scarcity | Make K's exclusive reviewed assignments satisfy every view quota exactly; fail with per-view capacity and deficit instead of silent rebalancing. |
| G and I: image-view evidence and editorial assignment | Retain K's distinction between retrieval hypotheses and reviewed assignments, now backed by decision lineage. |
| E and L: editor field versus publication | Add destination-specific publication review that keeps rights, consent, claims, context, and approval separate and default closed. |
| M: hostile receipt and verification checks | Bind each launch to a fresh nonce and reviewed plan digest; reject receipts whose execution, candidate, source, safety mode, albums, or counts do not match; record plan and receipt digests in independent verification. |
| K: evaluation honesty | Preserve saturated baseline results, distinguish structural from executable evidence, and include a proceed-oriented positive control. |

## Why this is coherent

Revision K assigns each eligible photograph to one reviewed view before selection. A general
overlap solver would introduce a second editorial-assignment model, so the composite instead
makes the existing exclusive model exact and diagnostic. Diversity-floor substitutions occur
only within the same view. If the frozen constraints cannot coexist, the selector reports the
conflict and stops.

The decision ledger records human judgment before candidate construction. The release seal
then binds the resulting candidate and its evidence before any write. Independent verification
tests what reached the catalog. Publication review begins only after that private editor-field
lifecycle and cannot be granted by the seal.

```text
retrieval hypotheses
        |
        v
append-only human decision ledger
        |
        v
materialized reviewed assignments + related-frame holds
        |
        v
exact-quota selection -> holdout -> full-master audit -> validation
        |
        v
candidate-bound release seal
        |
        v
bounded write test -> matching receipt -> independent verification
        |
        v
explicit production approval -> production write -> independent verification
        |
        v
separate destination-specific publication review
```

## Deliberate boundaries

- The release seal authorizes a bounded write test, not production, completion, or publication.
- A test receipt is not sufficient without independent read-only verification.
- A publication review may deny public use without removing an image from the private field.
- The ledger stores bounded reasons and state, not raw OCR or private visual descriptions.
- The standard-library core remains independent of Apple Photos and image libraries.
- This update does not add a cloud service, automatic taste model, direct Photos database write,
  face identification, or automated publication authority.

## Evaluation

The public bank now contains 18 synthetic scenarios and 72 explicit expectations. Fourteen
executable canaries bind the highest-risk scenarios to exact selection, decision lineage,
release sealing, publication review, receipt identity, and holdout leakage behavior. See
`docs/eval-hill-climb-K-composite.md` for the paired recursive comparison and repair record.
