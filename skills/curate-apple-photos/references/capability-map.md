# Apple Photos insight capability map

## Purpose

This skill is designed to give the archive owner or a local agent the fullest
Apple Photos insight that an osxphotos-class workflow can make available. It
does not default to a minimized metadata view. It discovers and names the
available insight surface before retrieval so nobody has to guess what the
archive can reveal or argue for one field at a time.

This capability enumeration is the default contract, not optional background
reading. The agent must present the available surface and named gaps to the
user at the beginning of Apple Photos work.

The reading boundary is intentionally broad. The mutation boundary remains
narrow: by default the skill may only create approved folders and albums and
add existing assets to them. Public projection remains closed until a named
human clears the exact photographs, fields, wording, credit, and destination.

The machine-readable contract is
[`capability-contract.json`](capability-contract.json). Run
`report_capabilities.py` after `doctor --live` and before retrieval.

## Default insight surface

1. **Library identity and continuity:** library/database version, frozen source
   scope, source count, and digest-bound membership continuity.
2. **Asset identity and technical properties:** stable UUID, current and
   original filename, kind/subtype, dimensions, size, UTI, reference status,
   and local/cloud/missing state.
3. **Time and import context:** creation, addition, modification, time zone, and
   import-session information where available.
4. **Original embedded metadata:** EXIF, IPTC, XMP, GPS, camera/lens, maker
   notes, orientation, color, QuickTime, and sidecar properties available from
   the local original. Metadata-minimized previews do not replace this record.
5. **Photos-authored metadata:** title, description, keywords, favorite,
   hidden, trashed, edit, and external-edit state.
6. **Albums and structure:** album memberships, nested folders, shared
   context, projects, moments, and import sessions where exposed.
7. **People, Pets, and faces:** existing named associations, face counts,
   records, and crops where available. The skill never invents a name for an
   unnamed face.
8. **Places and location:** coordinates and reverse-geocoded place hierarchy,
   retained exactly only in private artifacts.
9. **Computational context:** Apple classification/search labels, activities,
   holidays, venues, detected descriptions, and aesthetic/component scores.
10. **Variants and relationships:** original/edited resources, Live Photo
    components, RAW+JPEG pairs, bursts, adjustments, sidecars, duplicates, and
    related capture groups.
11. **Sharing and social context:** shared-library/album state, syndication,
    comments, likes, and contributor context where available.
12. **Query and export:** compound metadata queries, template fields, complete
    private JSON records, originals/edits/Live/RAW exports, sidecars, and
    dry-run reports.
13. **Local visual evidence:** offline pixels, verified review derivatives,
    labels, face counts, and ephemeral OCR safety signals without upload.
14. **Bounded catalog action:** approved folder/album creation and membership
    only, with receipts, idempotence evidence, and independent verification.

## Capability states

- `AVAILABLE`: the provider is installed and its bounded canary passed.
- `PARTIAL`: useful fields are available, but one or more named providers or
  field families are missing or unproven.
- `UNAVAILABLE`: the capability cannot currently be used.
- `UNVERIFIED`: an executable or artifact exists, but a live/read canary has
  not established that it works with the configured library.

An agent must report every `PARTIAL`, `UNAVAILABLE`, or `UNVERIFIED` item before
retrieval. It must not say that it has maximal or osxphotos-equivalent insight
unless the capability report and a one-record private read probe pass.

## Provider responsibilities

| Provider | Primary responsibility | Boundary |
| --- | --- | --- |
| Private inventory | Fast, source-frozen whole-library retrieval and indexed Photos relationships | Read-only catalog snapshot; private output |
| osxphotos | Broad `PhotoInfo` metadata, structural relationships, querying, variants, and export vocabulary | Read-only by default; writes require a separately reviewed operation |
| ExifTool | Full embedded tag inspection and sidecar-aware technical metadata | Read-only in this skill |
| PhotoKit helper | Permissioned local pixels, original ImageIO properties, and tightly bounded album writes | Network disabled; stable app identity; receipt required |
| Independent verifier | WAL-aware read-only confirmation of folder, album, and membership results | Never shares writer code or performs catalog writes |

## Current implementation boundary

The skill currently materializes the compact whole-library inventory, indexed
People/albums/keywords/search/labels/places, local PhotoKit pixels, original
ImageIO property trees, full non-shallow osxphotos `PhotoInfo` records, ExifTool
tag groups across locally available PhotoInfo resources, verified private
previews, and bounded album writes. A capability report plus
one-record private osxphotos probe must pass before its fields are described as
available in a run.

Some fields vary by macOS and Photos database version. Absence is an evidence
gap, not proof that the photograph never had that property. No capability
report is publication clearance.
