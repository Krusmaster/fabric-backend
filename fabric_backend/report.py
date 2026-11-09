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
        names = {c.lower(): c for c in t["columns"]}
        month = names.get("year month") or names.get("month")             # n151: "Year Month" keeps the years apart
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


# ------------------------------------------------------------------ n151: a page that reads like a report ------------
# On 7 November 2026 create_report ran live with visuals for the first time (shop_report_visuals on shop_model). Every
# figure was right; the page read like a draft: titles such as "Rows in audit_log", a log table among the cards, "59,00"
# for a count, a column chart left out with nothing in its place. The rules below change what the page looks like and
# nothing about what may be drawn (n144's rules above stay).

LOG_WORDS = {"log", "logs", "audit"}          # a table named like this is no business figure for a card
MARGIN, GAP = 16, 12
TITLE_H, CARD_H, FOOT_H, SLICER_W = 76, 120, 24, 220
# n180: on 9 November 2026 (demo_lh_report2, 1280 x 720) the captions under the cards' numbers ("Rows in orders", "Rows
# in order_items", "Total quantity") and the slicer's title "Category name" were cut off: a card 96 px high held its
# title, the number and the caption at Power BI's automatic sizes, and a dropdown slicer 44 px high held its title, its
# header and the box. Now the font sizes are set, the slicer's header is off (its title names the field), and each
# box is sized for its text by the estimate below (text_problems; the tests check every visual of a page with it).
CARD_TITLE_PT, CARD_VALUE_PT, CARD_CAPTION_PT, SLICER_TITLE_PT = 11, 24, 11, 10
PAD_PX, LINE_GAP_PX, DROPDOWN_PX = 10, 4, 32
CHAR_EM = 0.6                     # a generous average glyph width of Segoe UI, in em (digits and lower case are ~0.5)


def px(pt: float) -> float:
    return pt * 96 / 72


def text_px(text: str, pt: float) -> float:
    return len(text) * px(pt) * CHAR_EM


def caption_pt(text: str, width: float) -> int:
    """The caption's size: CARD_CAPTION_PT, smaller (down to 8 pt) only when a long measure name would not fit."""
    pt = CARD_CAPTION_PT
    while pt > 8 and text_px(text, pt) > width - 2 * PAD_PX:
        pt -= 1
    return pt


def text_problems(v: dict, pos: dict) -> list[str]:
    """What would be cut off in a card or a slicer at its position: the lines' heights against the box's height, each
    line's width against the box's width. Empty when the text fits."""
    out, w, h = [], pos["width"] - 2 * PAD_PX, pos["height"] - 2 * PAD_PX
    if v["type"] == "card":
        cap = v["measure"]["measure"]
        cpt = caption_pt(cap, pos["width"])
        lines = [(v["title"], CARD_TITLE_PT), ("0000000", CARD_VALUE_PT), (cap, cpt)]
    elif v["type"] == "slicer":
        lines = [(v["title"], SLICER_TITLE_PT)]
        h -= DROPDOWN_PX + LINE_GAP_PX
    else:
        return []
    need = sum(px(pt) * 1.25 for _, pt in lines) + LINE_GAP_PX * (len(lines) - 1)
    if need > h:
        out.append(f"{v['type']} {v['title']!r}: {need:.0f} px of text in {h:.0f} px")
    out += [f"{v['type']} {v['title']!r}: {t!r} is {text_px(t, pt):.0f} px wide in {w:.0f} px" for t, pt in lines if text_px(t, pt) > w]
    return out
THEME_NAME = "Krusgraph"
THEME_FILE = f"{THEME_NAME}.json"
# The colours of the site's CSS tokens (fabric_backend/static/site.css :root): ink and muted on white, the four accent
# colours in their darker "-d" and "-ink" forms for bars, so a data label next to a bar stays readable.
THEME = {"name": THEME_NAME,
         "dataColors": ["#E2604A", "#6F9775", "#8A79C8", "#B07A12", "#B23A24", "#3F6A46", "#5B4A9E", "#7F5404"],
         "foreground": "#1B1B1F", "foregroundNeutralSecondary": "#5B5660", "background": "#FFFFFF",
         "backgroundLight": "#FBF8F5", "tableAccent": "#E2604A",
         "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "fontSize": 14, "color": "#1B1B1F"},
                         "label": {"fontFace": "Segoe UI", "fontSize": 12, "color": "#1B1B1F"},
                         "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 32, "color": "#1B1B1F"},
                         "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": "#1B1B1F"}}}


def _words_of(name: str) -> list[str]:
    from .infer import _words
    return _words(name) or [name]


def _singular(word: str) -> str:
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return word[:-3] + "y"
    if w.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        return word[:-1]
    return word


def plain_table(model: dict, table: str) -> str:
    """A table's name in plain words: order_items -> "Order lines" when orders is in the model and order_items points at
    it (the lines of an order), audit_log -> "Audit log", DimCustomer -> "Dim customer". Nothing else is renamed."""
    words = _words_of(table)
    if len(words) >= 2 and words[-1] in ("items", "item", "lines", "line"):
        head = words[:-1]
        targets = {r["to_table"] for r in model.get("relationships", []) if r.get("from_table") == table}
        heads = {"_".join(head), "_".join(head) + "s", "".join(head), "".join(head) + "s"}
        if any(_words_of(t) in (head, head[:-1] + [head[-1] + "s"]) or t.lower() in heads for t in targets):
            words = head + ["lines"]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def title_of(model: dict, m: dict) -> str:
    """The plain title of a measure. "Rows in X" (COUNTROWS of X itself) -> X in plain words; a SUM of a quantity column
    (amounts.is_quantity) -> "Units"; any other measure keeps its own name: no meaning is invented."""
    expr = m.get("expression") or ""
    c = re.match(r"^\s*COUNTROWS\s*\(\s*('(?:[^']|'')+'|[A-Za-z_][A-Za-z0-9_]*)\s*\)\s*$", expr, re.I)
    if c and _unquote(c.group(1)) == m["table"] and m["measure"].lower() in (f"rows in {m['table']}".lower(), f"rows in {m['table']} ({m['table']})".lower()):
        return plain_table(model, m["table"])
    if m.get("kind") == "quantity":
        return "Units"
    return m["measure"]


def _dim_title(model: dict, table: str, singular: bool) -> str:
    words = plain_table(model, table).split(" ")
    if singular:
        words[-1] = _singular(words[-1])
    return " ".join(words)


def _is_log(table: str) -> bool:
    return any(w in LOG_WORDS for w in _words_of(table))


def _has_key(model: dict, table: str) -> bool:
    """An isKey column, or a part in an active relationship: TMDL marks only one-column keys, so a table with a composite
    key (order_items: order_id + line_no) shows its key only through the relationships it takes part in."""
    return (any(c.get("is_key") for c in model["tables"][table]["columns"].values())
            or any(table in (r["from_table"], r["to_table"]) for r in _active(model)))


def _whole(model: dict, m: dict) -> bool:
    """A count, or a SUM of an int64 column: shown without decimals."""
    if m["kind"] == "count":
        return True
    s = _SUM.match(m.get("expression") or "")
    if not s:
        return False
    col = model["tables"].get(_unquote(s.group(1)), {}).get("columns", {}).get(s.group(2).replace("]]", "]"))
    return bool(col) and col.get("data_type") == "int64"


def _format_of(model: dict, m: dict) -> dict:
    """What the dry run says about a measure's number format, and whether the visual sets it (labelPrecision 0): only for
    a whole-number measure whose model gives it no whole-number formatString (a model not made by Krusgraph)."""
    fs = model["tables"][m["table"]]["measures"].get(m["measure"], {}).get("format_string")
    whole = _whole(model, m)
    sets = whole and (not fs or "." in fs)
    return {"format_string": fs, "whole_number": whole, "visual_sets_no_decimals": sets}


def _cards(model: dict, usable: list[dict]) -> tuple[list[dict], list[dict]]:
    """(cards, skipped): row counts of business tables, the tables others point at first, then the units; at most four.
    A table without a key or named like a log (audit_log) gets no card unless nothing else would."""
    counts = [m for m in usable if m["kind"] == "count"]
    business = [m for m in counts if _has_key(model, m["table"]) and not _is_log(m["table"])]
    skipped = [{"visual": "card", "measure": f"{m['table']}[{m['measure']}]",
                "why": f"{m['table']} " + ("is named like a log" if _is_log(m["table"]) else "has no key and no relationship") + ": not a business figure for a card"}
               for m in counts if m not in business] if business else []
    inbound = lambda t: sum(1 for r in _active(model) if r["to_table"] == t)
    chosen = sorted(business or counts, key=lambda m: (-inbound(m["table"]), m["table"], m["measure"]))
    qty = next((m for m in usable if m["kind"] == "quantity"), None)
    chosen = chosen[:MAX_CARDS - (1 if qty else 0)] + ([qty] if qty else [])
    return chosen[:MAX_CARDS], skipped


def visuals(model: dict, model_name: str = "") -> dict:
    """The visuals of the default page, as plain dicts ({type, title, fields, ...}) before they become visual.json; the
    measures left out with the reason (left_out, n144) and the visuals not drawn with the reason (not_drawn, n151)."""
    usable, left = measures(model)
    has_measures = {m["table"] for m in usable} | {m["table"] for m in left}
    date = _date_table(model)
    is_dim = lambda t: t not in has_measures and (not date or t != date[0])
    out: list[dict] = []
    not_drawn: list[dict] = []
    cards, skipped = _cards(model, usable)
    not_drawn += skipped
    for m in cards:
        out.append({"type": "card", "title": title_of(model, m), "measure": m, "fields": [f"{m['table']}[{m['measure']}]"]})
    charted = [m for m in usable if m["kind"] == "quantity"] + [m for m in usable if m["kind"] == "count"]
    month = None
    if date:
        m = next((m for m in charted if date[0] in _reach(model, m["table"])), None)
        if m:
            month = {"type": "clusteredColumnChart", "title": f"{title_of(model, m)} by month", "measure": m,
                     "category": (date[0], date[1]), "sort": "category", "labels": True,
                     "fields": [f"{date[0]}[{date[1]}]", f"{m['table']}[{m['measure']}]"]}
            out.append(month)
        else:
            not_drawn.append({"visual": "clusteredColumnChart", "why": f"no count or quantity measure whose table reaches {date[0]} through active relationships"})
    else:
        not_drawn.append({"visual": "clusteredColumnChart", "why": "the model has no date table with a Month column on the one side of an active relationship"})
    bar_measure, bar_dim = None, None
    for m in charted:
        dims = [(t, d) for t, d in _reach(model, m["table"], through=is_dim).items() if is_dim(t) and _label(model, t)]
        if not dims:
            continue
        inbound = lambda t: sum(1 for r in _active(model) if r["to_table"] == t)
        t, _ = sorted(dims, key=lambda x: (-inbound(x[0]), -x[1], x[0]))[0]
        lab = _label(model, t)
        bar_measure, bar_dim = m, (t, lab)
        out.append({"type": "clusteredBarChart", "title": f"{title_of(model, m)} by {_dim_title(model, t, True).lower()}", "measure": m,
                    "category": (t, lab), "sort": "measure", "labels": True, "fields": [f"{t}[{lab}]", f"{m['table']}[{m['measure']}]"]})
        break
    base = bar_measure or (charted[0] if charted else None)
    if base:
        near = sorted((d, t) for t, d in _reach(model, base["table"], through=is_dim).items() if is_dim(t) and _label(model, t))
        if near:
            t = near[0][1]
            lab = _label(model, t)
            reach = lambda m: t in _reach(model, m["table"])
            pick = ([m for m in usable if m["kind"] == "quantity" and reach(m)] + [m for m in usable if m["kind"] == "amount" and reach(m)]
                    + [m for m in usable if m["kind"] == "count" and reach(m)])
            m = pick[0] if pick else base
            out.append({"type": "tableEx", "title": f"{_dim_title(model, t, False)} by {title_of(model, m).lower()}", "measure": m,
                        "category": (t, lab), "sort": "measure", "total": True, "fields": [f"{t}[{lab}]", f"{m['table']}[{m['measure']}]"]})
    if out:
        if month:
            out.append({"type": "slicer", "title": "Month", "category": month["category"], "fields": [f"{month['category'][0]}[{month['category'][1]}]"]})
        dim = bar_dim or next(((v["category"]) for v in out if v["type"] == "tableEx"), None)
        if dim:
            out.append({"type": "slicer", "title": _dim_title(model, dim[0], True), "category": dim, "fields": [f"{dim[0]}[{dim[1]}]"]})
    return {"visuals": out, "left_out": left, "not_drawn": not_drawn}


def _rows(vs: list[dict]) -> dict[str, tuple[float, float]]:
    """The page's rows, top to bottom, filling 1280 x 720 between even margins: the title (with the slicers beside it),
    the cards, the charts and the table share what is left, the footnote at the bottom."""
    present = {v["type"] for v in vs}
    fixed = [("title", TITLE_H)] + ([("cards", CARD_H)] if "card" in present else [])
    flex = [r for r, ts in (("charts", ("clusteredColumnChart", "clusteredBarChart")), ("table", ("tableEx",))) if present & set(ts)]
    rows = fixed + [(r, 0) for r in flex] + [("foot", FOOT_H)]
    free = PAGE_H - 2 * MARGIN - GAP * (len(rows) - 1) - sum(h for _, h in rows)
    out, y = {}, MARGIN
    for r, h in rows:
        h = h or free / len(flex)
        out[r] = (y, h)
        y += h + GAP
    return out


def _positions(vs: list[dict]) -> list[dict]:
    """A grid within the page's margins: cards side by side, the column chart and the bar chart side by side (the bar
    chart takes the whole width when there is no column chart, and the other way round), the table across the page."""
    rows, inner = _rows(vs), PAGE_W - 2 * MARGIN
    cards = [v for v in vs if v["type"] == "card"]
    charts = [v for v in vs if v["type"] in ("clusteredColumnChart", "clusteredBarChart")]
    slicers = [v for v in vs if v["type"] == "slicer"]
    out, z = [], 0
    for v in vs:
        if v["type"] == "card":
            i, n = cards.index(v), len(cards)
            w = (inner - GAP * (n - 1)) / n
            y, h = rows["cards"]
            pos = {"x": MARGIN + i * (w + GAP), "y": y, "width": w, "height": h}
        elif v in charts:
            i, n = charts.index(v), len(charts)
            w = (inner - GAP * (n - 1)) / n
            y, h = rows["charts"]
            pos = {"x": MARGIN + i * (w + GAP), "y": y, "width": w, "height": h}
        elif v["type"] == "tableEx":
            y, h = rows["table"]
            pos = {"x": MARGIN, "y": y, "width": inner, "height": h}
        elif v["type"] == "slicer":
            i, n = slicers.index(v), len(slicers)
            y, h = rows["title"]
            pos = {"x": PAGE_W - MARGIN - (n - i) * SLICER_W - (n - i - 1) * GAP, "y": y, "width": SLICER_W, "height": h}
        elif v["type"] == "title":
            y, h = rows["title"]
            pos = {"x": MARGIN, "y": y, "width": inner - len(slicers) * (SLICER_W + GAP), "height": h}
        else:                                                              # the footnote
            y, h = rows["foot"]
            pos = {"x": MARGIN, "y": y, "width": inner, "height": h}
        z += 1000
        out.append({k: round(x, 2) for k, x in pos.items()} | {"z": z, "tabOrder": z})
    return out


def _lit(value) -> dict:
    """A literal in a visual's formatting objects: 'text' (single quotes doubled), true/false, 12L (integer), 12.5D."""
    if isinstance(value, bool):
        v = "true" if value else "false"
    elif isinstance(value, int):
        v = f"{value}L"
    elif isinstance(value, float):
        v = f"{value:g}D"
    else:
        v = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": v}}}


def _text_box(text: str, size: str, bold: bool, color: str) -> dict:
    style = {"fontSize": size, "color": color} | ({"fontWeight": "bold"} if bold else {})
    return {"general": [{"properties": {"paragraphs": [{"textRuns": [{"value": text, "textStyle": style}]}]}}]}


def _visual_json(v: dict, name: str, pos: dict, model: dict) -> dict:
    if v["type"] in ("title", "footnote"):
        big = v["type"] == "title"
        return {"$schema": SCHEMA["visual"], "name": name, "position": pos,
                "visual": {"visualType": "textbox", "objects": _text_box(v["text"], "18pt" if big else "9pt", big, THEME["foreground"] if big
                                                                         else THEME["foregroundNeutralSecondary"])}}
    title = {"title": [{"properties": {"show": _lit(True), "text": _lit(v["title"])}}]}
    if v["type"] in ("card", "slicer"):                               # n180: sizes set, so the text fits its box
        size = CARD_TITLE_PT if v["type"] == "card" else SLICER_TITLE_PT
        title["title"][0]["properties"]["fontSize"] = _lit(float(size))       # PBIR writes sizes as doubles: 11D
    if v["type"] == "slicer":
        col = _projection("Column", *v["category"], active=True)
        return {"$schema": SCHEMA["visual"], "name": name, "position": pos,
                "visual": {"visualType": "slicer", "query": {"queryState": {"Values": {"projections": [col]}}},
                           "objects": {"data": [{"properties": {"mode": _lit("Dropdown")}}],
                                       "header": [{"properties": {"show": _lit(False)}}]},
                           "visualContainerObjects": title, "drillFilterOtherVisuals": True}}
    m = v["measure"]
    measure = _projection("Measure", m["table"], m["measure"])
    fmt = _format_of(model, m)
    objects: dict = {}
    if v["type"] == "card":
        state = {"Values": {"projections": [measure]}}
        objects["labels"] = [{"properties": {"fontSize": _lit(float(CARD_VALUE_PT))} | ({"labelPrecision": _lit(0)} if fmt["visual_sets_no_decimals"] else {})}]
        objects["categoryLabels"] = [{"properties": {"show": _lit(True), "fontSize": _lit(float(caption_pt(m["measure"], pos["width"])))}}]
    elif v["type"] == "tableEx":
        cat = _projection("Column", *v["category"])
        state = {"Values": {"projections": [cat, measure]}}
        usable_w = pos["width"] - 40                                   # the row headers' padding and a scroll bar
        objects["columnWidth"] = [{"properties": {"value": _lit(round(usable_w * 0.6, 2))}, "selector": {"metadata": cat["queryRef"]}},
                                  {"properties": {"value": _lit(round(usable_w * 0.4, 2))}, "selector": {"metadata": measure["queryRef"]}}]
        objects["total"] = [{"properties": {"totals": _lit(True)}}]
        if fmt["visual_sets_no_decimals"]:
            objects["columnFormatting"] = [{"properties": {"labelPrecision": _lit(0)}, "selector": {"metadata": measure["queryRef"]}}]
    else:
        state = {"Category": {"projections": [_projection("Column", *v["category"], active=True)]}, "Y": {"projections": [measure]}}
        objects["labels"] = [{"properties": {"show": _lit(True)} | ({"labelPrecision": _lit(0)} if fmt["visual_sets_no_decimals"] else {})}]
    query: dict = {"queryState": state}
    if v.get("sort") == "measure":
        query["sortDefinition"] = {"sort": [{"field": _field("Measure", m["table"], m["measure"]), "direction": "Descending"}]}
    elif v.get("sort") == "category":
        query["sortDefinition"] = {"sort": [{"field": _field("Column", *v["category"]), "direction": "Ascending"}]}
    visual = {"visualType": v["type"], "query": query}
    if objects:
        visual["objects"] = objects
    visual |= {"visualContainerObjects": title, "drillFilterOtherVisuals": True}
    return {"$schema": SCHEMA["visual"], "name": name, "position": pos, "visual": visual}


def definition_parts(model: dict, model_id: str, page_name: str = "Overview", model_name: str = "", created: str = "") -> dict:
    """{"parts": {path: text}, "visuals": [...], "left_out": [...], "not_drawn": [...]} of a PBIR report bound to the
    model by id: the page "Overview · <model name>" with a title, the visuals, a footnote with the creation date
    (`created`, "8 November 2026"; today in UTC when empty) and the Krusgraph theme."""
    import datetime as _dt
    chosen = visuals(model, model_name)
    page = _name(model_id, "page", page_name)
    label = model_name or model_id
    created = created or _dt.datetime.now(_dt.timezone.utc).strftime("%-d %B %Y")
    vs = list(chosen["visuals"])
    if vs:
        vs = [{"type": "title", "title": f"{page_name} · {label}", "text": f"{page_name} · {label}", "fields": ["title"]}] + vs + \
             [{"type": "footnote", "title": "Footnote", "text": f"{created}. Created by Krusgraph from the checked plan.", "fields": ["footnote"]}]
    version = {"visual": "2.0.0", "page": "2.0.0", "report": "3.1.0"}           # the schema versions these parts are written in
    parts = {"definition.pbir": {"$schema": SCHEMA["pbir"], "version": "4.0",
                                 "datasetReference": {"byConnection": {"connectionString": f"semanticmodelid={model_id}"}}},
             "definition/version.json": {"$schema": SCHEMA["version"], "version": "2.0.0"},
             "definition/report.json": {"$schema": SCHEMA["report"],
                                        "themeCollection": {"customTheme": {"name": THEME_FILE, "reportVersionAtImport": version,
                                                                            "type": "RegisteredResources"}},
                                        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                                                              "items": [{"name": THEME_FILE, "path": THEME_FILE, "type": "CustomTheme"}]}]},
             f"StaticResources/RegisteredResources/{THEME_FILE}": THEME,
             "definition/pages/pages.json": {"$schema": SCHEMA["pages"], "pageOrder": [page], "activePageName": page},
             f"definition/pages/{page}/page.json": {"$schema": SCHEMA["page"], "name": page, "displayName": page_name,
                                                    "displayOption": "FitToPage", "height": PAGE_H, "width": PAGE_W}}
    listed = []
    for v, pos in zip(vs, _positions(vs)):
        name = _name(model_id, page, v["type"], *v["fields"])
        parts[f"definition/pages/{page}/visuals/{name}/visual.json"] = _visual_json(v, name, pos, model)
        entry = {"type": v["type"] if v["type"] not in ("title", "footnote") else "textbox", "title": v.get("text") or v["title"],
                 "fields": v["fields"] if v["type"] not in ("title", "footnote") else [], "name": name,
                 "position": {k: pos[k] for k in ("x", "y", "width", "height")}}
        if "measure" in v:
            entry["format"] = _format_of(model, v["measure"])
        listed.append(entry)
    return {"parts": {k: json.dumps(val, indent=2) for k, val in parts.items()}, "visuals": listed, "left_out": chosen["left_out"],
            "not_drawn": chosen["not_drawn"]}


def definition_payload(name: str, parts: dict[str, str], description: str = "") -> dict:
    """The request body with a `definition` (PBIR parts, InlineBase64) and no creationPayload."""
    body = {"displayName": name,
            "definition": {"parts": [{"path": p, "payload": base64.b64encode(t.encode("utf-8")).decode("ascii"), "payloadType": "InlineBase64"}
                                     for p, t in sorted(parts.items())]}}
    if description:
        body["description"] = description[:256]
    return body
