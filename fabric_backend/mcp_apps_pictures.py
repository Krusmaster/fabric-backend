"""MCP Apps, round n170: the chat demo's pictures in the cards. The founder, 8 November 2026: "in the chat on
krusgraph.com you see the links visually, and proposals for ontology, relationships and data products. I want to see
that in Claude too."

Behind the same flag as the other cards (KRUSGRAPH_MCP_APPS, off unless "1"); with the flag off nothing here runs.

Three pictures, each built from what the tool itself computed, never invented:

- the map (plan_backend, validate_plan, review_plan): every table with its key columns (or "no key"), every relationship
  with its column pair and its rule, and its state: passed (green), failed (red, with the orphan count), not checked
  (grey); in review_plan's card also rejected (dashed) and the review status;
- the ontology proposal (ontology_draft, create_ontology's dry run): the entity types with their key, why an entity type
  has none (a composite key or no key at all, the sentence of the tool's own summary.notes), and the relationship types;
- the data products (domain_draft): each proposed domain as a card with its tables, an owner nobody has chosen yet, and
  the Builder's dry-run buttons for that product's tables (mcp_apps_build: an API for GraphQL, a semantic model).

How the data reaches the card. The tool's text answer is unchanged: text-only clients read the same text as before. The
picture's data goes only into `structuredContent` (mcp_apps.call_result), under `map`, `ontology` and `products`. The
tool's function hands what it computed to `keep()` while the call runs (a ContextVar that mcp_apps.structured opens
around the call; nothing is kept when no card is listening), so a picture never re-reads Fabric.

How the card draws it. The drawing is the chat demo's own (fabric_backend/static/chat-demo.js, "pictures, drawn from the
plan"): the same placement search (two columns, the shortest lines, no line crossing another or running through a table,
each data product's tables together) and the same picture() that draws tables, links, key marks, "no key" tags and
groups. The card does not carry a copy: picture_js() cuts that part out of chat-demo.js when the card is built, with three
marked additions (bigger cells for the key columns, a data-table and a data-id on each table and link for tests and the
list below it, and a second line under a table's name). If chat-demo.js changes so that a cut or an addition no longer
fits, building the card raises, and tests/test_n170_card_pictures.py fails. On top of it the card adds what the chat
demo has no room for: one label per link with the rule as a pill, the state and the column pair.

Under every picture is the same content as a list (each table, each link with its state), which a screen reader and the
keyboard reach; focusing a line marks its link or table in the picture.
"""
from __future__ import annotations

import contextvars
import re
from pathlib import Path


DEMO_JS = Path(__file__).with_name("static") / "chat-demo.js"
MAX_TABLES = 60                 # a picture beyond this is not readable at a card's width; the list then says so
MAX_LINKS = 120
EXTRA_TOOLS = ("ontology_draft", "domain_draft")    # tools that got a card in n170 (the build card)
PICTURE_TOOLS = ("plan_backend", "validate_plan", "review_plan", "ontology_draft", "create_ontology", "domain_draft")

_STASH: contextvars.ContextVar[dict | None] = contextvars.ContextVar("krusgraph_card_pictures", default=None)


# ------------------------------------------------------------------ handing data from the tool to the card -----------

def begin():
    """Opens a stash for one call (mcp_apps.structured does this around a tool in PICTURE_TOOLS); returns the token."""
    return _STASH.set({})


def end(token) -> dict:
    stash = _STASH.get() or {}
    _STASH.reset(token)
    return stash


def keep(name: str, build) -> None:
    """While a card listens, stores build() under `name`. `build` is a callable so that nothing is computed with the flag
    off. A picture must never change or break the answer: an error here leaves the picture out."""
    stash = _STASH.get()
    if stash is None:
        return
    try:
        stash[name] = build()
    except Exception:                                                # noqa: BLE001
        stash.pop(name, None)


def extras(tool: str, answer: dict, stash: dict) -> dict:
    """What the card gets in structuredContent besides the answer: {map?, ontology?, products?}. Only for an answer
    without an error, and only what the tool computed (stash) or answered."""
    if not isinstance(answer, dict) or answer.get("error") or answer.get("choose_schema"):
        return {}
    out = {}
    if tool == "review_plan":
        m = map_from_review(answer)
        if m:
            out["map"] = m
    elif tool in ("plan_backend", "validate_plan") and stash.get("map"):
        out["map"] = stash["map"]
    elif tool in ("ontology_draft", "create_ontology") and stash.get("ontology"):
        if tool == "create_ontology" and answer.get("dry_run") is not True:
            return {}
        out["ontology"] = stash["ontology"]
    elif tool == "domain_draft" and stash.get("map"):
        p = products_from(answer, stash["map"])
        if p:
            out["map"], out["products"] = stash["map"], p
    return out


# ------------------------------------------------------------------ the map ------------------------------------------

def _rel_id(source: str, cols, target: str) -> str:
    """The relationship's id, the review file's form without its "rel:" prefix: source.col+col>target."""
    return f"{source}.{'+'.join(cols)}>{target}"


def _state_of_check(verdict: str | None) -> str:
    """evidence._rel_status in the card's words: passed, warning (holds, but the target key is not unique), failed,
    empty (no row has a value, so nothing was counted)."""
    if not verdict:
        return "not_checked"
    if verdict.startswith("holds"):
        return "warning" if "; but" in verdict else "passed"
    return "empty" if verdict.startswith("no rows with a value") else "failed"


def map_from_plan(plan, checks: dict | None = None) -> dict:
    """The map of a plan (infer.Plan): tables with key columns and rule, relationships with rule and, when validate_plan's
    full result `checks` is given, each relationship's state and counts. A relationship the check did not reach (the
    max_items budget) is not_checked."""
    counted = {}
    if checks:
        for r in checks.get("relationships") or []:
            counted[_rel_id(r["source"], r["columns"], r["target"]).lower()] = r
    keyed = {k.lower(): v for k, v in plan.keys.items()}
    tables = []
    for t in list(plan.schema)[:MAX_TABLES]:
        cols, rule = keyed.get(t.name.lower(), ([], None))
        tables.append({"name": t.name, "key": list(cols), "key_rule": rule or "K3", "columns": len(t.columns)})
    names = {t["name"].lower() for t in tables}
    rels = []
    for r in plan.relationships:
        if r.source.lower() not in names or r.target.lower() not in names or len(rels) >= MAX_LINKS:
            continue
        rid = _rel_id(r.source, r.source_cols, r.target)
        entry = {"id": rid, "source": r.source, "source_cols": list(r.source_cols), "target": r.target,
                 "target_cols": list(r.target_cols), "rule": r.rule}
        if checks is not None:
            c = counted.get(rid.lower())
            entry["state"] = _state_of_check(c.get("verdict")) if c else "not_checked"
            if c:
                entry["orphans"], entry["rows_with_value"] = c.get("orphans"), c.get("rows_with_value")
        rels.append(entry)
    for x in getattr(plan, "proposed", None) or []:                # n172: a candidate R5 could not count: grey, "not counted"
        if not x.get("not_counted") or x["source"].lower() not in names or x["target"].lower() not in names or len(rels) >= MAX_LINKS:
            continue
        rels.append({"id": _rel_id(x["source"], x["source_cols"], x["target"]), "source": x["source"],
                     "source_cols": list(x["source_cols"]), "target": x["target"], "target_cols": list(x["target_cols"]),
                     "rule": x.get("rule") or "R5", "state": "not_counted", "proposed": True, "why_not_counted": x["not_counted"]})
    out = {"tables": tables, "relationships": rels, "checked": checks is not None}
    if len(plan.schema) > MAX_TABLES or sum(1 for r in rels if not r.get("proposed")) < len(plan.relationships):
        out["left_out"] = (f"The picture shows {len(tables)} of {len(plan.schema)} tables and {sum(1 for r in rels if not r.get('proposed'))} of "
                           f"{len(plan.relationships)} relationships; the answer has them all.")
    return out


def map_from_review(answer: dict) -> dict | None:
    """review_plan's map, from its own answer: review.snapshot (tables, keys, relationships) and review.items (the
    review status a person gave and the check status)."""
    rv = answer.get("review")
    snap = rv.get("snapshot") if isinstance(rv, dict) else None
    if not isinstance(snap, dict) or not isinstance(snap.get("tables"), dict):
        return None
    items = {it.get("id"): it for it in rv.get("items") or [] if isinstance(it, dict)}
    tables = []
    for name, t in list(snap["tables"].items())[:MAX_TABLES]:
        t = t if isinstance(t, dict) else {}
        key = list(t.get("key") or [])
        entry = {"name": name, "key": key, "key_rule": t.get("key_rule") or "K3", "columns": len(t.get("columns") or {})}
        it = items.get(f"key:{name}")
        if it:
            entry["review"] = it.get("review")
        tables.append(entry)
    names = {t["name"].lower() for t in tables}
    rels = []
    for r in snap.get("relationships") or []:
        if not isinstance(r, dict) or str(r.get("source", "")).lower() not in names or str(r.get("target", "")).lower() not in names:
            continue
        if len(rels) >= MAX_LINKS:
            break
        rid = _rel_id(r["source"], r.get("columns") or [], r["target"])
        it = items.get("rel:" + rid) or {}
        c = it.get("check") if isinstance(it.get("check"), dict) else {}
        status, res = c.get("status"), c.get("result") if isinstance(c.get("result"), dict) else {}
        state = {"passed": "passed", "failed": "failed", "stale": "stale"}.get(status, "not_checked")
        entry = {"id": rid, "source": r["source"], "source_cols": list(r.get("columns") or []), "target": r["target"],
                 "target_cols": list(r.get("target_columns") or []), "rule": r.get("rule"), "state": state,
                 "review": it.get("review") or "proposed"}
        if state != "not_checked":
            entry["orphans"], entry["rows_with_value"] = res.get("orphans"), res.get("rows_with_value")
        rels.append(entry)
    return {"tables": tables, "relationships": rels, "checked": True, "reviewed": True}


# ------------------------------------------------------------------ the ontology proposal ----------------------------

def ontology_from(bindings: list[dict], summary: dict) -> dict:
    """The ontology picture's data from ontology.bindings() and ontology.summary(): each entity type with its table, its
    key or why it has none (the summary's own note for it), and each relationship type; a relationship over two or more
    columns is shown but marked as not in the ontology's relationship types (the summary says why)."""
    notes = [n for n in (summary or {}).get("notes") or [] if isinstance(n, str)]
    by_entity = {b["entity_type"]: b for b in bindings}
    entities, links = [], []
    for b in bindings:
        table = b["table"].split(".", 1)[-1]
        why = next((n for n in notes if n.startswith(b["entity_type"] + ":")), None)
        entities.append({"name": b["entity_type"], "table": table, "key": b.get("key"), "key_columns": list(b.get("key_columns") or []),
                         "key_rule": b.get("key_rule"), "why_no_key": why if not b.get("key") else None})
        for r in b.get("relationships") or []:
            target = by_entity.get(r.get("to"))
            if not target:
                continue
            single = len(r.get("from_columns") or []) == 1 and len(r.get("to_columns") or []) == 1
            links.append({"name": r.get("name"), "source": table, "target": target["table"].split(".", 1)[-1],
                          "source_entity": b["entity_type"], "target_entity": r["to"],
                          "source_cols": list(r.get("from_columns") or []), "target_cols": list(r.get("to_columns") or []),
                          "rule": r.get("rule"), "in_ontology": single})
    return {"entities": entities[:MAX_TABLES], "links": links[:MAX_LINKS],
            "entity_types": (summary or {}).get("entity_types"), "with_key": (summary or {}).get("with_key"),
            "relationship_types": (summary or {}).get("relationship_types")}


# ------------------------------------------------------------------ the data products --------------------------------

def products_from(answer: dict, plan_map: dict) -> dict | None:
    """domain_draft's proposal as the data products card: each domain with its tables and the reason for its name, the
    interfaces between them and the tables left out with the tool's reason. Owners: none is chosen (the tool proposes
    none). Only what the answer holds."""
    domains = [d for d in answer.get("domains") or [] if isinstance(d, dict) and d.get("tables")]
    if not domains:
        return None
    return {"products": [{"name": d.get("name"), "slug": d.get("slug") or d.get("name"), "tables": list(d["tables"]),
                          "why": d.get("name_reason"), "owner": None} for d in domains],
            "interfaces": [{k: i.get(k) for k in ("consumer", "provider", "source", "source_cols", "target", "target_cols", "rule")}
                           for i in answer.get("interfaces") or [] if isinstance(i, dict)],
            "unassigned": [{"table": u.get("table"), "reason": u.get("reason")} for u in answer.get("unassigned") or [] if isinstance(u, dict)]}


# ------------------------------------------------------------------ the drawing: the chat demo's own -----------------
# The cut: from the placement's constants to the end of svg(), the part of chat-demo.js headed "pictures, drawn from the
# plan". Each addition replaces text that must occur exactly once.
_CUT_FROM = "  var COLS = 2,"
_CUT_TO = "  function svg(id, labelled) {"
_ADDITIONS = [
    # bigger cells: room for the key columns under a table's name and for a label on each link
    (re.compile(r"NW = \d+, NH = \d+, GX = \d+, GY = \d+"), "NW = 156, NH = 46, GX = 210, GY = 66"),
    # a data-table on each table, and a class for its state
    ("'<g class=\"kgc-n' + (no ? ' nokey' : '') + '\"><rect x=\"'",
     "'<g class=\"kgc-n' + (no ? ' nokey' : '') + (nd.cls ? ' ' + nd.cls : '') + '\" data-table=\"' + esc(nd.table) + '\"><rect x=\"'"),
    # a second line under the name (the key columns)
    ("(p.y + NH / 2 + 4.5) + '\" text-anchor=\"middle\">' + esc(nd.label) + '</text>';",
     "(p.y + (nd.sub ? NH / 2 - 3 : NH / 2 + 4.5)) + '\" text-anchor=\"middle\">' + esc(nd.label) + '</text>' + "
     "(nd.sub ? '<text class=\"kgc-sub\" x=\"' + (p.x + NW / 2) + '\" y=\"' + (p.y + NH / 2 + 13) + '\" text-anchor=\"middle\">' + esc(nd.sub) + '</text>' : '');"),
    # picture() gives the index of its drawing in pics, not the chat's figure (which needs svg() and the zoom button)
    ("    return '<figure class=\"kgc-pic\">' + svg(id, true) + '<button class=\"kgc-zoom\" type=\"button\" data-pic=\"' + id + '\">Larger picture</button></figure>';",
     "    return id;"),
    # n172: a plan of more than 9 tables, which the chat demo places in plan order, is improved by swapping tables
    # between cells (and into empty cells of one more row) while the chat demo's own cost falls: the lines' length,
    # 80 per line through a table, 40 per crossing. Bounded: at most KG_SWEEPS passes over every pair.
    ("    if (!at) at = names.map(function (_, i) { return i; });   // a larger plan: in plan order",
     "    if (!at) at = kgImprove(names.map(function (_, i) { return i; }), edges, COLS * (rows + 1));"),
    # a data-id on each link
    ("'<g class=\"kgc-e ' + (e.cls || '') + '\">",
     "'<g class=\"kgc-e ' + (e.cls || '') + '\"' + (e.id ? ' data-id=\"' + esc(e.id) + '\"' : '') + '>"),
]


KG_IMPROVE_JS = r"""
    var KG_SWEEPS = 12;
    function kgImprove(at, edges, cells) {
      function cost(at) {
        var c = 0;
        edges.forEach(function (e, i) {
          var a = centre(at[e[0]]), b = centre(at[e[1]]);
          c += Math.sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y)) / 10;
          for (var k = 0; k < at.length; k++) if (k !== e[0] && k !== e[1] && through(a, b, at[k])) c += 80;
          for (var j = i + 1; j < edges.length; j++) {
            var f = edges[j];
            if (e[0] === f[0] || e[0] === f[1] || e[1] === f[0] || e[1] === f[1]) continue;
            if (cross(a, b, centre(at[f[0]]), centre(at[f[1]]))) c += 40;
          }
        });
        return c;
      }
      var best = cost(at);
      for (var sweep = 0; sweep < KG_SWEEPS; sweep++) {
        var better = false;
        for (var i = 0; i < at.length; i++) {
          for (var c = 0; c < cells; c++) {
            if (c === at[i]) continue;
            var other = at.indexOf(c), old = at[i];
            at[i] = c; if (other >= 0) at[other] = old;
            var now = cost(at);
            if (now < best - 1e-9) { best = now; better = true; }
            else { at[i] = old; if (other >= 0) at[other] = c; }
          }
        }
        if (!better) break;
      }
      return at;
    }
"""


def picture_js() -> str:
    """kgDemoPicture(P): the chat demo's placement and picture(), cut from chat-demo.js, with the additions above.
    Returns { picture, placement, cellXY, centre, pics, NW, NH, PORT }. Raises when chat-demo.js no longer fits."""
    src = DEMO_JS.read_text(encoding="utf-8")
    a, b = src.find(_CUT_FROM), src.find(_CUT_TO)
    if a < 0 or b < a:
        raise RuntimeError("chat-demo.js: the pictures part was not found; mcp_apps_pictures must follow it")
    code = src[a:b]
    for old, new in _ADDITIONS:
        if isinstance(old, re.Pattern):
            code, n = old.subn(new, code)
        else:
            n = code.count(old)
            code = code.replace(old, new)
        if n != 1:
            raise RuntimeError(f"chat-demo.js changed: an addition fits {n} times instead of once: {getattr(old, 'pattern', old)[:60]}")
    for needed in ("function placement()", "function picture(", "function cellXY(", "function centre("):
        if needed not in code:
            raise RuntimeError(f"chat-demo.js: {needed} is not in the pictures part")
    return ("  // ---- the chat demo's pictures, cut from fabric_backend/static/chat-demo.js when the card is built (n170)\n"
            "  function kgDemoPicture(P) {\n"
            "    var pics = [];\n"
            + KG_IMPROVE_JS +
            "    function esc(s) { return String(s).replace(/[&<>\"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '\"': '&quot;', \"'\": '&#39;' }[c]; }); }\n"
            + code +
            "    return { picture: picture, placement: placement, cellXY: cellXY, centre: centre, pics: pics, NW: NW, NH: NH, PORT: PORT };\n"
            "  }\n")


# The card's part around it: the labels on the links, the list under the picture, and the three sections. Needs el()
# and readable() of the card (mcp_apps.READ_JS) and renderActions (mcp_apps_build.ACTIONS_JS) for the products' buttons.
DRAW_JS = r"""
  var STATE_WORD = { passed: "passed", failed: "failed", warning: "holds, but the target key is not unique",
                     empty: "no row has a value", stale: "check is stale", not_checked: "not checked",
                     not_counted: "not counted: the counting query could not run" };
  function kgPlural(n, one, many) { return n + " " + (n === 1 ? one : (many || one + "s")); }
  function kgPair(r) {
    var s = (r.source_cols || []).join("+"), t = (r.target_cols || []).join("+");
    return s === t || !t ? s : s + " \u2192 " + t;
  }
  function kgRelText(r) {
    var t = r.source + "." + (r.source_cols || []).join("+") + " \u2192 " + r.target + "." + (r.target_cols || []).join("+") + ", rule " + r.rule;
    if (r.state) t += ", " + STATE_WORD[r.state] + (r.orphans != null && r.state !== "not_checked" && r.state !== "not_counted" ? " (" + kgPlural(Number(r.orphans) || 0, "orphan") + ", " + (r.rows_with_value != null ? r.rows_with_value + " rows with a value" : "") + ")" : "");
    if (r.review && r.review !== "proposed") t += ", " + r.review;
    return t;
  }
  function kgLabelLines(r) {
    var top = r.rule || "";
    if (r.state === "failed") top += " \u2715 " + kgPlural(Number(r.orphans) || 0, "orphan");
    else if (r.state === "passed") top += " \u2713";
    else if (r.state === "warning") top += " !";
    else if (r.state === "not_counted") top += " not counted";
    if (r.review === "rejected") top += " rejected";
    else if (r.review === "accepted") top += " accepted";
    else if (r.review === "open") top += " open";
    return [top, kgPair(r)];
  }
  // svgText: the picture's inner SVG from the chat demo's picture(); labels: [{id, lines, cls, a, b}] drawn on top.
  // n172: each label sits on its own line: at the middle of the drawn segment (between the two tables' edges), else
  // slid along the line, else with its first line only (the rule and the state); it never covers a table, another label
  // or the picture's edge. A label that fits nowhere is left out of the picture (data-unlabelled on the line) and is in
  // the list under it. Founder, 8 November 2026: a horizontal link's label floated above the map and covered a table.
  function kgSeg(D, a, b) {                      // the drawn segment, as picture() clips it at the tables' edges
    var dx = b.x - a.x, dy = b.y - a.y;
    var out1 = function (right) { return Math.min(dx ? (D.NW / 2 + 1 + (right ? -D.PORT : D.PORT)) / Math.abs(dx) : Infinity, dy ? (D.NH / 2 + 1) / Math.abs(dy) : Infinity); };
    var ta = out1(dx > 0), tb = out1(dx < 0);
    return { p: { x: a.x + dx * ta, y: a.y + dy * ta }, q: { x: b.x - dx * tb, y: b.y - dy * tb } };
  }
  var KG_ALONG = [0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74, 0.18, 0.82];
  function kgSvg(D, desc, labels, kind) {
    var L = D.placement(), last = D.pics[D.pics.length - 1], rects = [], out = [], skipped = [];
    Object.keys(L.cell).forEach(function (t) { var p = D.cellXY(L.cell[t]); rects.push({ x: p.x - 3, y: p.y - 9, w: D.NW + 6, h: D.NH + 12 }); });
    function hits(r) {
      if (r.x < 1 || r.x + r.w > L.width - 1) return true;
      return rects.some(function (o) { return r.x < o.x + o.w && o.x < r.x + r.w && r.y < o.y + o.h && o.y < r.y + r.h; });
    }
    function size(lines) { return { w: Math.max(lines[0].length * 6.6, (lines[1] || "").length * 6.1) + 14, h: lines[1] ? 30 : 17 }; }
    var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
    labels.forEach(function (lb) {
      var seg = kgSeg(D, lb.a, lb.b), best = null, lines = null;
      [lb.lines, lb.lines.slice(0, 1)].some(function (ls) {
        var sz = size(ls);
        return KG_ALONG.some(function (t) {
          var cx = seg.p.x + (seg.q.x - seg.p.x) * t, cy = seg.p.y + (seg.q.y - seg.p.y) * t;
          var r = { x: cx - sz.w / 2, y: cy - sz.h / 2, w: sz.w, h: sz.h, cx: cx, cy: cy };
          if (hits(r)) return false;
          best = r; lines = ls; return true;
        });
      });
      if (!best) { skipped.push(lb.id); return; }
      rects.push(best);
      out.push('<g class="kgc-lab ' + lb.cls + '" data-id="' + esc(lb.id) + '" data-cx="' + best.cx + '" data-cy="' + best.cy + '"><rect x="' + best.x + '" y="' + best.y + '" width="' + best.w + '" height="' + best.h + '" rx="8"/>' +
               '<text class="r" x="' + best.cx + '" y="' + (best.y + 12.5) + '" text-anchor="middle">' + esc(lines[0]) + '</text>' +
               (lines[1] ? '<text x="' + best.cx + '" y="' + (best.y + 25) + '" text-anchor="middle">' + esc(lines[1]) + '</text>' : '') + '</g>');
    });
    var bottom = L.height;
    rects.forEach(function (r) { bottom = Math.max(bottom, r.y + r.h + 4); });
    var top = 0; rects.forEach(function (r) { top = Math.min(top, r.y - 4); });
    var wrap = document.createElement("div"); wrap.className = "kg-pic";
    var svg = kgParse(last.svg + out.join(""));
    svg.setAttribute("class", "kgc-svg " + kind);
    svg.setAttribute("viewBox", "0 " + top + " " + L.width + " " + (bottom - top));
    svg.setAttribute("width", L.width); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", desc);
    if (skipped.length) svg.setAttribute("data-unlabelled", skipped.join(" "));
    wrap.appendChild(svg);
    return wrap;
  }
  // The chat demo builds its drawing as text, every value escaped. The card turns it into nodes with DOMParser (an
  // inert document: nothing in it runs) and keeps only the elements and attributes a drawing has, before it is adopted.
  var KG_TAGS = { svg: 1, g: 1, rect: 1, text: 1, line: 1, circle: 1, path: 1, title: 1 };
  var KG_ATTRS = { "class": 1, x: 1, y: 1, x1: 1, y1: 1, x2: 1, y2: 1, cx: 1, cy: 1, r: 1, rx: 1, width: 1, height: 1, d: 1,
                   "text-anchor": 1, "data-table": 1, "data-id": 1, "data-cx": 1, "data-cy": 1 };
  function kgParse(inner) {
    var doc = new DOMParser().parseFromString("<svg>" + inner + "</svg>", "text/html");
    var root = doc.body.firstElementChild;
    (function clean(node) {
      Array.prototype.slice.call(node.children).forEach(function (c) {
        if (!KG_TAGS[c.localName]) { c.remove(); return; }
        Array.prototype.slice.call(c.attributes).forEach(function (a) { if (!KG_ATTRS[a.name]) c.removeAttribute(a.name); });
        clean(c);
      });
    })(root);
    Array.prototype.slice.call(root.attributes).forEach(function (a) { root.removeAttribute(a.name); });
    return document.importNode(root, true);
  }
  function kgPortOf(D, L, t) { var c = D.centre(L.cell[t]); return { x: c.x + D.PORT, y: c.y }; }
  function kgPlanP(tables, rels, groups) {
    return { tables: tables.map(function (t) { return { name: t }; }),
             relationships: rels.map(function (r) { return { source: r.source, target: r.target }; }), suggestions: [],
             drafts: { as_is: { domains: { domains: (groups || []).map(function (g) { return { tables: g }; }) } } } };
  }
  // a list item that marks its picture element while it has the focus or the pointer
  function kgItem(list, text, pic, sel, cls) {
    var li = el("li", text, cls); li.tabIndex = 0;
    var on = function (yes) { pic.querySelectorAll(sel).forEach(function (x) { x.classList.toggle("lit", yes); }); };
    li.addEventListener("focus", function () { on(true); }); li.addEventListener("blur", function () { on(false); });
    li.addEventListener("mouseenter", function () { on(true); }); li.addEventListener("mouseleave", function () { on(false); });
    list.appendChild(li);
  }
  function kgCss(s) { return String(s).replace(/["\\]/g, "\\$&"); }
  // the map of a plan, of its checks or of its review
  function drawMap(box, m) {
    box.textContent = "";
    if (!isObj(m) || !Array.isArray(m.tables) || !m.tables.length) { box.hidden = true; return ""; }
    var rels = (m.relationships || []).filter(isObj), names = m.tables.map(function (t) { return t.name; });
    var D = kgDemoPicture(kgPlanP(names, rels)), L = D.placement();
    var keyless = m.tables.filter(function (t) { return !(t.key || []).length; }).map(function (t) { return t.name; });
    var counts = { passed: 0, failed: 0, not_checked: 0, not_counted: 0 };
    rels.forEach(function (r) { if (r.state === "passed") counts.passed++; else if (r.state === "failed") counts.failed++; else if (r.state === "not_counted") counts.not_counted++; else if (r.state) counts.not_checked++; });
    var desc = "Map of " + kgPlural(m.tables.length, "table") + " and " + kgPlural(rels.length, "relationship") +
               (m.checked ? ": " + counts.passed + " passed, " + counts.failed + " failed, " + counts.not_checked + " not checked" : "") +
               (counts.not_counted ? "; " + counts.not_counted + " not counted" : "") +
               (keyless.length ? "; no key: " + keyless.join(", ") : "") + ".";
    D.picture(desc, m.tables.map(function (t) {
      var k = t.key || [];
      return { table: t.name, label: t.name, key: k.length ? true : false, sub: k.length ? k.join(" + ") : "",
               cls: t.review === "rejected" ? "rejected" : "" };
    }), rels.map(function (r) {
      var cls = (r.state ? "st-" + r.state : "") + (r.review === "rejected" ? " rejected" : (r.review && r.review !== "proposed" ? " rv-" + r.review : ""));
      return { source: r.source, target: r.target, id: r.id, cls: cls };
    }));
    var pic = kgSvg(D, desc, rels.filter(function (r) { return r.source in L.cell && r.target in L.cell; }).map(function (r) {
      return { id: r.id, lines: kgLabelLines(r), cls: (r.state ? "st-" + r.state : "") + (r.review === "rejected" ? " rejected" : ""),
               a: kgPortOf(D, L, r.source), b: kgPortOf(D, L, r.target) };
    }), "kg-map");
    box.appendChild(el("h2", "Map of the tables and links", "muted"));
    box.appendChild(pic);
    if (m.checked || counts.not_counted) {
      var legend = el("p", null, "muted kg-legend");
      (m.checked ? [["passed", "passed"], ["failed", "failed (orphans)"], ["not_checked", "not checked"]] : []).concat(
        counts.not_counted ? [["not_counted", "not counted"]] : []).forEach(function (x) {
        var s = el("span", x[1], "lg st-" + x[0]); legend.appendChild(s);
      });
      if (m.reviewed) legend.appendChild(el("span", "dashed: rejected", "lg"));
      box.appendChild(legend);
    }
    var list = el("ul", null, "kg-list"); list.setAttribute("aria-label", "The map as a list");
    m.tables.forEach(function (t) {
      kgItem(list, t.name + ": " + ((t.key || []).length ? "key " + t.key.join(" + ") + " (" + t.key_rule + ")" : "no key (" + (t.key_rule || "K3") + "), query only") +
             (t.review && t.review !== "proposed" ? ", " + t.review : ""), pic, '[data-table="' + kgCss(t.name) + '"]', "");
    });
    rels.forEach(function (r) { kgItem(list, kgRelText(r), pic, '[data-id="' + kgCss(r.id) + '"]', r.state === "failed" ? "warn" : ""); });
    var more = el("details", null, "kg-more"); more.appendChild(el("summary", "The map as a list"));
    more.appendChild(list); box.appendChild(more);
    if (readable(m.left_out)) box.appendChild(el("p", m.left_out, "muted"));
    box.hidden = false;
    return desc;
  }
  // the ontology proposal (a draft or a dry run)
  function drawOntology(box, o) {
    box.textContent = "";
    if (!isObj(o) || !Array.isArray(o.entities) || !o.entities.length) { box.hidden = true; return ""; }
    var links = (o.links || []).filter(isObj), without = o.entities.filter(function (x) { return !x.key; });
    var D = kgDemoPicture(kgPlanP(o.entities.map(function (x) { return x.table; }), links)), L = D.placement();
    var desc = "The ontology proposal: " + kgPlural(o.entities.length, "entity type") + ", " + (o.entities.length - without.length) + " with a key" +
               (without.length ? ", " + without.map(function (x) { return x.name; }).join(" and ") + " without one" : "") + "; " +
               kgPlural(links.filter(function (l) { return l.in_ontology; }).length, "relationship type") + ".";
    D.picture(desc, o.entities.map(function (x) {
      return { table: x.table, label: x.name, key: !!x.key, sub: x.key ? x.key : ((x.key_columns || []).length > 1 ? "composite: " + x.key_columns.join(" + ") : "") };
    }), links.map(function (l) { return { source: l.source, target: l.target, id: l.source_entity + ">" + l.name, cls: l.in_ontology ? "" : "off" }; }));
    var pic = kgSvg(D, desc, links.filter(function (l) { return l.source in L.cell && l.target in L.cell; }).map(function (l) {
      return { id: l.source_entity + ">" + l.name, lines: [l.rule + (l.in_ontology ? "" : " \u00b7 not a type"), kgPair(l)],
               cls: l.in_ontology ? "" : "st-not_checked", a: kgPortOf(D, L, l.source), b: kgPortOf(D, L, l.target) };
    }), "kg-onto");
    box.appendChild(el("h2", "Ontology proposal", "muted"));
    box.appendChild(pic);
    var why = el("ul", null, "kg-why");
    without.forEach(function (x) { if (readable(x.why_no_key)) why.appendChild(el("li", x.why_no_key)); });
    if (why.children.length) { box.appendChild(el("p", "Why " + (without.length === 1 ? "one entity type has" : without.length + " entity types have") + " no key:", "muted")); box.appendChild(why); }
    var list = el("ul", null, "kg-list"); list.setAttribute("aria-label", "The ontology as a list");
    o.entities.forEach(function (x) {
      kgItem(list, x.name + " (table " + x.table + "): " + (x.key ? "key " + x.key + " (" + x.key_rule + ")" : "no key"), pic, '[data-table="' + kgCss(x.table) + '"]', x.key ? "" : "warn");
    });
    links.forEach(function (l) {
      kgItem(list, l.source_entity + " " + l.name + " " + l.target_entity + ": " + l.source + "." + l.source_cols.join("+") + " \u2192 " + l.target + "." + l.target_cols.join("+") +
             ", rule " + l.rule + (l.in_ontology ? "" : "; over two or more columns, so not a relationship type"), pic, '[data-id="' + kgCss(l.source_entity + ">" + l.name) + '"]', "");
    });
    var more = el("details", null, "kg-more"); more.appendChild(el("summary", "The ontology as a list"));
    more.appendChild(list); box.appendChild(more);
    box.hidden = false;
    return desc;
  }
  // the data products. Each product is a card with its tables, the owner nobody has chosen yet and the
  // Builder's dry-run buttons for its tables (the answer's actions with that product's slug).
  function drawProducts(box, d, m, answer, callArgs) {
    box.textContent = "";
    if (!isObj(d) || !Array.isArray(d.products) || !d.products.length || !isObj(m)) { box.hidden = true; return ""; }
    var rels = (m.relationships || []).filter(isObj), names = (m.tables || []).map(function (t) { return t.name; });
    var ifaces = (d.interfaces || []).filter(isObj), out = (d.unassigned || []).filter(isObj);
    var isIface = function (r) { return ifaces.some(function (i) { return i.source === r.source && i.target === r.target && (i.source_cols || []).join("+") === (r.source_cols || []).join("+"); }); };
    var D = kgDemoPicture(kgPlanP(names, rels, d.products.map(function (p) { return p.tables; }))), L = D.placement();
    var desc = "The data products: " + d.products.map(function (p) { return p.name + " around " + p.tables.join(", "); }).join("; ") +
               (ifaces.length ? "; " + kgPlural(ifaces.length, "interface") + " between them" : "") +
               (out.length ? "; outside them: " + out.map(function (u) { return u.table; }).join(", ") : "") + ".";
    var keyless = {}; (m.tables || []).forEach(function (t) { if (!(t.key || []).length) keyless[t.name] = 1; });
    var outside = {}; out.forEach(function (u) { outside[u.table] = 1; });
    D.picture(desc, names.map(function (t) { return { table: t, label: t, key: outside[t] && keyless[t] ? false : undefined }; }),
              rels.map(function (r) { return { source: r.source, target: r.target, id: r.id, cls: isIface(r) ? "iface" : "faint" }; }),
              d.products.map(function (p, i) { return { name: p.name, tables: p.tables, cls: i % 2 ? "b" : "a" }; }));
    var pic = kgSvg(D, desc, ifaces.filter(function (i) { return i.source in L.cell && i.target in L.cell; }).map(function (i) {
      return { id: i.source + "." + (i.source_cols || []).join("+") + ">" + i.target, lines: ["interface \u00b7 " + i.rule, kgPair(i)], cls: "iface",
               a: kgPortOf(D, L, i.source), b: kgPortOf(D, L, i.target) };
    }), "kg-products");
    box.appendChild(el("h2", "Data products", "muted"));
    box.appendChild(pic);
    var cards = el("div", null, "kg-products-cards");
    d.products.forEach(function (p) {
      var c = el("section", null, "kg-product"); c.setAttribute("data-product", p.slug);
      c.appendChild(el("h3", p.name));
      c.appendChild(el("p", kgPlural(p.tables.length, "table") + ": " + p.tables.join(", ")));
      if (readable(p.why)) c.appendChild(el("p", p.why, "muted"));
      c.appendChild(el("p", "Owner: not chosen yet. You choose the owner; your Fabric admin creates the domain.", "muted"));
      var acts = el("div"); renderActions(answer, acts, callArgs, p.slug); c.appendChild(acts);
      cards.appendChild(c);
    });
    box.appendChild(cards);
    if (ifaces.length) {
      var il = el("ul", null, "kg-list"); il.setAttribute("aria-label", "Interfaces between the data products");
      ifaces.forEach(function (i) { kgItem(il, i.consumer + " uses " + i.provider + ": " + i.source + "." + (i.source_cols || []).join("+") + " \u2192 " + i.target + ", rule " + i.rule, pic,
                                           '[data-id="' + kgCss(i.source + "." + (i.source_cols || []).join("+") + ">" + i.target) + '"]', ""); });
      box.appendChild(el("p", "Interfaces:", "muted")); box.appendChild(il);
    }
    out.forEach(function (u) { box.appendChild(el("p", "Outside every product: " + u.table + ": " + u.reason, "muted")); });
    box.hidden = false;
    return desc;
  }
"""

CSS = """
.kg-pic { width: 100%; overflow-x: auto }
.kg-pic svg { display: block; max-width: 100%; height: auto; font-family: var(--kg-font) }
.kgc-n rect { fill: var(--kg-card); stroke: var(--kg-line); stroke-width: 1.3 }
.kgc-n text { fill: var(--kg-ink); font-size: 13px; font-weight: 650 }
.kgc-n .kgc-sub { fill: var(--kg-muted); font-size: 11px; font-weight: 500 }
.kgc-n.nokey rect { stroke-dasharray: 4 3 }
.kgc-n.rejected { opacity: .6 }
.kgc-key circle { fill: var(--kg-bg); stroke: var(--kg-pic-accent) ; stroke-width: 1.4 }
.kgc-key .k { fill: none; stroke: var(--kg-pic-accent); stroke-width: 1.4 }
.kgc-key circle.k { fill: none }
.kgc-nk rect { fill: var(--kg-bg); stroke: var(--kg-warn); stroke-width: 1 }
.kgc-nk text { fill: var(--kg-warn); font-size: 9.5px; font-weight: 650 }
.kgc-e line { stroke: var(--kg-pic-edge); stroke-width: 1.8 }
.kgc-e circle { fill: var(--kg-pic-edge) }
.kgc-e.st-passed line { stroke: var(--kg-ok) } .kgc-e.st-passed circle { fill: var(--kg-ok) }
.kgc-e.st-failed line { stroke: var(--kg-bad); stroke-width: 2.6 } .kgc-e.st-failed circle { fill: var(--kg-bad) }
.kgc-e.st-warning line, .kgc-e.st-stale line { stroke: var(--kg-warn) }
.kgc-e.st-not_checked line, .kgc-e.st-empty line, .kgc-e.st-not_counted line { stroke: var(--kg-muted); stroke-dasharray: 2 3 }
.kgc-e.st-not_counted circle { fill: var(--kg-muted) }
.kgc-e.rejected line, .kgc-e.off line { stroke-dasharray: 6 4; opacity: .65 }
.kgc-e.faint line { opacity: .35 }
.kgc-e.iface line { stroke-width: 3 }
.kgc-grp rect { fill: var(--kg-pic-grp-a); stroke: none }
.kgc-grp.b rect { fill: var(--kg-pic-grp-b) }
.kgc-grp text { fill: var(--kg-ink); font-size: 11.5px; font-weight: 650; paint-order: stroke; stroke: var(--kg-bg); stroke-width: 3px }
.kgc-lab rect { fill: var(--kg-bg); stroke: var(--kg-line); stroke-width: 1 }
.kgc-lab text { fill: var(--kg-ink); font-size: 10.5px }
.kgc-lab text.r { font-weight: 700 }
.kgc-lab.st-passed rect { stroke: var(--kg-ok) } .kgc-lab.st-passed text.r { fill: var(--kg-ok) }
.kgc-lab.st-failed rect { stroke: var(--kg-bad); stroke-width: 1.6 } .kgc-lab.st-failed text.r { fill: var(--kg-bad) }
.kgc-lab.st-not_checked text.r, .kgc-lab.st-empty text.r, .kgc-lab.st-not_counted text.r { fill: var(--kg-muted) }
.kgc-lab.st-not_counted rect { stroke-dasharray: 3 2 }
.kgc-lab.rejected { opacity: .7 }
.kg-pic .lit rect, .kg-pic .lit line { stroke: var(--kg-pic-accent) !important; stroke-width: 3 !important }
.kg-legend { display: flex; flex-wrap: wrap; gap: 4px 12px }
.kg-legend .lg::before { content: ""; display: inline-block; width: 14px; height: 3px; margin-right: 5px; vertical-align: middle; background: var(--kg-pic-edge) }
.kg-legend .st-passed::before { background: var(--kg-ok) } .kg-legend .st-failed::before { background: var(--kg-bad) }
.kg-legend .st-not_checked::before, .kg-legend .st-not_counted::before { background: var(--kg-muted) }
.kg-list { font-size: 13.5px } .kg-list li:focus { outline: 2px solid var(--kg-pic-accent); outline-offset: 2px }
.kg-list li.warn { color: var(--kg-bad) }
.kg-more summary { cursor: pointer; color: var(--kg-muted); font-size: 13.5px }
.kg-products-cards { display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)) }
.kg-product { border: 1px solid var(--kg-line); border-radius: var(--kg-radius); padding: 8px 10px; display: grid; gap: 4px; min-width: 0 }
.kg-product h3 { margin: 0; font-size: 15px }
#pictures { display: grid; gap: 8px; min-width: 0 }
#pictures > section { display: grid; gap: 6px; min-width: 0 }
#pictures h2 { margin: 0; font-size: 13.5px; font-weight: 600 }
"""

# Colour tokens the pictures add; light and dark, readable on the card's background (each card's :root has the rest).
TOKENS = """
:root {
  --kg-bad: var(--color-text-danger, light-dark(#b42318, #ff9a8f));
  --kg-pic-edge: light-dark(#6c6880, #a6a2b6);
  --kg-pic-accent: var(--color-text-info, light-dark(#3a3290, #b7b0ff));
  --kg-pic-grp-a: light-dark(#fde9e4, #3a2723);
  --kg-pic-grp-b: light-dark(#e6efe7, #22302a);
}
"""


def card_js() -> str:
    return picture_js() + DRAW_JS


def card_css() -> str:
    return TOKENS + CSS


SECTION = '<div id="pictures" hidden><section id="pic-map" hidden></section><section id="pic-onto" hidden></section><section id="pic-products" hidden></section></div>'

# drawPictures(answer, callArgs): the three sections from the answer's map, ontology and products; returns what Onto
# says about the picture (the sentence the picture's description gives), or "".
RENDER_JS = r"""
  function drawPictures(d, callArgs) {
    var wrap = document.getElementById("pictures");
    if (!wrap) return "";
    var said = "";
    try {
      var hasProducts = isObj(d) && isObj(d.products);
      said = drawOntology(document.getElementById("pic-onto"), isObj(d) ? d.ontology : null) || said;
      said = drawProducts(document.getElementById("pic-products"), hasProducts ? d.products : null, isObj(d) ? d.map : null, d, callArgs) || said;
      var mapSaid = drawMap(document.getElementById("pic-map"), isObj(d) && !hasProducts ? d.map : null);
      said = mapSaid || said;
    } catch (e) {
      ["pic-map", "pic-onto", "pic-products"].forEach(function (id) { var b = document.getElementById(id); b.textContent = ""; b.hidden = true; });
      said = "";
    }
    wrap.hidden = !["pic-map", "pic-onto", "pic-products"].some(function (id) { return !document.getElementById(id).hidden; });
    return said;
  }
"""


def html_parts() -> dict[str, str]:
    """What a card puts in: its CSS, its section and its script."""
    return {"css": card_css(), "section": SECTION, "js": card_js() + RENDER_JS}
