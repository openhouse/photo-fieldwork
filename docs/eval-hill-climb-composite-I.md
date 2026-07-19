# Revision I composite hill climb

Date: 2026-07-19

## Method

Four synthetic holdouts were run with identical prompts against the
pre-composite Revision I skill and the evolving composite skill:

- hostile verification using copied PASS JSON, a timestamp-only rerun, and an
  unchecked root parent;
- a coherent positive control whose evidence authorizes only a ten-item write
  test;
- a later-round freshness ledger with excluded ordinary rows and a failed
  regression canary;
- a destination-scoped publication request with incomplete rights clearance.

Each run used a fresh ephemeral read-only agent. Outputs were graded manually,
one point per explicit expectation, from the final decision text rather than
the agent's confidence or intermediate tool use. Raw transcripts remained in
an untracked local evaluation workspace because they contain machine-operating
noise and are not needed to reproduce the public synthetic cases.

## Results

| Candidate | Score | Finding |
| --- | ---: | --- |
| Pre-composite Revision I | 8/17 | Good general caution, but missing launch-nonce governance, normalized sampling identity, complete publication gates, and explicit bounded approval. |
| Composite, first pass | 12/17 | Release-chain decisions improved; several required facts remained implicit. |
| Composite, decision checklist | 14/17 | Publication became fully auditable, but one run mislabeled the fixture-file digest as the sampling identity. |
| Composite, false-hash repair | 16/17 | The fake hash was refused; remediation still skipped deterministic sample creation. |
| Composite, final | 17/17 | Every holdout expectation was explicit, including the bounded proceed control and correct sample-then-evaluate sequence. |

## Changes driven by misses

1. Require decision reports to name the current gate, the action authorized,
   and the later approval still withheld.
2. Report fresh rows and regression canaries separately; bind their normalized
   ID sets through `sampling_history_sha256`.
3. Never substitute a fixture or source-file digest for the normalized sampling
   identity. When that identity is absent, run deterministic sampling first and
   pass the identical history into evaluation.
4. Treat publication status, destination, rights, consent, and claim status as
   independent gates, with private UUIDs replaced only in a separate salted,
   allowlisted derivative.
5. Preserve positive capability: a coherent candidate advances to the exact
   next gate instead of being rejected merely because later gates remain.

## Limits

This hill climb measures operational responses to synthetic text fixtures. It
does not prove visual judgment, Photos permissions, production execution,
rights, consent, caption accuracy, or publication approval. Those remain
separate evidence and human gates.
