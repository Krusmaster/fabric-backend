"""An empty Power BI report bound to a semantic model, as a Fabric item (round n64).

`POST /v1/workspaces/{workspaceId}/reports` takes either a `definition` (PBIR parts) or a `creationPayload`, never
both. With `creationPayload.semanticModelReference` (`referenceType: "ById"`, `itemId`, `workspaceId`) Fabric creates
a report with one blank page and no visuals, already bound to that model, and no PBIR is sent. Delegated scope
`Report.ReadWrite.All` or `Item.ReadWrite.All`; Contributor on the workspace and read permission on the model. The
call answers 201 with the item, or 202 with `x-ms-operation-id` (a long-running operation). Microsoft Learn, Report -
Items - Create Report (learn.microsoft.com/rest/api/fabric/report/items/create-report), read 29 October 2026.

Round n144: the default page has visuals. On 7 November 2026 create_report on shop_model created a page with nothing on
it. Now the tool reads the model's TMDL (the same getDefinition compare_semantic_model reads, model_compare.from_tmdl)
and sends a `definition` in PBIR instead of the creationPayload; `empty_page=true` keeps the old blank page. The
visuals are built only on the model's own measures and columns (`visuals`):

- a card per count measure (COUNTROWS, COUNT, COUNTA, DISTINCTCOUNT), at most four;
- a clustered column chart of a quantity measure (a SUM of a column amounts.is_quantity reads as a quantity), else a
  count measure, by the Month column of the date table, when the measure's table reaches that table through active
  many-to-one relationships (orders.order_date -> Calendar.Date in semantic_model_draft);
- a clustered bar chart of the same kind of measure by the most-referenced dimension the measure's table reaches
  through dimensions only (a table without measures on the one side of an active relationship): ranked by the active
  relationships pointing at it, then by distance (further is coarser, fewer bars), then by name. For shop:
  order_items -> products -> categories, so Total quantity by categories.name; a header such as orders holds measures
  of its own and is not walked through;
- a table of the nearest dimension's label and a measure, sorted by the measure, largest first (the top rows first;
  no Top N filter is written).

A filter flows from the one side to the many side, so a measure is only ever drawn by a column of a table its own
table reaches that way; a header amount drawn by a product would repeat the order total on every bar. A measure that
is a plain SUM of a column the model does not sum by default (summarizeBy: none, which semantic_model_draft and n133
set on header amounts and on flat-table header amounts, amount_levels and n106), or of a column whose name is also a
column of a table it references (a header's amount copied onto its lines), is never drawn: `left_out` says why. A
personal-data label column (privacy.classify) is not used. Everything is sorted, and names are uuid5 hashes of the
model and the visual, so the same model gives the same definition.

The format, from Microsoft's public sources (read 7 November 2026), nothing guessed:

- Parts and binding: Report definition (microsoft/mcp ee11217, tools/Fabric.Mcp.Tools.Docs/src/Resources/item-definitions/
  report-definition.md, the item-definition article Report - Items - Create Report links to): `definition.pbir` with
  `datasetReference.byConnection.connectionString` "semanticmodelid=<id>" for a model in a workspace; the PBIR
  `definition/` folder with `version.json`, `report.json`, `pages/pages.json`, `pages/<page>/page.json` and
  `pages/<page>/visuals/<visual>/visual.json`; its visual.json example (`position`, `visual.visualType`,
  `visual.query.queryState.<role>.projections[].field.Column|Measure.Expression.SourceRef.Entity` + `Property`,
  `queryRef`, `active`, `sortDefinition.sort[].direction` "Descending", `drillFilterOtherVisuals`). Create Report
  takes `definition.parts` (path, payload, payloadType InlineBase64), microsoft/fabric-rest-api-specs 6f817cb
  report/definitions.json and examples/CreateReport.json.
- Schemas: microsoft/json-schemas eecc60d fabric/item/report: definitionProperties 2.0.0, definition/versionMetadata
  1.0.0, report 3.1.0 (`themeCollection` required, its properties not; empty here, as browser_build's report.json
  config already writes it), pagesMetadata 1.0.0, page 2.0.0 (`displayOption` "FitToPage"), visualContainer 2.0.0
  with visualConfiguration 2.0.0 (`queryState` role -> `projections`, RoleProjection `field` + `queryRef` required).
- version.json "2.0.0" and the PBIR files of a clusteredColumnChart (Category, Y) and a tableEx (Values): the PBIR
  report microsoft/semantic-link-labs b42fc83 ships, src/sempy_labs/report/_bpareporttemplate/ (MIT; read as a format
  example, no code taken).
- card (Values), clusteredBarChart (Category, Y) and tableEx (Values): Microsoft's sample report
  microsoft/Analysis-Services d3ccb50 pbidevmode/fabricps-pbip/SamplePBIP/Sales.Report/report.json (the PBIR-legacy
  format browser_build writes; the roles are the same names in PBIR).

Unit-tested (tests/test_create_report.py): every part parses, has the fields those schemas require and no others the
schemas forbid at the top level, every visual names a measure or column the model has, no visual draws a refused
measure, and two runs give the same parts. Not verified: that Fabric accepts this definition and renders the page;
nothing here has been sent to Fabric.

This module never updates or deletes a report.
"""
from __future__ import annotations

import base64
import json
import re
import uuid

from .deploy import FABRIC, _headers, _id_from, find_item, wait_operation

SCOPE = "Report.ReadWrite.All or Item.ReadWrite.All"
SPEC = "Microsoft Learn, Report - Items - Create Report (creationPayload.semanticModelReference), read 29 October 2026"
DEFINITION_SPEC = ("Report definition (PBIR), microsoft/mcp ee11217 item-definitions/report-definition.md; schemas microsoft/json-schemas "
                   "eecc60d fabric/item/report; read 7 November 2026")
ROUTE = "reports"
ITEM_TYPE = "Report"


def payload(name: str, model_id: str, model_workspace_id: str, description: str = "") -> dict:
    """The request body: displayName, an optional description, and the model reference. No `definition` key."""
    body = {"displayName": name,
            "creationPayload": {"semanticModelReference": {"referenceType": "ById", "itemId": model_id, "workspaceId": model_workspace_id}}}
    if description:
        body["description"] = description[:256]
    return body


def create(body: dict, workspace: str, token_provider=None, poll_seconds: int = 3, max_polls: int = 60) -> dict:
    """POST the report. Succeeded with the item's id, or Failed with the HTTP status and body for the error layer
    (server._finish_create). Creates only: the caller checks the name first, and nothing here updates or deletes."""
    import requests
    headers = _headers(token_provider)
    r = requests.post(f"{FABRIC}/v1/workspaces/{workspace}/{ROUTE}", headers=headers, json=body, timeout=60)
    if r.status_code not in (200, 201, 202):
        return {"status": "Failed", "mode": "created", "http": r.status_code, "body": r.text}
    item_id = _id_from(r)
    op = r.headers.get("x-ms-operation-id")
    if op:
        s = wait_operation(op, headers, poll_seconds, max_polls)
        if s.get("status") != "Succeeded":
            s["mode"] = "created"
            return s
        if not item_id:
            item_id = find_item(workspace, body["displayName"], headers, ITEM_TYPE)
    return {"status": "Succeeded", "mode": "created", "id": item_id}


# ------------------------------------------------------------------ n144: a page with visuals (PBIR) ----------------

_SCHEMAS = "https://developer.microsoft.com/json-schemas/fabric/item/report"
SCHEMA = {"pbir": f"{_SCHEMAS}/definitionProperties/2.0.0/schema.json",
          "version": f"{_SCHEMAS}/definition/versionMetadata/1.0.0/schema.json",
          "report": f"{_SCHEMAS}/definition/report/3.1.0/schema.json",
          "pages": f"{_SCHEMAS}/definition/pagesMetadata/1.0.0/schema.json",
          "page": f"{_SCHEMAS}/definition/page/2.0.0/schema.json",
          "visual": f"{_SCHEMAS}/definition/visualContainer/2.0.0/schema.json"}
PAGE_W, PAGE_H = 1280, 720
MAX_CARDS = 4
_NS = uuid.UUID("6c0b8a52-1f1e-4b8e-9a51-7b1a0c6e1144")        # fixed: the same model gives the same names
_COUNT = re.compile(r"^\s*(COUNTROWS|COUNTA|COUNT|DISTINCTCOUNT)\s*\(", re.I)
_SUM = re.compile(r"^\s*SUM\s*\(\s*('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)\s*\[((?:[^\]]|\]\])+)\]\s*\)\s*$", re.I)
_NUMERIC = ("int64", "double", "decimal")
_LABEL_NAMES = ("name", "title", "label", "description", "category")


def _name(*parts: str) -> str:
    """A 20-character hex name like the ones Power BI writes for pages and visuals, from a uuid5 of the parts."""
    return uuid.uuid5(_NS, "\x1f".join(parts)).hex[:20]


def _unquote(table: str) -> str:
    return table[1:-1].replace("''", "'") if table.startswith("'") else table


def _active(model: dict) -> list[dict]:
    return [r for r in model.get("relationships", []) if r.get("active", True)
            and r.get("from_table") in model["tables"] and r.get("to_table") in model["tables"]]


def _up(model: dict) -> dict[str, list[dict]]:
    """table -> its active relationships to the one side (the tables whose filter reaches it)."""
    out: dict[str, list[dict]] = {}
    for r in _active(model):
        if (r.get("from_cardinality"), r.get("to_cardinality")) == ("many", "one"):
            out.setdefault(r["from_table"], []).append(r)
    return out


def _reach(model: dict, start: str, through=lambda t: True) -> dict[str, int]:
    """Tables a filter reaches `start` from (one side to many side, active relationships), with their distance."""
    up, seen, todo = _up(model), {start: 0}, [start]
    while todo:
        t = todo.pop(0)
        for r in sorted(up.get(t, []), key=lambda r: (r["to_table"], r.get("to_column", ""))):
            nxt = r["to_table"]
            if nxt not in seen:
                seen[nxt] = seen[t] + 1
                if through(nxt):
                    todo.append(nxt)
    seen.pop(start)
    return seen


def _date_table(model: dict) -> tuple[str, str] | None:
    """(table, month column): the one side of an active relationship on a dateTime column of a table that has a Month
    column (the Calendar semantic_model_draft writes; a date table of the user's own with Month too)."""
    for r in sorted(_active(model), key=lambda r: (r["to_table"], r.get("to_column", ""))):
        t = model["tables"][r["to_table"]]
        col = t["columns"].get(r.get("to_column", ""))
        month = next((c for c in sorted(t["columns"]) if c.lower() == "month"), None)
        if col and col.get("data_type") == "dateTime" and month:
            return r["to_table"], month
    return None


def _label(model: dict, table: str) -> str | None:
    """The column a dimension is shown by: a text column that is no key, no relationship column and no personal data."""
    from . import privacy
    linked = {r.get("from_column") for r in model["relationships"] if r.get("from_table") == table} | \
             {r.get("to_column") for r in model["relationships"] if r.get("to_table") == table}
    cols = [c for c in model["tables"][table]["columns"].values()
            if c.get("data_type") == "string" and not c.get("is_key") and c["name"] not in linked
            and not c["name"].lower().endswith("id") and privacy.classify(table, c["name"]) is None]
    if not cols:
        return None
    return sorted(cols, key=lambda c: (c["name"].lower() not in _LABEL_NAMES, c["name"].lower()))[0]["name"]


def measures(model: dict) -> tuple[list[dict], list[dict]]:
    """(usable, left_out): every measure of the model with its kind (count, quantity, amount), or the reason it is
    never drawn (a plain SUM of a column the model does not sum, or of a header's amount copied onto the lines)."""
    from . import amounts
    usable, left = [], []
    refs = {}
    for r in _active(model):
        refs.setdefault(r["from_table"], set()).add(r["to_table"])
    for tname in sorted(model["tables"]):
        for mname in sorted(model["tables"][tname]["measures"]):
            expr = model["tables"][tname]["measures"][mname].get("expression") or ""
            m = {"table": tname, "measure": mname, "expression": expr}
            s = _SUM.match(expr)
            if _COUNT.match(expr):
                usable.append(m | {"kind": "count"})
                continue
            if s:
                st, sc = _unquote(s.group(1)), s.group(2).replace("]]", "]")
                col = model["tables"].get(st, {}).get("columns", {}).get(sc)
                if col and (col.get("summarize_by") or "").lower() == "none":
                    left.append(m | {"why": f"a plain SUM of {st}.{sc}, which the model does not sum by default (summarizeBy: none): "
                                            "an amount at another level, such as a header's amount repeated over its lines"})
                    continue
                copied = sorted(o for o in refs.get(st, ()) if sc in model["tables"][o]["columns"])
                if copied and amounts.looks_like_amount(sc, "unknown"):
                    left.append(m | {"why": f"a plain SUM of {st}.{sc}, and {copied[0]} has a column {sc} too: probably the header's "
                                            f"amount on each line, which a sum over {st} would count once per line"})
                    continue
                dt = (col or {}).get("data_type")
                if amounts.is_quantity(sc, "unknown") and (dt is None or dt in _NUMERIC):
                    usable.append(m | {"kind": "quantity"})
                    continue
            usable.append(m | {"kind": "amount"})
    return usable, left


def _field(kind: str, table: str, prop: str) -> dict:
    return {kind: {"Expression": {"SourceRef": {"Entity": table}}, "Property": prop}}


def _projection(kind: str, table: str, prop: str, active: bool | None = None) -> dict:
    p = {"field": _field(kind, table, prop), "queryRef": f"{table}.{prop}", "nativeQueryRef": prop}
    if active is not None:
        p["active"] = active
    return p


def visuals(model: dict) -> dict:
    """The visuals of the default page, as plain dicts ({type, title, fields, ...}) before they become visual.json, and
    the measures left out with the reason."""
    usable, left = measures(model)
    has_measures = {m["table"] for m in usable} | {m["table"] for m in left}
    date = _date_table(model)
    is_dim = lambda t: t not in has_measures and (not date or t != date[0])
    out: list[dict] = []
    for m in [m for m in usable if m["kind"] == "count"][:MAX_CARDS]:
        out.append({"type": "card", "title": m["measure"], "measure": m, "fields": [f"{m['table']}[{m['measure']}]"]})
    charted = [m for m in usable if m["kind"] == "quantity"] + [m for m in usable if m["kind"] == "count"]
    if date:
        m = next((m for m in charted if date[0] in _reach(model, m["table"])), None)
        if m:
            out.append({"type": "clusteredColumnChart", "title": f"{m['measure']} by {date[0]} {date[1]}", "measure": m,
                        "category": (date[0], date[1]), "sort": "category",
                        "fields": [f"{date[0]}[{date[1]}]", f"{m['table']}[{m['measure']}]"]})
    bar_measure = None
    for m in charted:
        dims = [(t, d) for t, d in _reach(model, m["table"], through=is_dim).items() if is_dim(t) and _label(model, t)]
        if not dims:
            continue
        inbound = lambda t: sum(1 for r in _active(model) if r["to_table"] == t)
        t, _ = sorted(dims, key=lambda x: (-inbound(x[0]), -x[1], x[0]))[0]
        lab = _label(model, t)
        bar_measure = m
        out.append({"type": "clusteredBarChart", "title": f"{m['measure']} by {t} {lab}", "measure": m, "category": (t, lab),
                    "sort": "measure", "fields": [f"{t}[{lab}]", f"{m['table']}[{m['measure']}]"]})
        break
    base = bar_measure or (charted[0] if charted else None)
    if base:
        near = sorted((d, t) for t, d in _reach(model, base["table"], through=is_dim).items() if is_dim(t) and _label(model, t))
        if near:
            t = near[0][1]
            lab = _label(model, t)
            pick = [m for m in usable if m["kind"] == "amount" and t in _reach(model, m["table"])]
            pick = sorted(pick, key=lambda m: (m["table"] != base["table"], m["table"], m["measure"]))
            m = pick[0] if pick else base
            out.append({"type": "tableEx", "title": f"{t} by {m['measure']}, largest first", "measure": m, "category": (t, lab),
                        "sort": "measure", "fields": [f"{t}[{lab}]", f"{m['table']}[{m['measure']}]"]})
    return {"visuals": out, "left_out": left}


def _positions(vs: list[dict]) -> list[dict]:
    """Cards across the top, the two charts side by side, the table below; within a 1280 x 720 page."""
    cards = [v for v in vs if v["type"] == "card"]
    gap, out, z = 20, [], 0
    for v in vs:
        if v["type"] == "card":
            i, n = cards.index(v), len(cards)
            w = (PAGE_W - gap * (n + 1)) / n
            pos = {"x": gap + i * (w + gap), "y": gap, "width": w, "height": 120}
        elif v["type"] == "clusteredColumnChart":
            pos = {"x": gap, "y": 160, "width": (PAGE_W - 3 * gap) / 2, "height": 260}
        elif v["type"] == "clusteredBarChart":
            pos = {"x": gap * 2 + (PAGE_W - 3 * gap) / 2, "y": 160, "width": (PAGE_W - 3 * gap) / 2, "height": 260}
        else:
            pos = {"x": gap, "y": 440, "width": PAGE_W - 2 * gap, "height": 260}
        z += 1000
        out.append(pos | {"z": z, "tabOrder": z})
    return out


def _visual_json(v: dict, name: str, pos: dict) -> dict:
    m = v["measure"]
    measure = _projection("Measure", m["table"], m["measure"])
    if v["type"] == "card":
        state = {"Values": {"projections": [measure]}}
    elif v["type"] == "tableEx":
        state = {"Values": {"projections": [_projection("Column", *v["category"]), measure]}}
    else:
        state = {"Category": {"projections": [_projection("Column", *v["category"], active=True)]}, "Y": {"projections": [measure]}}
    query: dict = {"queryState": state}
    if v.get("sort") == "measure":
        query["sortDefinition"] = {"sort": [{"field": _field("Measure", m["table"], m["measure"]), "direction": "Descending"}]}
    elif v.get("sort") == "category":
        query["sortDefinition"] = {"sort": [{"field": _field("Column", *v["category"]), "direction": "Ascending"}]}
    return {"$schema": SCHEMA["visual"], "name": name, "position": pos,
            "visual": {"visualType": v["type"], "query": query, "drillFilterOtherVisuals": True}}


def definition_parts(model: dict, model_id: str, page_name: str = "Overview") -> dict:
    """{"parts": {path: text}, "visuals": [...], "left_out": [...]} of a PBIR report bound to the model by id."""
    chosen = visuals(model)
    page = _name(model_id, "page", page_name)
    parts = {"definition.pbir": {"$schema": SCHEMA["pbir"], "version": "4.0",
                                 "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={model_id}"}}},
             "definition/version.json": {"$schema": SCHEMA["version"], "version": "2.0.0"},
             "definition/report.json": {"$schema": SCHEMA["report"], "themeCollection": {}},
             "definition/pages/pages.json": {"$schema": SCHEMA["pages"], "pageOrder": [page], "activePageName": page},
             f"definition/pages/{page}/page.json": {"$schema": SCHEMA["page"], "name": page, "displayName": page_name,
                                                    "displayOption": "FitToPage", "height": PAGE_H, "width": PAGE_W}}
    listed = []
    for v, pos in zip(chosen["visuals"], _positions(chosen["visuals"])):
        name = _name(model_id, page, v["type"], *v["fields"])
        parts[f"definition/pages/{page}/visuals/{name}/visual.json"] = _visual_json(v, name, pos)
        listed.append({"type": v["type"], "title": v["title"], "fields": v["fields"], "name": name})
    return {"parts": {k: json.dumps(val, indent=2) for k, val in parts.items()}, "visuals": listed, "left_out": chosen["left_out"]}


def definition_payload(name: str, parts: dict[str, str], description: str = "") -> dict:
    """The request body with a `definition` (PBIR parts, InlineBase64) and no creationPayload."""
    body = {"displayName": name,
            "definition": {"parts": [{"path": p, "payload": base64.b64encode(t.encode("utf-8")).decode("ascii"), "payloadType": "InlineBase64"}
                                     for p, t in sorted(parts.items())]}}
    if description:
        body["description"] = description[:256]
    return body
