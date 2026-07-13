#!/usr/bin/env python3
"""Generate a local-only editor review surface from manifests and verified previews."""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path


SAFE_FIELDS = {
    "uuid",
    "filename",
    "primary_view",
    "assigned_view",
    "score_total",
    "assignment_status",
    "selection_reason",
    "direct_provenance",
    "safety_status",
    "proposal_id",
    "master_sha256",
}


def canonical_id(value: str) -> str:
    return value.strip().split("/", 1)[0]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def build_payload(sample: list[dict[str, str]], preview_index: list[dict[str, str]]) -> list[dict[str, str]]:
    previews = {
        canonical_id(row["uuid"]): row
        for row in preview_index
        if row.get("decode_status") == "ok" and row.get("preview_path")
    }
    missing = [row["uuid"] for row in sample if canonical_id(row["uuid"]) not in previews]
    if missing:
        raise ValueError(f"{len(missing)} review rows lack verified previews; first={missing[0]}")
    payload = []
    for source in sample:
        item = {key: str(source.get(key, "")) for key in SAFE_FIELDS}
        item["uuid"] = canonical_id(source["uuid"])
        item["preview_url"] = Path(previews[item["uuid"]]["preview_path"]).resolve().as_uri()
        item["decision"] = ""
        item["caption"] = ""
        item["rights_status"] = "unreviewed"
        item["consent_status"] = "unreviewed"
        item["public_safety_status"] = "unreviewed"
        payload.append(item)
    return payload


def render_html(payload: list[dict[str, str]], title: str) -> str:
    data = json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: #f4f4f1; color: #181816; }}
header {{ position: sticky; top: 0; z-index: 2; background: #fff; border-bottom: 1px solid #cbc9c2; padding: 12px 18px; }}
.bar {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px; max-width: 1500px; margin: auto; }}
h1 {{ font-size: 18px; margin: 0 auto 0 0; letter-spacing: 0; }}
label {{ font-size: 12px; font-weight: 650; }}
select, input, textarea, button {{ font: inherit; border: 1px solid #aaa79f; background: #fff; color: #181816; border-radius: 4px; }}
select, input, button {{ min-height: 34px; padding: 6px 9px; }}
button {{ cursor: pointer; font-weight: 650; }}
button.primary {{ background: #1e5d48; color: #fff; border-color: #1e5d48; }}
main {{ max-width: 1500px; margin: auto; padding: 16px 18px 48px; }}
.summary {{ display: flex; gap: 18px; margin-bottom: 14px; font-size: 13px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }}
article {{ background: #fff; border: 1px solid #d2d0c9; border-radius: 6px; overflow: hidden; min-width: 0; }}
.image {{ aspect-ratio: 4 / 3; background: #262622; display: grid; place-items: center; }}
.image img {{ width: 100%; height: 100%; object-fit: contain; }}
.body {{ padding: 10px; display: grid; gap: 8px; }}
.meta {{ display: flex; gap: 8px; justify-content: space-between; font-size: 12px; color: #56534d; min-width: 0; }}
.uuid {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.decisions {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 4px; }}
.decisions button {{ padding: 4px; min-width: 0; font-size: 11px; }}
.decisions button[aria-pressed="true"] {{ background: #1e5d48; color: #fff; border-color: #1e5d48; }}
textarea {{ width: 100%; min-height: 52px; padding: 7px; resize: vertical; }}
.checks {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; }}
.checks label {{ display: grid; gap: 3px; }}
.checks select {{ width: 100%; min-width: 0; }}
@media (max-width: 700px) {{ .grid {{ grid-template-columns: 1fr; }} .decisions {{ grid-template-columns: repeat(3, 1fr); }} }}
</style>
</head>
<body>
<header><div class="bar">
<h1>{html.escape(title)}</h1>
<label>View <select id="view-filter"><option value="">All</option></select></label>
<label>Decision <select id="decision-filter"><option value="">All</option><option>keep</option><option>alternate</option><option>reject</option><option>uncertain</option><option>needs-rights-review</option></select></label>
<label>Search <input id="search" type="search" autocomplete="off"></label>
<button id="export" class="primary">Export feedback CSV</button>
</div></header>
<main>
<div class="summary"><span id="visible-count"></span><span id="shortlist-count"></span><span id="review-count"></span></div>
<div id="grid" class="grid"></div>
</main>
<script>
const records = {data};
const decisions = ["keep", "alternate", "reject", "uncertain", "needs-rights-review"];
const statusOptions = ["unreviewed", "clear", "needs-review", "hold"];
const grid = document.querySelector("#grid");
const viewFilter = document.querySelector("#view-filter");
const decisionFilter = document.querySelector("#decision-filter");
const search = document.querySelector("#search");
const esc = value => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
for (const view of [...new Set(records.map(r => r.primary_view))].sort()) {{
  const option = document.createElement("option"); option.value = view; option.textContent = view; viewFilter.append(option);
}}
function statusSelect(field, value, index) {{
  const options = statusOptions.map(item => `<option ${{item === value ? "selected" : ""}}>${{item}}</option>`).join("");
  return `<label>${{field.replaceAll("_", " ")}}<select data-index="${{index}}" data-field="${{field}}">${{options}}</select></label>`;
}}
function render() {{
  const query = search.value.trim().toLowerCase();
  const visible = records.map((record, index) => [record, index]).filter(([record]) =>
    (!viewFilter.value || record.primary_view === viewFilter.value) &&
    (!decisionFilter.value || record.decision === decisionFilter.value) &&
    (!query || `${{record.uuid}} ${{record.filename}} ${{record.selection_reason}}`.toLowerCase().includes(query))
  );
  grid.innerHTML = visible.map(([record, index]) => `<article>
    <div class="image"><img src="${{esc(record.preview_url)}}" alt=""></div>
    <div class="body">
      <div class="meta"><span class="uuid" title="${{esc(record.uuid)}}">${{esc(record.uuid)}}</span><span>view ${{esc(record.primary_view)}}</span></div>
      <div class="decisions">${{decisions.map(decision => `<button data-index="${{index}}" data-decision="${{decision}}" aria-pressed="${{record.decision === decision}}">${{decision}}</button>`).join("")}}</div>
      <textarea data-index="${{index}}" data-field="caption" placeholder="Caption or sequence note">${{esc(record.caption)}}</textarea>
      <div class="checks">${{statusSelect("rights_status", record.rights_status, index)}}${{statusSelect("consent_status", record.consent_status, index)}}${{statusSelect("public_safety_status", record.public_safety_status, index)}}</div>
    </div></article>`).join("");
  document.querySelector("#visible-count").textContent = `${{visible.length}} visible`;
  const shortlist = records.filter(record => ["keep", "alternate"].includes(record.decision)).length;
  document.querySelector("#shortlist-count").textContent = `${{shortlist}} shortlisted${{shortlist >= 20 && shortlist <= 28 ? "" : " (target 20-28)"}}`;
  document.querySelector("#review-count").textContent = `${{records.filter(record => record.decision).length}} reviewed`;
}}
grid.addEventListener("click", event => {{
  const button = event.target.closest("button[data-decision]"); if (!button) return;
  records[Number(button.dataset.index)].decision = button.dataset.decision; render();
}});
grid.addEventListener("change", event => {{
  const control = event.target.closest("[data-field]"); if (!control) return;
  records[Number(control.dataset.index)][control.dataset.field] = control.value;
}});
grid.addEventListener("input", event => {{
  const control = event.target.closest("textarea[data-field]"); if (!control) return;
  records[Number(control.dataset.index)][control.dataset.field] = control.value;
}});
for (const control of [viewFilter, decisionFilter, search]) control.addEventListener("input", render);
document.querySelector("#export").addEventListener("click", () => {{
  const fields = ["uuid", "primary_view", "proposal_id", "master_sha256", "decision", "judgment", "caption", "rights_status", "consent_status", "public_safety_status"];
  const quote = value => `"${{String(value ?? "").replaceAll('"', '""')}}"`;
  const rows = records.filter(record => record.decision).map(record => {{
    const judgment = record.decision === "keep" ? "fit" : record.decision === "reject" ? "reject" : "uncertain";
    return fields.map(field => quote(field === "judgment" ? judgment : record[field])).join(",");
  }});
  const blob = new Blob([[fields.join(","), ...rows].join("\\n") + "\\n"], {{type: "text/csv"}});
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = "editor-feedback.csv"; link.click(); URL.revokeObjectURL(link.href);
}});
render();
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--preview-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="Photo Fieldwork editor review")
    args = parser.parse_args()
    payload = build_payload(read_csv(args.sample), read_csv(args.preview_index))
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output / "index.html"
    output.write_text(render_html(payload, args.title), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
