# Inventory fields

The selector accepts UTF-8 CSV. Unknown columns are preserved. Boolean values may be `true`, `false`, `1`, or `0`.

## Required

| Field | Meaning |
| --- | --- |
| `uuid` | Stable catalog or file identifier. |
| `filename` | Human-readable original filename. |
| `assigned_view` | Explicit reviewed editorial assignment. The selector never derives this from `candidate_views`. |

## Recommended

| Field | Meaning |
| --- | --- |
| `candidate_views` | Semicolon-separated view IDs suggested by metadata retrieval. These remain hypotheses. |
| `assignment_status` | `assigned`, `unclassified`, `sparse-hypothesis`, `held`, or `rejected`. Held and rejected rows cannot enter the master. |
| `assignment_reason` | Visible or provenance-based reason for the final assignment. |
| `assignment_version` | Identifier for the retrieval or editorial rule set that produced the assignment. |
| `evidence_confidence` | `high`, `medium`, `low`, or `unknown`. |
| `visible_context` | Short controlled description such as `people`, `apparatus`, `place`, or `document`. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `safety_status` | `clear-automated`, `needs-human-review`, `cleared-human`, `hold-automated`, or `hold-human`. Legacy `clear`, `needs-review`, and `hold` remain readable. Only states explicitly allowed by the configuration can enter the master. |
| `safety_reason` | Generalized reason. Do not store sensitive OCR text. |
| `hidden` | Excludes the item when true. |
| `missing` | Excludes the item when true. |
| `duplicate_group` | Exact-duplicate group identifier. One representative is retained. |
| `perceptual_cluster_id` | Local pixel-derived near-duplicate cluster identifier. One representative is retained. |
| `burst_group` | Near-identical burst group identifier. The configured limit is retained. |
| `aesthetic_score` | Optional Apple score used only within a duplicate or burst group. |
| `event_cluster` | Event identifier used to limit concentration. |
| `date` | Capture or import date. Treat as fallible provenance. |
| `place` | Coarsened place only in editor-facing exports. |
| `local_path` | Local preview or original path. Do not publish private paths. |

The selector writes `primary_view` as an output alias of `assigned_view`, then adds `score_total`, `selection_tier`, `selection_reason`, `proposal_id`, and `master_sha256` to the proposed master.
