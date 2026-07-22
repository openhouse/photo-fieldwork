# Permissioned helper authorization

The Apple Photos helper has four separate evidence layers. Keep them separate:

1. **Human permission:** macOS Privacy & Security shows Full Access for the
   configured application.
2. **Application identity:** the private machine profile points to the exact
   `.app`, executable, and bundle identifier that macOS authorized.
3. **Execution receipt:** the app emits a newly modified receipt carrying the
   bridge-generated launch nonce, source observation, helper fingerprint, and
   offline-use facts.
4. **Catalog verification:** after any write, the independent verifier checks
   exact folder parentage, album parentage, and membership through a WAL-aware,
   read-only Photos database snapshot.

Apple's database may represent a top-level user folder as a child of one
untitled internal kind-3999 library root. The verifier accepts only that exact
system-root representation as equivalent to plan-level top-level placement;
every other unexpected parent remains a hard failure.

No one layer substitutes for the others. A settings screenshot is useful human
evidence, but it does not prove that a shell-launched executable inherited the
same identity. Likewise, a visible album does not prove exact parentage or
membership.

## Live authorization check

After completing the private machine profile, run:

```bash
python3 skills/curate-apple-photos/scripts/photo_archive_bridge.py doctor --live
```

The live check launches the configured application bundle and asks PhotoKit to
verify the frozen source. It requests zero images, exports no previews, runs no
OCR, classification, or face detection, performs no network access, and makes
no Photos changes. Its private plan, logs, and nonce-bound receipt remain under
the configured workspace root in `.authorization-checks/`.

`doctor` without `--live` checks paths, profile values, inventory metadata, and
application identity only. It does not prove current PhotoKit authorization.

## External-volume access

Photos access and removable-volume access are separate macOS permissions. If
the Photos library or private run workspace is on an external volume, the
configured helper may also ask to access files on a removable volume. That
prompt governs local plan, log, receipt, preview, or media-file access; it does
not mean Photos Full Access was lost.

Let the named helper display the prompt so a human can decide. Do not automate
the answer or broaden access for historical helper identities. A denial or
unanswered prompt leaves the live check without a receipt and therefore
unverified.

## Launch completion

`/usr/bin/open -W` is a launcher boundary, not a receipt boundary. On some
systems it may return before a long-running helper has written its receipt.
The bridge therefore polls for a newly modified, valid JSON receipt carrying
the current launch nonce. The helper keeps its own configured log private, and
the bridge fails on a launcher error or bounded receipt timeout.

Use `--receipt-timeout-seconds` only to set an honest upper bound for the
operation. Never shorten it merely to make a stuck run appear decisive, and
never infer completion from the launcher's exit code.

## Collection identifiers

Photos SQLite collection UUIDs and PhotoKit local identifiers are not
interchangeable. PhotoKit identifiers include a type suffix such as
`/L0/NNN`. Never pass a bare database `ZUUID` to a PhotoKit collection fetch.
The helper rejects it before the framework call, preventing the framework
exception `PHQuery requires a type`.

For initial setup, verify the intended title path read-only, resolve each
existing folder through its exact parent, and retain the typed identifiers from
the private receipt in the mode-0600 machine profile.

## Interpreting authorization status

Do not compare raw numeric authorization values copied from different macOS
APIs or logs. Their enum meanings are API-specific. Treat the app-bundle result
and fresh receipt as authoritative for this integration. Launching the Mach-O
executable directly is a diagnostic of a different process context and is not
the supported authorization test.

## Rebuilds and historical helpers

The installed app's stable bundle identifier is part of the permission
contract. A rebuild, replacement, rename, or ad-hoc signature change can cause
macOS to request access again. Never reset TCC or replace the app automatically.

Old helper entries in System Settings are separate identities. They need not
remain authorized for the configured current helper to work. Remove or disable
historical identities only through an explicit human maintenance decision.

Build a reviewed helper candidate with:

```bash
./bin/build-helper-app /private/build-output
```

The build uses the tracked plist and Swift source, links the required macOS
frameworks, signs with `PHOTO_FIELDWORK_CODESIGN_IDENTITY` when set or ad-hoc
signing otherwise, and verifies the resulting bundle. Installation remains a
separate explicit human-reviewed operation because replacing the authorized
bundle can trigger new system permission prompts.

Keep screenshots, local paths, source counts and digests, catalog identifiers,
and receipts private. Public documentation should describe the contract, not a
person's library state.
