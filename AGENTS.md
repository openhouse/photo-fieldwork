# Working in Photo Fieldwork

Start with `README.md`, then read `docs/workflow.md` and `docs/safety.md` before changing selection or catalog-writing behavior.

Non-negotiable invariants:

- Never modify source photographs or source-album membership.
- Never write directly to an Apple Photos database.
- Never upload photographs, previews, OCR, faces, coordinates, or manifests without explicit authorization.
- Keep safety holds out of the master selection.
- Preserve an unclassified path. Do not force every photograph into a project story.
- Treat project labels as retrieval hypotheses until visible evidence or external provenance supports them.
- Use aesthetic scores only to choose among near-identical burst or duplicate-cluster members.
- Require a small write test and read-only post-write verification before declaring a catalog commit complete.

Run `make check` after changes. Keep the standard-library-only practice workflow working on a fresh Python 3.11+ installation.

