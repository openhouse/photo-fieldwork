# Inventory fields

The selector accepts UTF-8 CSV. Unknown columns are preserved. Boolean values may be `true`, `false`, `1`, or `0`.

## Required

| Field | Meaning |
| --- | --- |
| `uuid` | Stable catalog or file identifier. |
| `filename` | Human-readable original filename. |

## Recommended

| Field | Meaning |
| --- | --- |
| `candidate_views` | Semicolon-separated view IDs suggested by metadata retrieval. These remain hypotheses. |
| `reserved_view` | View whose candidate reserve admitted the asset before global union and truncation. |
| `evidence_confidence` | `high`, `medium`, `low`, or `unknown`. |
| `retrieval_evidence_types` | Typed reason the asset entered retrieval, normally `retrieval_index`. |
| `editor_hypothesis` | Provisional interpretive view; never source provenance by itself. |
| `visible_evidence` | Generalized observation supported by local pixel inspection. |
| `source_provenance` | Traceable project or archival authority, when separately established. |
| `visible_context` | Short controlled description such as `people`, `apparatus`, `place`, or `document`. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `safety_status` | `clear` or `hold`. Holds can never enter the master. |
| `safety_reason` | Generalized reason. Do not store sensitive OCR text. |
| `source_face_count` | Existing catalog face count; never treated as an identity inference. |
| `inspected_face_count` | Local detector count from the declared inspection policy. |
| `known_face_count` | Conservative maximum of source and inspected counts. |
| `hidden` | Excludes the item when true. |
| `missing` | Excludes the item when true. |
| `duplicate_group` | Exact-duplicate group identifier. One representative is retained. |
| `burst_group` | Near-identical burst group identifier. The configured limit is retained. |
| `aesthetic_score` | Optional Apple score used only within a duplicate or burst group. |
| `event_cluster` | Event identifier used to limit concentration. |
| `date` | Capture or import date. Treat as fallible provenance. |
| `place` | Coarsened place only in editor-facing exports. |
| `local_path` | Local preview or original path. Do not publish private paths. |
| `inspection_key` | Content address for asset, source, helper, preview, classifier, and ruleset policy. |
| `preview_sha256` | Optional local exact-preview digest for duplicate audit. |
| `perceptual_hash` | Optional adapter-provided local perceptual hash for review candidates. |
| `replacement_review_status` | `pending` until a cascading addition or reassignment is visually reviewed. |
| `duplicate_review_status` | `pending` until a cross-UUID duplicate candidate is resolved. |
| `publication_clearance` | Separate consent state; defaults to `not_assessed`. |

The selector writes `primary_view`, `score_total`, `selection_tier`, and `selection_reason` into the proposed master. Album membership never changes `publication_clearance`.
