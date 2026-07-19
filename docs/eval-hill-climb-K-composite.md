# Revision K composite eval hill climb

The composite was evaluated without Apple Photos access, private images, or catalog mutation.
The pre-composite Revision K skill was frozen before editing and used as the baseline. Candidate
and baseline received identical prompts under the same `gpt-5.6-sol` model, read-only sandbox,
and tool boundary.

## Public bank and executable layer

- 18 synthetic adversarial scenarios
- 72 explicit response expectations
- 1 proceed-oriented positive control
- 14 deterministic executable contracts
- 50 full-suite unit tests after implementation

`make evals` validates prompt coverage and runs executable canaries for holdout leakage, exact
quotas, decision-ledger integrity, related-frame holds, release seals, publication boundaries,
and receipt identity. Structural and executable results are reported separately.

## Paired behavioral climb

Expectations were graded conservatively from explicit response evidence. Generic caution did not
earn credit for naming an executable mechanism or complete identity chain.

| Round | Cases | Composite | Frozen K baseline | Finding |
| --- | ---: | ---: | ---: | --- |
| 1: initial discriminators | 4 / 16 expectations | 15 / 16 | 11 / 16 | Quota scarcity and the green control saturated. The composite distinguished decision supersession and release identity, but failed to explicitly preserve a failing audit of the existing drifted seal. |
| 2: adversarial expansion | 3 / 12 expectations | 12 / 12 | 11 / 12 | Copied-receipt identity distinguished the composite. Related-frame safety and the green control remained saturated canaries. |
| 3: targeted repair | 2 / 8 expectations | 8 / 8 | 5 / 8 | The repaired skill now audits and preserves the old failing seal before rebuilding; the unchanged positive control still proceeded to the bounded write test. |
| 4: execution binding | 2 / 8 expectations | 8 / 8 | 7 / 8 | The copied-receipt contract now requires a bridge launch nonce and reviewed plan digest; the green control remained intact. |

The round-three composite response explicitly required: audit the existing seal, preserve its
failing report, create a new candidate, rerun evaluation and validation, regenerate the plan,
and create a new seal. The baseline correctly blocked the write but did not preserve a failing
seal audit or require a replacement seal.

Round four promoted fresh-execution proof from prose into the helper protocol. The bridge creates
a fresh nonce and binds the reviewed plan digest to a private launch plan. A compatible helper
must echo both in its receipt, and independent verification checks the reviewed plan digest.

## Product defects closed

The recursive process produced executable product changes rather than prompt-only language:

1. Selection now fails with exact per-view scarcity diagnostics and cannot break quotas while
   satisfying global diversity floors.
2. Human assignments, evaluations, and safety decisions now have append-only, hash-chained
   lineage with explicit supersession and related-frame hold propagation.
3. One release seal now binds source membership, config, exact master assignments, full audit,
   validation, and plan content; artifact drift fails its audit.
4. Helper receipts are rejected when plan, candidate, source, safety mode, album, or count
   identity differs, even when timestamps and headline counts look plausible.
5. Publication review remains destination-specific and default closed after editor-field release.

## Limits

These are single paired runs, not a variance estimate. The natural-language scores measure
release reasoning under synthetic scenarios, not visual taste, live PhotoKit compatibility,
human safety judgment, rights, consent, or publication suitability. Raw model transcripts remain
in a private temporary workspace; only this aggregate method and result are public.
