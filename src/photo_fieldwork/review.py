from __future__ import annotations

import html
import json
from pathlib import Path


PUBLIC_FIELDS = (
    "uuid",
    "filename",
    "primary_view",
    "score_total",
    "selection_tier",
    "selection_reason",
    "retrieval_basis",
    "visible_observation",
    "provenance_basis",
    "claim_boundary",
    "visible_context",
    "safety_status",
    "safety_reason",
    "judgment",
    "evaluation_note",
    "error_category",
    "round_id",
    "reviewer_lens",
)


def _preview_name(uuid: str) -> str:
    return uuid.replace("/", "_") + ".jpg"


def render_workbench(rows: list[dict[str, str]], previews: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    preview_root = Path(
        __import__("os").path.relpath(previews.resolve(), output.parent.resolve())
    )
    records = []
    for row in rows:
        item = {field: str(row.get(field, "")) for field in PUBLIC_FIELDS}
        item["preview"] = str(preview_root / _preview_name(row["uuid"]))
        records.append(item)
    payload = json.dumps(records, ensure_ascii=True).replace("</", "<\\/")
    title = html.escape(output.stem.replace("-", " ").title())
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{title}</title>
<style>
:root {{ color-scheme: light; --ink:#171717; --paper:#f7f7f4; --line:#c9c9c3; --accent:#175a46; --hold:#8b1e2d; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.4 system-ui,sans-serif; letter-spacing:0; }}
button {{ font:inherit; }}
.toolbar {{ min-height:56px; padding:8px 14px; border-bottom:1px solid var(--line); display:flex; align-items:center; gap:8px; flex-wrap:wrap; background:#fff; }}
.toolbar strong {{ margin-right:auto; }}
.toolbar button {{ min-height:36px; padding:6px 12px; border:1px solid #777; border-radius:4px; background:#fff; color:var(--ink); }}
.toolbar button[data-action="fit"] {{ border-color:var(--accent); color:var(--accent); }}
.toolbar button[data-action="hold"] {{ border-color:var(--hold); color:var(--hold); }}
.layout {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(280px,380px); height:calc(100vh - 57px); }}
.stage {{ min-width:0; display:grid; place-items:center; padding:18px; background:#262626; overflow:hidden; }}
.stage img {{ max-width:100%; max-height:100%; object-fit:contain; }}
.preview-state {{ display:none; color:#fff; font-size:14px; font-weight:700; letter-spacing:0; }}
.panel {{ overflow:auto; border-left:1px solid var(--line); background:#fff; padding:16px; }}
.panel h1 {{ font-size:18px; margin:0 0 4px; overflow-wrap:anywhere; }}
.view {{ color:#555; margin:0 0 16px; }}
dl {{ margin:0; }}
dt {{ font-size:12px; font-weight:700; text-transform:uppercase; margin-top:14px; }}
dd {{ margin:3px 0 0; overflow-wrap:anywhere; white-space:pre-wrap; }}
textarea {{ width:100%; min-height:80px; margin-top:6px; resize:vertical; font:inherit; }}
.status {{ display:flex; gap:12px; margin-top:14px; font-variant-numeric:tabular-nums; }}
@media (max-width:760px) {{ .layout {{ grid-template-columns:1fr; grid-template-rows:minmax(42vh,1fr) auto; height:auto; }} .panel {{ border-left:0; border-top:1px solid var(--line); }} .stage {{ min-height:42vh; }} }}
</style>
</head>
<body>
<header class="toolbar">
  <strong>Local review workbench</strong>
  <button type="button" data-action="fit">Fit</button>
  <button type="button" data-action="reject">Reject</button>
  <button type="button" data-action="uncertain">Uncertain</button>
  <button type="button" data-action="hold">HOLD</button>
  <button type="button" id="previous" aria-label="Previous image">Previous</button>
  <button type="button" id="next" aria-label="Next image">Next</button>
  <button type="button" id="export">Export CSV</button>
</header>
<main class="layout">
  <section class="stage"><img id="preview" alt=""><p class="preview-state" id="preview-state">PREVIEW UNAVAILABLE</p></section>
  <aside class="panel">
    <h1 id="filename"></h1><p class="view" id="view"></p>
    <dl id="details"></dl>
    <label><strong>Evaluation note</strong><textarea id="note"></textarea></label>
    <div class="status"><span id="progress"></span><span id="decision"></span></div>
  </aside>
</main>
<script>
const records={payload};
const key="photo-fieldwork:"+location.pathname;
const saved=JSON.parse(localStorage.getItem(key)||"{{}}");
let index=0;
for(const row of records) Object.assign(row,saved[row.uuid]||{{}});
const fields=["retrieval_basis","visible_observation","provenance_basis","claim_boundary","selection_reason","visible_context","safety_status","safety_reason","error_category","round_id","reviewer_lens"];
function persist(){{ const value={{}}; for(const row of records) value[row.uuid]={{judgment:row.judgment||"",evaluation_note:row.evaluation_note||"",safety_status:row.safety_status||""}}; localStorage.setItem(key,JSON.stringify(value)); }}
function render(){{ const row=records[index]; const preview=document.getElementById("preview"); const state=document.getElementById("preview-state"); preview.style.display="block"; state.style.display="none"; preview.onload=()=>{{preview.style.display="block";state.style.display="none";}}; preview.onerror=()=>{{preview.style.display="none";state.style.display="block";}}; preview.src=row.preview; preview.alt=row.filename; document.getElementById("filename").textContent=row.filename; document.getElementById("view").textContent=row.primary_view+" · "+row.uuid; const dl=document.getElementById("details"); dl.textContent=""; for(const field of fields){{ if(!row[field]) continue; const dt=document.createElement("dt"); dt.textContent=field.replaceAll("_"," "); const dd=document.createElement("dd"); dd.textContent=row[field]; dl.append(dt,dd); }} document.getElementById("note").value=row.evaluation_note||""; document.getElementById("progress").textContent=`${{index+1}} / ${{records.length}}`; document.getElementById("decision").textContent=row.judgment||"unreviewed"; }}
function decide(action){{ const row=records[index]; row.judgment=action==="hold"?"reject":action; if(action==="hold") row.safety_status="hold"; persist(); if(index<records.length-1) index++; render(); }}
document.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",()=>decide(button.dataset.action)));
document.getElementById("previous").onclick=()=>{{index=Math.max(0,index-1);render();}};
document.getElementById("next").onclick=()=>{{index=Math.min(records.length-1,index+1);render();}};
document.getElementById("note").oninput=event=>{{records[index].evaluation_note=event.target.value;persist();}};
document.addEventListener("keydown",event=>{{if(event.target.tagName==="TEXTAREA")return; const actions={{f:"fit",r:"reject",u:"uncertain",h:"hold",ArrowLeft:"previous",ArrowRight:"next"}}; const action=actions[event.key]; if(["fit","reject","uncertain","hold"].includes(action)) decide(action); if(action==="previous") document.getElementById("previous").click(); if(action==="next") document.getElementById("next").click();}});
document.getElementById("export").onclick=()=>{{const columns=["uuid","primary_view","judgment","evaluation_note","safety_status","error_category","round_id","reviewer_lens"]; const quote=value=>'"'+String(value||"").replaceAll('"','""')+'"'; const csv=[columns.join(","),...records.map(row=>columns.map(column=>quote(row[column])).join(","))].join("\\n"); const link=document.createElement("a"); link.href=URL.createObjectURL(new Blob([csv],{{type:"text/csv"}})); link.download="review-feedback.csv"; link.click(); URL.revokeObjectURL(link.href);}};
render();
</script>
</body>
</html>
"""
    output.write_text(document, encoding="utf-8")
