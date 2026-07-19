# Evaluation system

Photo Fieldwork uses two complementary evaluation layers.

## Skill prompts

`evals/evals.json` contains realistic operator requests for qualitative with-skill and baseline review. The prompts cover whole-library freshness, interruption recovery, sensitive archives, weak-view evaluation, feedback identity, inspection shards, unsupported project claims, and public handoff boundaries.

These prompts evaluate whether the skill guides an operator toward the right sequence and distinctions. They do not establish that the underlying implementation enforces those contracts.

## Executable system evals

`evals/system-evals.json` defines the highest-consequence implementation contracts. `scripts/run_evals.py` executes them against synthetic records only.

Each root case represents a valid operation. Deterministic mutations then alter order, identifiers, membership, safety state, receipts, checkpoints, or public text. The runner recursively evaluates mutation combinations up to the configured depth. A safe system must continue accepting harmless transformations and reject every unsafe mutation before state or catalog output is trusted.

```bash
make evals
```

Reports are written under `build/evals/` and are not committed. A nonempty failure frontier exits nonzero.
Reports normalize ephemeral workspaces and time-varying fixture data so identical code and inputs produce byte-identical JSON.

## Recursive hill climb

1. Run depth zero to confirm valid roots remain usable.
2. Run depth one to expose single-point failures.
3. Fix the product contract, not the fixture.
4. Run depth two to expose interactions between individually understood failures.
5. Promote every newly discovered failure into the persistent mutation bank or a focused regression test.
6. When the finite mutation bank is tractable, exhaust every compatible combination rather than stopping at an arbitrary depth.
7. Stop only when the complete frontier passes without lowering thresholds or converting a reject expectation into a waiver.

The mutation bank is intentionally synthetic and public-safe. Production photographs, identifiers, manifests, OCR, People associations, and local paths never belong in repository eval fixtures.

## Revision D hill climb

The July 19, 2026 Revision D pass used the same public synthetic fixtures throughout:

| Iteration | Frontier | Result | Product response |
| --- | ---: | ---: | --- |
| Corrected baseline | depth 2, 91 variants | 54 pass / 37 fail | Preserved the failure frontier without changing thresholds. |
| Contract climb | depth 2, 91 variants | 91 pass | Added explicit safety, canonical identity, sample binding, checkpoint-chain, exact-shard, and public-handoff guards. |
| Recursive expansion | depth 3, 120 variants | 120 pass | Confirmed that the initial guards compose under compound mutations. |
| Identity expansion | exhaustive compatible frontier, 187 variants | 187 pass | Added view-label drift, fully stripped feedback binding, mixed local-ID representations, and shard source-count drift, then exhausted every compatible mutation combination. |

The initial oracle incorrectly treated quota infeasibility caused by an explicit HOLD as an eval failure. That oracle was corrected before product changes. Safe refusal is a pass condition; an evaluator must not reward the system for selecting held material merely to satisfy a quota.

A final reproducibility probe found that temporary workspace paths and a generated plan timestamp made otherwise identical reports differ byte for byte. The runner now normalizes ephemeral fixture data, and a regression test requires two complete executions to return identical report objects.
