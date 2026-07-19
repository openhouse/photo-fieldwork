# Curate Apple Photos evals

These cases test decisions that can make an apparently successful fieldwork run
unsafe, irreproducible, or epistemically misleading. They contain no private
images, identifiers, paths, People data, or live catalog operations.

## Coverage

| Eval | Contract under pressure |
| --- | --- |
| 1 | source drift and generated-album recursion |
| 2 | interrupted inspection and truthful resumed receipts |
| 3 | final-holdout identity through offline review |
| 4 | event caps during diversity-floor swaps |
| 5 | unsupported project claims and explicit reallocation |
| 6 | narrow human safety clearance versus publication permission |
| 7 | preview decode failure and local-only replacement |
| 8 | post-freeze drift, writer fallback, test writes, and verification |
| 9 | default-closed public projection |
| 10 | fresh recursive evaluation and uncertainty |
| 11 | overlap-aware exact quota assignment |
| 12 | same-count source-membership substitution |
| 13 | append-only recovery, artifact drift, and ordered phases |
| 14 | relational final-holdout leakage |
| 15 | release-candidate and registered-plan identity |
| 16 | fresh evaluation versus regression canaries |
| 17 | distinct production attempts and independent verification |
| 18 | eval-auditor positive controls and anti-shortcuts |
| 19 | valid bounded production PROCEED control |
| 20 | unbound auxiliary memberships and outcome-free receipts |
| 21 | legacy-ledger migration and append-only plan supersession |
| 22 | relation identity through offline review export |
| 23 | joint diversity-floor backtracking across views |
| 24 | stale nonce revocation after invalidation or supersession |
| 25 | duplicate catalog album-key ambiguity |
| 26 | identical adapter bytes for idempotence |
| 27 | exact dominance pruning and production-scale solver evidence |
| 28 | verified write-test evidence before production |
| 29 | semantic album roles when memberships are equal |
| 30 | relation identifiers in holdout sample identity |
| 31 | complete relation schema for prior feedback |
| 32 | single-buffer adapter validation and authorization |
| 33 | out-of-band runtime-plan authorization through writer and verifier |

## Hill-climb protocol

1. Snapshot the current skill before changing it.
2. Run every prompt against the snapshot and save one output per eval.
3. Grade each expectation as pass or fail with quoted output evidence. Do not
   award implied behavior that the output does not state.
4. Cluster failures by missing general contract, not by prompt wording.
5. Revise the skill and supporting implementation once per cluster.
6. Rerun the complete bank. A fix wins only when it improves aggregate pass rate
   without regressing a previously passing safety expectation.
7. Add a regression test for every implementation defect discovered by an eval.
8. Stop when a complete pass repeats or the remaining failure requires a real
   human, permission, or private-data decision that the skill should not fake.

Use the `skill-creator` grading schema for `grading.json` and benchmark output.
Real Photos mutation is prohibited during these evals.

See [hill-climb-report.md](hill-climb-report.md) for the aggregate recursive
evaluation record. Raw model outputs remain private and are not committed.
