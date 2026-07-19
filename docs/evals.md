# Evaluation system

Photo Fieldwork uses two complementary evaluation layers.

## Skill prompts

`evals/evals.json` contains realistic operator requests for qualitative with-skill and baseline review. The prompts cover whole-library freshness, interruption recovery, sensitive archives, weak-view evaluation, feedback identity, inspection shards, unsupported project claims, public handoff boundaries, candidate drift, holdout contamination, and decision-ledger tampering.

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

The July 19, 2026 Revision D and composite pass used public synthetic fixtures throughout:

| Iteration | Frontier | Result | Product response |
| --- | ---: | ---: | --- |
| Corrected baseline | depth 2, 91 variants | 54 pass / 37 fail | Preserved the failure frontier without changing thresholds. |
| Contract climb | depth 2, 91 variants | 91 pass | Added explicit safety, canonical identity, sample binding, checkpoint-chain, exact-shard, and public-handoff guards. |
| Recursive expansion | depth 3, 120 variants | 120 pass | Confirmed that the initial guards compose under compound mutations. |
| Identity expansion | exhaustive compatible frontier, 187 variants | 187 pass | Added view-label drift, fully stripped feedback binding, mixed local-ID representations, and shard source-count drift, then exhausted every compatible mutation combination. |
| Composite red baseline | exhaustive compatible frontier, 795 variants | 187 pass / 608 fail | Added decision-ledger integrity, holdout contamination, and candidate-bound release families before implementing their product APIs. |
| First composite implementation | exhaustive compatible frontier, 795 variants | 794 pass / 1 fail | Implemented hash-chained decisions, asset-and-cluster holdout audit, and recomputed release seals. One coordinated assignment/config drift still passed. |
| Assignment-binding repair | exhaustive compatible frontier, 795 variants | 795 pass | Bound exact view and safety assignments and required catalog view albums to equal the current master assignments. |
| Holdout-report expansion | exhaustive compatible frontier, 1,307 variants | 1,306 pass / 1 fail | Added report-coherence and forged-status checks. They exposed a neighboring error: a coherent FAIL report was validated as internally consistent but was not blocked from release. |
| Holdout-independence repair | exhaustive compatible frontier, 1,307 variants | 1,307 pass | Required valid report structure, PASS/leakage coherence, actual independence, and a tuning digest matching the released feedback set. |
| Cluster-alias expansion | exhaustive compatible frontier, 1,371 variants | 1,370 pass / 1 fail | After correcting a noncomposing mutation fixture, exposed the same duplicate cluster represented as `duplicate_group` in tuning and `duplicate_group_id` in holdout. |
| Cluster-normalization repair | exhaustive compatible frontier, 1,371 variants | 1,371 pass | Normalized duplicate-field aliases to one cluster namespace before contamination comparison. |
| Independent-review red frontier | exhaustive compatible frontier, 4,443 variants | 4,438 pass / 5 fail | Exposed tuning cluster drift after audit and a valid human publication-approval event entering an editor-field release. Compound failures preserved both missing rules. |
| Current-split and authority repair | exhaustive compatible frontier, 4,443 variants | 4,443 pass | Recomputed the split audit from current manifests, bound normalized structure digests, and rejected publication approval in the editor-field release class. |
| Symmetric split-drift expansion | exhaustive compatible frontier, 16,731 variants | 16,731 pass | Added tuning, final-holdout, and canary cluster drift to the candidate-bound family and exhausted all compatible combinations. |
| Final-review red frontier | exhaustive compatible frontier, 33,115 variants | 33,113 pass / 2 fail | An intact ledger from an unrelated run remained acceptable alone and when a prior tamper was replaced by a newly sealed unrelated event. A focused receipt regression also showed that missing completion and object identifiers were accepted. |
| Candidate-provenance expansion | exhaustive compatible frontier, 65,883 variants | 65,883 pass | Bound the ledger to the catalog plan run, froze and bound the pre-clearance safety baseline, required exact asset-specific human clearance transitions, and rejected structurally incomplete writer receipts. |

The initial oracle incorrectly treated quota infeasibility caused by an explicit HOLD as an eval failure. That oracle was corrected before product changes. Safe refusal is a pass condition; an evaluator must not reward the system for selecting held material merely to satisfy a quota.

A final reproducibility probe found that temporary workspace paths and a generated plan timestamp made otherwise identical reports differ byte for byte. The runner now normalizes ephemeral fixture data, and a regression test requires two complete executions to return identical report objects.

Independent review also produced focused regressions outside the combinatorial frontier: release-bound Apple Photos plans now use schema 3 so stale helpers fail before mutation, and `snapshot-plans` rejects any view field other than the sealed `primary_view` assignment.

The executable frontier is complete only for the finite mutation families currently declared in `system-evals.json`; 65,883/65,883 is not a claim of universal correctness. The three new qualitative prompts are committed as review instruments but were not scored by an external model during this implementation pass.
