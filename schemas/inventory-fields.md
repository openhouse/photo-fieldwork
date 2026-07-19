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
| `evidence_confidence` | `high`, `medium`, `low`, or `unknown`. |
| `visible_context` | Short controlled description such as `people`, `apparatus`, `place`, or `document`. |
| `persons` | Semicolon-separated pre-existing person names. Never infer unnamed identities. |
| `favorite` | Prior human attention signal. |
| `edited` | Prior human attention signal. |
| `safety_status` | `clear`, `needs-review`, `hold`, or `unavailable`. Only `clear` can enter the master automatically. |
| `safety_reason` | Generalized reason. Do not store sensitive OCR text. |
| `hidden` | Excludes the item when true. |
| `missing` | Excludes the item when true. |
| `duplicate_group` | Exact-duplicate group identifier. One representative is retained. |
| `burst_group` | Near-identical burst group identifier. The configured limit is retained. |
| `aesthetic_score` | Optional Apple score used only within a duplicate or burst group. |
| `event_cluster` | Event identifier used to limit concentration. |
| `outside_prior` | Whether the item is outside a configured prior corpus. |
| `album_lineages` | Private source lineage classes such as `human_source` or `fieldwork_generated`. |
| `date` | Capture or import date. Treat as fallible provenance. |
| `place` | Coarsened place only in editor-facing exports. |
| `local_path` | Local preview or original path. Do not publish private paths. |

The selector writes `primary_view`, `score_total`, `selection_tier`, and `selection_reason` into the proposed master.

## Publication-readiness fields

These states are intentionally independent. Retrieval relevance, safety, consent,
and permission to publish are not interchangeable.

| Field | Allowed values |
| --- | --- |
| `source_eligibility` | `eligible`, `unavailable`, `excluded` |
| `retrieval_relevance` | `high`, `medium`, `low`, `unknown` |
| `visible_evidence` | `supported`, `ambiguous`, `contradicted`, `unreviewed` |
| `rights_status` | `owner-verified`, `third-party`, `unknown` |
| `consent_status` | `cleared-for-use`, `ask`, `declined`, `not-applicable`, `unknown` |
| `claim_status` | `visible-only`, `provenance-backed`, `caption-review` |
| `publication_status` | `not-reviewed`, `candidate`, `cleared-for-specific-use`, `published` |

Consent clearance must be scoped to a use, audience, surface, and date outside
the selector. People associations and public-event context are never consent.
