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
