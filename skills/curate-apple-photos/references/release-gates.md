# Release decisions and evidence closure

Use this order whenever an operator asks whether a run may resume, advance, write, complete, or publish. Evaluate the requested transition, not a vague global sense of progress.

## Dispositions

- `BLOCKED`: the requested transition has an unresolved blocker. Preserve completed evidence and perform only non-mutating diagnosis or repair until it closes.
- `READY_FOR_NEXT_PHASE`: the current correction is evidence-backed and may proceed, but completion has not been established. An unsupported optional view may be omitted or returned to unclassified without blocking otherwise feasible work.
- `EDITOR_FIELD_VERIFIED`: every editor-field release gate below is closed for one unchanged source, config, master, plan, write, and verification chain.

Track `editor_field_status` and `publication_status` independently. A verified private editor field can still have publication blocked or not assessed. If publication was not evaluated, say `not-assessed`, not `blocked` or `cleared`.

## Gate order

1. `run_integrity`: verify run state and every attached receipt. Filenames and phase labels are not evidence. A hash mismatch blocks resume.
2. `source_freshness`: match source identifier, immutable inventory hash, frozen count, and current live count. Preserve stale inventories; create a new immutable inventory rather than relabeling one.
3. `helper_capability`: verify the intended permissioned helper, source access, network policy, free space, and writer/verifier capabilities.
4. `preview_integrity`: exported must also mean present and decodable. Missing or corrupt previews are not visually reviewed and must be repaired, re-exported, or held.
5. `assignment_feasibility`: solve exact quotas and representation floors jointly. Report independent scarcity constraints; never invent view support or silently lower the approved config.
6. `hypothesis_resolution`: omit an unsupported optional project view or return uncertain material to unclassified with an anti-claim. Continue when the remaining field is feasible.
7. `final_evaluation`: every material view needs sufficient decisive evidence and must pass its own threshold. Freeze the master, then draw a final holdout untouched by tuning feedback. Keep a separate risk-stratified safety audit.
8. `replacement_audit`: review every final entrant absent from prior evaluation; apply active item/view decisions and duplicate/burst cluster holds before validation.
9. `validation_binding`: validation, evaluation, master, HOLD, source, config, and proposal hashes must describe the same unchanged candidate.
10. `test_write`: seal the membership-only plan, run a small non-sensitive write, verify it independently, and prove an idempotent rerun.
11. `production_verification`: bind writer receipt and independent read-only verification to the sealed production plan; require zero missing, unexpected, outside-source, and HOLD-overlap items.
12. `completion`: register and reverify the completed version. Do not invent a new blocker when every editor-field gate is evidenced and consistent.

Any candidate-affecting change invalidates downstream evaluation, validation, plans, and write receipts. Recompute them against the changed candidate.

## Evidence closure

For each finding, name:

- a stable finding code;
- the artifact IDs or paths that establish it;
- the requested transition it blocks or enables;
- the smallest safe next action;
- whether that action mutates Photos.

In structured output, use the canonical gate name and finding code exactly. Do not append asset IDs or explanatory suffixes to codes; put item-specific detail in evidence references and the required action. This keeps summaries comparable across rounds and tools.

Claims of success must cite the whole relevant chain, not only its final receipt. Contradictory evidence is a blocker until reconciled. Distinguish `not recovered in this run` from `does not exist`.

Use these canonical codes in structured reports while accepting clearly equivalent historical wording:

- source: `SOURCE_COUNT_MISMATCH`, `FRESH_INVENTORY_REQUIRED`;
- evaluation: `VIEW_GATE_FAILED`, `HOLDOUT_CONTAMINATED`;
- previews: `PREVIEW_MISSING`, `PREVIEW_CORRUPT`, `NOT_VISUALLY_REVIEWED`;
- final closure: `UNEVALUATED_FINAL_ENTRANT`, `REJECTED_VIEW_REENTRY`, `HELD_CLUSTER_IN_MASTER`;
- resume: `RECEIPT_HASH_MISMATCH`, `RUN_STATE_UNVERIFIED`;
- assignment: `VIEW_QUOTA_SCARCITY`, `DIVERSITY_FLOOR_SCARCITY`;
- unsupported view: `UNSUPPORTED_PROJECT_VIEW`, `NOT_RECOVERED_ANTI_CLAIM`;
- completion: `EDITOR_FIELD_VERIFICATION_SUPPORTED`, `PUBLICATION_SEPARATE`.

## Publication boundary

Editor-field membership is never rights, consent, caption provenance, credit, accessibility completion, sensitive-context review, or destination approval. Use `EDITOR_FIELD_NOT_PUBLICATION_PERMISSION` and `PUBLICATION_CLEARANCE_INCOMPLETE` when those facts are missing.

Scope the disposition to the user's requested transition. If the user asks to publish a set and any member lacks destination clearance, the publication request is `BLOCKED` even though `editor_field_status` remains `verified` and some individual rows may be clear. Do not silently narrow the requested set.

A public handoff is an allowlisted projection, not a copy of the private run. Use `PRIVATE_FIELD_REDACTION_REQUIRED` and exclude archive UUIDs, People associations, albums, local paths, raw OCR, exact locations, HOLD membership, and private safety reasons. Clearance is item-specific and destination-specific.
