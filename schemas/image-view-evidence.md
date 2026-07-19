# Image-view evidence manifest

Relevance is an edge between an asset and an editorial view. A rejection applies to that edge, not automatically to the asset in every context.

| Field | Required | Contract |
| --- | --- | --- |
| `uuid` | yes | Canonical base asset identifier. Photos collection suffixes are removed before comparison. |
| `view_id` | yes | A view present in the run configuration. |
| `retrieval_score` | yes | Numeric metadata-retrieval strength for this view. |
| `direct_provenance` | yes | Boolean indicating direct project or source provenance. |
| `visible_fit_score` | yes | Numeric view-specific visible-evidence score, normally `0` through `1`. |
| `evidence_terms` | yes | Controlled, non-sensitive visible terms. Never raw OCR. |
| `confidence` | yes | `high`, `medium`, `low`, or `unknown`. |
| `status` | yes | `eligible`, `reject`, `uncertain`, `needs-review`, or `hold`. |
| `round_id` | yes | Evaluation lineage. May be empty before review. |
| `reason` | yes | Concise visible or provenance reason. |

Only `eligible` and `uncertain` edges can be assigned. An `uncertain` edge propagates low confidence and an explicit review state into the master.

Safety remains asset-level. Feedback that omits `safety_status` leaves safety unchanged. Clearing a prior `needs-review` state requires both `safety_clearance=true` and an identified reviewer; a HOLD cannot be cleared within the run.
