# Operator runbook

This is the production path. Complete the synthetic practice run first.

## 1. Establish the boundary

- Use a populated local machine profile outside Git.
- Keep the run workspace on a local, private, non-File-Provider volume.
- Confirm pixels, OCR, faces, coordinates, and manifests may not leave the machine.
- Confirm allowed Photos mutations are folder creation, album creation, and addition of existing membership only.

## 2. Reserve the run

Use `photo-fieldwork run init`. One semantic version may have one authoritative run. Failed evaluation rounds remain inside that workspace.

## 3. Preflight

Run profile check, bridge doctor, and the operational Photos probe. Confirm live source count, inventory freshness, helper capability version, free storage, and network-disabled plans. Record the reports as the `preflight` receipt.

## 4. Retrieve and inspect

Save retrieval diagnostics. Verify preview decoding before contact-sheet review. If using the cache, report newly decoded and verified-cache-hit counts separately. A missing or corrupt preview fails closed.

## 5. Review recursively

Inspect every view at low, middle, and high scores. Read all rejections. Persist known rejects and historical holds. Keep evaluation rounds separate. Do not lower thresholds to finish.

## 6. Freeze and validate

Mark post-pass replacements. Audit the actual frozen field and every replacement. Run validation with the final evaluation report and feedback. Freeze the validated master, HOLD, config, feedback, and plans by checksum.

## 7. Write and verify

1. Run the ten-item plan.
2. Extract compact WAL-aware evidence and verify exact test membership.
3. Run the production plan.
4. Rerun production and require the same identifiers and counts.
5. Extract new compact evidence and verify every album exactly.
6. Confirm zero missing, unexpected, outside-source, or HOLD-overlap memberships.

Select a reviewed PhotoKit or AppleScript adapter before writing. Do not improvise a new mutation path mid-run.

## 8. Close the run

Record independent verification as passing. Generate the completion report from receipts. Run the cleanup report to identify storage that may be removed later. Preserve manifests, evaluations, plans, receipts, checksums, final reports, and every prior Photos version.

The run is editor-ready, not publication-ready. Rights, consent, caption accuracy, attribution, and contextual dignity remain separate editorial work.
