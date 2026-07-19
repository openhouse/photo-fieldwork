from __future__ import annotations

import json
from pathlib import Path


def preview_uri(previews: Path, identifier: str) -> str:
    name = identifier.replace("/", "_") + ".jpg"
    return (previews / name).resolve().as_uri()


def render_review_workspace(
    rows: list[dict[str, str]],
    previews: Path,
    round_id: str,
    reviewer_lens: str,
) -> str:
    records = [
        {
            "uuid": row["uuid"],
            "filename": row["filename"],
            "primary_view": row.get("primary_view", "unknown"),
            "score_total": row.get("score_total", ""),
            "preview": preview_uri(previews, row["uuid"]),
            "judgment": row.get("judgment", ""),
            "visible_reason": row.get("visible_reason", ""),
            "safety_status": row.get("safety_status", "clear"),
            "public_suitability": row.get("public_suitability", "unreviewed"),
            "provenance_status": row.get("provenance_status", "unreviewed"),
            "error_category": row.get("error_category", ""),
            "round_id": row.get("round_id") or round_id,
            "reviewer_lens": row.get("reviewer_lens") or reviewer_lens,
        }
        for row in rows
    ]
    payload = json.dumps(records, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Photo Fieldwork Review</title>
<style>
:root {{ color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #f5f5f2; color: #171714; }}
header {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 18px; border-bottom: 1px solid #c9c9c2; background: #fff; }}
h1 {{ margin: 0; font-size: 18px; letter-spacing: 0; }}
button, select, textarea {{ font: inherit; }}
button {{ min-width: 44px; min-height: 38px; border: 1px solid #8a8a82; background: #fff; cursor: pointer; }}
button[aria-pressed="true"] {{ background: #171714; color: #fff; }}
main {{ display: grid; grid-template-columns: minmax(0, 1fr) 360px; min-height: calc(100vh - 63px); }}
.image-stage {{ display: grid; place-items: center; padding: 20px; background: #20201d; min-width: 0; }}
img {{ display: block; max-width: 100%; max-height: calc(100vh - 105px); object-fit: contain; }}
.panel {{ padding: 18px; overflow: auto; background: #fff; border-left: 1px solid #c9c9c2; }}
.meta {{ color: #5b5b54; font-size: 13px; overflow-wrap: anywhere; }}
.choices {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 18px 0; }}
label {{ display: grid; gap: 6px; margin: 14px 0; font-size: 13px; font-weight: 600; }}
select, textarea {{ width: 100%; border: 1px solid #8a8a82; padding: 8px; background: #fff; }}
textarea {{ min-height: 96px; resize: vertical; }}
.nav {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 18px; }}
.privacy {{ margin: 10px 0 0; font-size: 12px; color: #5b5b54; }}
@media (max-width: 760px) {{ main {{ grid-template-columns: 1fr; }} .panel {{ border-left: 0; border-top: 1px solid #c9c9c2; }} img {{ max-height: 60vh; }} }}
</style>
</head>
<body>
<header>
  <div><h1>Photo Fieldwork Review</h1><p class="privacy">Static local file. No network service or upload.</p></div>
  <button id="download" type="button">Export feedback CSV</button>
</header>
<main>
  <section class="image-stage"><img id="preview" alt="Private review preview"></section>
  <aside class="panel">
    <p id="position" class="meta"></p>
    <p id="identity" class="meta"></p>
    <div class="choices" aria-label="Judgment">
      <button type="button" data-judgment="fit">Fit (F)</button>
      <button type="button" data-judgment="reject">Reject (R)</button>
      <button type="button" data-judgment="uncertain">Uncertain (U)</button>
    </div>
    <label>Visible reason<textarea id="reason"></textarea></label>
    <label>Safety state<select id="safety"><option>clear</option><option>machine-suspected</option><option>human-confirmed-hold</option></select></label>
    <label>Public suitability<select id="suitability"><option>unreviewed</option><option>not-suitable</option><option>review-required</option><option>candidate</option></select></label>
    <label>Provenance state<select id="provenance"><option>unreviewed</option><option>unsupported</option><option>partial</option><option>externally-supported</option></select></label>
    <label>Error category<select id="error"><option value=""></option><option>retrieval-mismatch</option><option>context-collapse</option><option>taxonomy-coercion</option><option>privacy-miss</option><option>relationship-loss</option><option>temporal-distortion</option><option>redundancy</option><option>aesthetic-overreach</option><option>visible-fit</option></select></label>
    <div class="nav"><button id="previous" type="button">Previous</button><button id="next" type="button">Next</button></div>
  </aside>
</main>
<script>
const records = {payload};
let index = 0;
const byId = id => document.getElementById(id);
const fields = {{reason: "visible_reason", safety: "safety_status", suitability: "public_suitability", provenance: "provenance_status", error: "error_category"}};
function saveFields() {{ const row = records[index]; for (const [id,key] of Object.entries(fields)) row[key] = byId(id).value; }}
function render() {{
  const row = records[index];
  byId("preview").src = row.preview;
  byId("position").textContent = `${{index + 1}} of ${{records.length}} | view ${{row.primary_view}} | score ${{row.score_total}}`;
  byId("identity").textContent = row.uuid;
  for (const [id,key] of Object.entries(fields)) byId(id).value = row[key] || "";
  document.querySelectorAll("[data-judgment]").forEach(button => button.setAttribute("aria-pressed", button.dataset.judgment === row.judgment));
}}
function move(delta) {{ saveFields(); index = Math.max(0, Math.min(records.length - 1, index + delta)); render(); }}
function judge(value) {{ records[index].judgment = value; render(); }}
document.querySelectorAll("[data-judgment]").forEach(button => button.addEventListener("click", () => judge(button.dataset.judgment)));
byId("previous").addEventListener("click", () => move(-1));
byId("next").addEventListener("click", () => move(1));
document.addEventListener("keydown", event => {{
  if (event.target.matches("textarea,select")) return;
  if (event.key === "ArrowLeft") move(-1);
  if (event.key === "ArrowRight") move(1);
  if (event.key.toLowerCase() === "f") judge("fit");
  if (event.key.toLowerCase() === "r") judge("reject");
  if (event.key.toLowerCase() === "u") judge("uncertain");
}});
byId("download").addEventListener("click", () => {{
  saveFields();
  const columns = ["uuid","filename","primary_view","judgment","visible_reason","safety_status","public_suitability","provenance_status","error_category","round_id","reviewer_lens"];
  const quote = value => `"${{String(value ?? "").replaceAll('"','""')}}"`;
  const csv = [columns.join(","), ...records.map(row => columns.map(key => quote(row[key])).join(","))].join("\\n") + "\\n";
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([csv], {{type: "text/csv"}}));
  link.download = "photo-fieldwork-feedback.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}});
render();
</script>
</body>
</html>
"""
