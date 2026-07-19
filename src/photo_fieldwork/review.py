from __future__ import annotations

import json
import os
from pathlib import Path


def _preview_path(previews: Path, uuid: str) -> Path | None:
    base = uuid.split("/", 1)[0]
    for extension in ("jpg", "jpeg", "png"):
        for name in (f"{base}_L0_001.{extension}", f"{base}.{extension}", f"{uuid.replace('/', '_')}.{extension}"):
            match = previews / name
            if match.is_file():
                return match
    matches = sorted(previews.glob(f"{base}*"))
    return matches[0] if matches else None


def build_review_surface(rows: list[dict[str, str]], previews: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    payload = []
    missing = 0
    for row in rows:
        item = dict(row)
        preview = _preview_path(previews, row["uuid"])
        if preview:
            item["preview_url"] = os.path.relpath(preview.resolve(), output.resolve())
        else:
            item["preview_url"] = ""
            missing += 1
        payload.append(item)
    encoded = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Photo Fieldwork Review</title>
<style>
:root {{ color-scheme: light; font-family: ui-sans-serif, system-ui, sans-serif; }}
body {{ margin: 0; color: #161616; background: #f4f3ef; }}
header {{ position: sticky; top: 0; z-index: 2; padding: 12px 18px; background: #fff; border-bottom: 1px solid #bbb; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
h1 {{ font-size: 18px; margin: 0 auto 0 0; }}
button, select {{ min-height: 36px; border: 1px solid #777; background: #fff; padding: 6px 10px; }}
main {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(280px,1fr)); gap: 10px; padding: 10px; }}
article {{ background: #fff; border: 1px solid #bbb; border-radius: 6px; overflow: hidden; }}
.frame {{ aspect-ratio: 4 / 3; background: #222; display: grid; place-items: center; }}
img {{ width: 100%; height: 100%; object-fit: contain; }}
.missing {{ color: #fff; }}
.body {{ padding: 10px; display: grid; gap: 8px; }}
.meta {{ font-size: 12px; overflow-wrap: anywhere; }}
.choices {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 5px; }}
.choices label {{ border: 1px solid #999; padding: 7px 3px; text-align: center; }}
textarea, input[type=text] {{ box-sizing: border-box; width: 100%; border: 1px solid #999; padding: 7px; }}
textarea {{ min-height: 70px; resize: vertical; }}
details {{ border-top: 1px solid #ddd; padding-top: 7px; }}
details > div {{ display: grid; gap: 6px; padding-top: 7px; }}
article[data-judgment=fit] {{ border-color: #168248; border-width: 2px; }}
article[data-judgment=reject] {{ border-color: #b52c2c; border-width: 2px; }}
article[data-judgment=uncertain] {{ border-color: #9a6b00; border-width: 2px; }}
</style>
</head>
<body>
<header><h1>Photo Fieldwork Review</h1><span id="count"></span>
<select id="filter" aria-label="Filter judgment"><option value="all">All</option><option value="open">Open</option><option value="fit">Fit</option><option value="reject">Reject</option><option value="uncertain">Uncertain</option></select>
<button id="download">Download feedback CSV</button></header>
<main id="grid"></main>
<script id="review-data" type="application/json">{encoded}</script>
<script>
const rows=JSON.parse(document.getElementById('review-data').textContent); const grid=document.getElementById('grid');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
function render(){{grid.innerHTML=''; const filter=document.getElementById('filter').value; let shown=0;
rows.forEach((r,i)=>{{const j=r.judgment||''; if(filter==='open'&&j||filter!=='all'&&filter!=='open'&&j!==filter)return; shown++;
const card=document.createElement('article');card.dataset.judgment=j;card.innerHTML=`<div class="frame">${{r.preview_url?`<img loading="lazy" src="${{esc(r.preview_url)}}" alt="Local preview for ${{esc(r.filename||r.uuid)}}">`:'<span class="missing">Preview unavailable</span>'}}</div><div class="body"><strong>${{esc(r.primary_view||r.view_id||'Unclassified')}}</strong><div class="meta">${{esc(r.filename)}}<br>${{esc(r.uuid)}}</div><div class="choices">${{['fit','reject','uncertain'].map(v=>`<label><input type="radio" name="j-${{i}}" value="${{v}}" ${{j===v?'checked':''}}> ${{v}}</label>`).join('')}}</div><textarea class="note" placeholder="Visible reason">${{esc(r.visible_reason||r.evaluation_note||'')}}</textarea><input class="error" type="text" placeholder="Error category" value="${{esc(r.error_category||'')}}"><label>Safety <select><option value="clear">clear</option><option value="hold" ${{(r.editorial_safety_status||r.safety_status)==='hold'?'selected':''}}>hold</option></select></label><details><summary>Attribution and provenance</summary><div><input class="provenance" type="text" placeholder="Provenance status" value="${{esc(r.provenance_status||'hypothesis')}}"><input class="actor" type="text" placeholder="Reviewer actor" value="${{esc(r.reviewer_actor||'')}}"><input class="lens" type="text" placeholder="Reviewer lens" value="${{esc(r.reviewer_lens||'')}}"><input class="round" type="text" placeholder="Round ID" value="${{esc(r.round_id||'')}}"></div></details></div>`;
card.querySelectorAll('input[type=radio]').forEach(x=>x.onchange=()=>{{r.judgment=x.value;render()}}); card.querySelector('.note').oninput=e=>r.visible_reason=e.target.value; card.querySelector('.error').oninput=e=>r.error_category=e.target.value; card.querySelector('.provenance').oninput=e=>r.provenance_status=e.target.value; card.querySelector('.actor').oninput=e=>r.reviewer_actor=e.target.value; card.querySelector('.lens').oninput=e=>r.reviewer_lens=e.target.value; card.querySelector('.round').oninput=e=>r.round_id=e.target.value; card.querySelector('.body select').onchange=e=>r.editorial_safety_status=e.target.value; grid.appendChild(card);}}); document.getElementById('count').textContent=`${{shown}} shown / ${{rows.length}} total`;}}
function csvCell(v){{const s=String(v??'');return /[",\\n]/.test(s)?'"'+s.replaceAll('"','""')+'"':s}};
document.getElementById('filter').onchange=render; document.getElementById('download').onclick=()=>{{const fields=['uuid','filename','primary_view','judgment','visible_reason','error_category','editorial_safety_status','provenance_status','reviewer_actor','reviewer_lens','round_id'];const csv=[fields.join(','),...rows.map(r=>fields.map(f=>csvCell(r[f])).join(','))].join('\\n')+'\\n';const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{{type:'text/csv'}}));a.download='evaluation-feedback.csv';a.click();URL.revokeObjectURL(a.href)}}; render();
</script>
</body></html>
"""
    index = output / "index.html"
    index.write_text(document, encoding="utf-8")
    return {
        "rows": len(rows),
        "previews_found": len(rows) - missing,
        "previews_missing": missing,
        "index": str(index),
        "network_required": False,
    }
