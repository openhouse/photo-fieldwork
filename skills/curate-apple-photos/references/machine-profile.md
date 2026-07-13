# Local Apple Photos profile

Live Apple Photos operations require a private JSON profile conforming to the
public `schemas/profile.schema.json`. Begin with `profiles/profile.example.json`,
store the completed file outside the repository, and pass it explicitly with
`--profile`.

`photo_archive_bridge.py init-profile --help` creates the private file with mode
`0600` and refuses to overwrite an existing profile.

The private profile contains:

- the stable permissioned app path, executable name, and bundle identifier;
- the durable private workspace root;
- the compact inventory and immutable Photos database paths;
- the intended source identifier and frozen count;
- protected root, private-review, and write-audit folder titles and identifiers;
- the installed `photo-fieldwork` CLI path.

Do not put a real profile, asset identifier, protected folder identifier, People
manifest, or library count in the public repository.

## Permissioned helper

Always launch plans through the installed app bundle so macOS uses its stable
Photos permission identity. Before inventory, inspection, or writing, run:

```bash
python3 scripts/photo_archive_bridge.py doctor \
  --profile /private/path/profile.json \
  --live
```

The `preflight-read-only` operation must confirm the authorization state observed
by the launched process, resolve the intended source, match its frozen count,
and fetch one local sample with network access disabled. It performs no catalog
mutation and writes a diagnostic receipt even when a check fails.

Replacing, renaming, cloning, rebuilding, or re-signing the helper may create a
new TCC identity. Treat that as an explicit operation, not a troubleshooting loop.

## Source scopes

An immutable source can be a physical Photos album or the virtual
`visible-library-stills://v1` scope. The virtual source means visible, non-hidden,
non-trashed, primary-scope still photographs.

The whole-library inventory builder derives the count it observes. Freeze that
count in the private run and every subsequent plan. Never compile a previously
observed library count into the builder.

## Photos database

Inventory and verification access must use SQLite URI `mode=ro&immutable=1` and
`PRAGMA query_only=ON`. Never issue `INSERT`, `UPDATE`, `DELETE`, schema changes,
or a non-read-only connection against Photos.sqlite.

## Workspaces

- Preserve every version as its own durable workspace and Photos folder.
- Create run directories with mode `0700`.
- Create writer ID files with mode `0600`.
- Keep previews, People associations, HOLD, OCR-derived flags, and writer plans
  outside public repositories and shared web roots.
