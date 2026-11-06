"""MCP Apps, second card (round n124): review_plan's answer as an ER diagram with the decisions still to make.

Behind the same flag as the n119 card (KRUSGRAPH_MCP_APPS, off unless "1"); with the flag off nothing here reaches the
server. It follows `mcp_apps.py` and the specification read there (modelcontextprotocol/ext-apps,
specification/2026-01-26/apps.mdx, Status: Stable): a `ui://` resource served as `text/html;profile=mcp-app` through the
SDK's `Apps` extension, the tool pointing at it with `_meta.ui.resourceUri` and the deprecated flat
`_meta["ui/resourceUri"]`, no `_meta.ui.csp` (the host's restrictive default applies), and the view talking to the host
with JSON-RPC 2.0 over postMessage (`ui/initialize`, `ui/notifications/initialized`, `ui/notifications/tool-input`,
`ui/notifications/tool-result`, `ui/notifications/size-changed`, `tools/call`). No code from that repository is copied.

What the card shows, all of it read from the text of review_plan's answer (the same text every client gets):

- the summary and the answer's `attention` lines;
- an ER diagram drawn as inline SVG from `review.snapshot`: one box per table with its key columns marked "key" and its
  referencing columns marked "ref", one arrow per relationship labelled with its rule and, when the item was checked,
  its counts (rows with a value, orphans); items with a failed or stale check, items left open, keyless tables and
  tables an open question is about are highlighted, rejected relationships are dashed;
- every key and relationship as text, with its review status and check verdict;
- since n136, the site's mascots (mcp_apps_mascots): Onto says the summary (the counts), the Thinker the first line of
  `attention`, the Builder the answer's `note` (what to do next with the file, also shown under "Next steps"); each
  word for word from the text answer and on the card; glad only when every item was checked, every check passed and
  nothing needs attention; a button on the card hides them;
- for each item still undecided (review "proposed" or "open") one button that asks the host to call review_plan again
  with that one decision. Nothing else can be called: the only tool the page names is review_plan, which builds the
  review file in its answer and creates nothing in Fabric.

The call a button asks for: the original call's workspace, source, schema, keys, confirmed and tables, plus `previous`
set to the review file of the answer on screen (so earlier decisions and checks are carried, the way the tool documents)
and `decisions` with the one item. `validate` and `max_items` are not carried: the checks travel in `previous`, so a
decision does not run the counting queries again.
"""
from __future__ import annotations

import json

from . import mcp_apps
from . import mcp_apps_mascots as mascots

CARD_URI = "ui://krusgraph/review-plan-card.html"
TOOL = "review_plan"
DECISIONS = ("accepted", "rejected", "open")      # what a button can record; review.REVIEW without "proposed"
UNDECIDED = ("proposed", "open")
# The arguments carried from the review_plan call into the call a button asks for; previous and decisions are the card's.
CARRIED = ("workspace", "source", "schema", "keys", "confirmed", "tables")
SVG_NS = "http://www.w3.org/2000/svg"             # a namespace name for createElementNS, not a location; nothing loads it


def tool_meta(on: bool | None = None) -> dict | None:
    """review_plan's `_meta` when the flag is on, else None (no `_meta` at all)."""
    if not (mcp_apps.enabled() if on is None else on):
        return None
    return {"ui": {"resourceUri": CARD_URI}, "ui/resourceUri": CARD_URI}


def add_to(apps) -> None:
    """Registers the card on the SDK's Apps extension that mcp_apps.extensions() builds."""
    apps.add_html_resource(CARD_URI, card_html(), name="review_plan_card", title="Plan review",
                           description="review_plan's answer as an ER diagram: each relationship with its rule and "
                                       "counts, keys marked, findings highlighted, and a button per undecided item "
                                       "that asks the host to call review_plan with that decision.",
                           prefers_border=True)


def card_html() -> str:
    """One self-contained HTML5 document: no src, href, url(), @import, fetch or other load. The diagram is SVG built in
    the page from the answer; every word on the card is in review_plan's text answer or is a label of the card itself."""
    allowed = json.dumps({TOOL: list(CARRIED)}, separators=(",", ":"))
    return (_HTML.replace("__ALLOWED__", allowed).replace("__PROTOCOL__", mcp_apps.PROTOCOL_VERSION)
            .replace("__SVGNS__", SVG_NS).replace("__DECISIONS__", json.dumps(list(DECISIONS)))
            .replace("__UNDECIDED__", json.dumps(list(UNDECIDED)))
            .replace("__MASCOT_CSS__", mascots.CSS).replace("__MASCOT_TOGGLE__", mascots.TOGGLE)
            .replace("__MASCOTS__", mascots.section()).replace("__MASCOT_JS__", mascots.JS))


_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plan review</title>
<style>
:root {
  color-scheme: light dark;
  --kg-bg: var(--color-background-primary, light-dark(#ffffff, #1b1b1f));
  --kg-card: var(--color-background-secondary, light-dark(#f6f5fb, #26252c));
  --kg-ink: var(--color-text-primary, light-dark(#1b1b1f, #f3f2f7));
  --kg-muted: var(--color-text-secondary, light-dark(#55535e, #b9b6c4));
  --kg-line: var(--color-border-primary, light-dark(#c9c5d6, #4a4753));
  --kg-edge: light-dark(#6c6880, #a6a2b6);
  --kg-accent: var(--color-text-info, light-dark(#3a3290, #b7b0ff));
  --kg-ok: var(--color-text-success, light-dark(#1d6b3a, #8fd6a6));
  --kg-warn: var(--color-text-warning, light-dark(#8a4b00, #f2c27a));
  --kg-warn-bg: light-dark(#fff3e0, #3a2c17);
  --kg-radius: var(--border-radius-lg, 14px);
  --kg-font: var(--font-sans, system-ui, -apple-system, "Segoe UI", sans-serif);
}
* { box-sizing: border-box }
html, body { margin: 0; background: var(--kg-bg); color: var(--kg-ink); font: 15px/1.45 var(--kg-font) }
main { padding: 14px 16px; display: grid; gap: 12px; min-width: 0 }
h1 { margin: 0; font-size: 17px; font-weight: 650 }
h2 { margin: 0 0 4px; font-size: 13.5px; font-weight: 600; color: var(--kg-muted) }
p { margin: 0 }
.muted { color: var(--kg-muted); font-size: 13.5px }
ul { margin: 0; padding-left: 18px }
li { margin: 2px 0; overflow-wrap: anywhere }
.warn { color: var(--kg-warn) }
.ok { color: var(--kg-ok) }
#diagram { width: 100%; overflow-x: auto }
svg { display: block; font-family: var(--kg-font) }
svg .box > rect { fill: var(--kg-card); stroke: var(--kg-line); stroke-width: 1.2 }
svg .box.finding > rect { stroke: var(--kg-warn); stroke-width: 2.2 }
svg .box .name { fill: var(--kg-ink); font-size: 13px; font-weight: 650 }
svg .box .col { fill: var(--kg-ink); font-size: 12px }
svg .box .more { fill: var(--kg-muted); font-size: 11.5px }
svg .box .tag { fill: var(--kg-accent); font-size: 10.5px; font-weight: 650 }
svg .box .tag.ref { fill: var(--kg-muted) }
svg .box .tag.nokey { fill: var(--kg-warn) }
svg .box line { stroke: var(--kg-line) }
svg .rel path { fill: none; stroke: var(--kg-edge); stroke-width: 1.5 }
svg .rel.finding path { stroke: var(--kg-warn); stroke-width: 2.4 }
svg .rel.rejected path { stroke-dasharray: 5 4; opacity: .7 }
svg .rel .head { fill: var(--kg-edge); stroke: none }
svg .rel.finding .head { fill: var(--kg-warn) }
svg .label rect { fill: var(--kg-bg); stroke: var(--kg-line); stroke-width: 1 }
svg .label.finding rect { fill: var(--kg-warn-bg); stroke: var(--kg-warn) }
svg .label text { fill: var(--kg-ink); font-size: 11px }
svg .label .rule { font-weight: 650 }
.items { display: grid; gap: 6px }
.item { border: 1px solid var(--kg-line); border-radius: 10px; padding: 6px 10px; display: grid; gap: 4px; min-width: 0 }
.item.finding { border-color: var(--kg-warn); border-width: 2px }
.item .what { font-weight: 600; overflow-wrap: anywhere }
.decide { display: flex; flex-wrap: wrap; gap: 6px; align-items: center }
select, input, button { font: inherit; font-size: 14px; color: var(--kg-ink); background: var(--kg-card);
  border: 1px solid var(--kg-line); border-radius: 8px; padding: 3px 8px; min-width: 0 }
input { flex: 1 1 140px }
button { font-weight: 650; border-radius: 999px; padding: 3px 14px; cursor: pointer }
button:disabled { cursor: default; opacity: .6 }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important } }
__MASCOT_CSS__
</style>
</head>
<body>
<main>
  <div class="kg-head"><h1>Plan review</h1>__MASCOT_TOGGLE__</div>
  <p id="verdict" class="muted" role="status">Waiting for review_plan's answer.</p>
  __MASCOTS__
  <section id="attention" hidden><h2>Needs attention</h2><ul id="attention-list"></ul></section>
  <section id="er" hidden><h2>Tables and relationships</h2><div id="diagram"></div>
    <p class="muted">Arrows point from the referencing table to the table it refers to; the label is the rule and, when checked, the counts.</p></section>
  <section id="list" hidden><h2>Keys and relationships</h2><div id="items" class="items"></div></section>
  <section id="next" hidden><h2>Next steps</h2><p id="note"></p></section>
  <p id="call" class="muted" role="status" hidden></p>
  <p class="muted">The same answer is in the text of the tool result. A button asks the host to call review_plan with that one decision; the host may ask you first. review_plan writes the review file in its answer and creates nothing in Fabric.</p>
</main>
<script>
(function () {
  "use strict";
  var ALLOWED = __ALLOWED__;            // the one tool a button can ask for -> the arguments carried over from this call
  var TOOL = "review_plan";
  var DECISIONS = __DECISIONS__, UNDECIDED = __UNDECIDED__;
  var NS = "__SVGNS__";
  var input = {}, answer = null;
  var nextId = 1, pending = {};
  function send(msg) { window.parent.postMessage(msg, "*"); }
  function request(method, params) {
    var id = nextId++;
    send({ jsonrpc: "2.0", id: id, method: method, params: params });
    return new Promise(function (resolve, reject) { pending[id] = { resolve: resolve, reject: reject }; });
  }
  function notify(method, params) { send({ jsonrpc: "2.0", method: method, params: params || {} }); }
__MASCOT_JS__
  function el(tag, text, cls) { var e = document.createElement(tag); if (text != null) e.textContent = String(text); if (cls) e.className = cls; return e; }
  function sv(tag, attrs, text) {
    var e = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text != null) e.textContent = String(text);
    return e;
  }
  function textOf(result) {
    var parts = (result && result.content) || [];
    for (var i = 0; i < parts.length; i++) if (parts[i] && parts[i].type === "text") return parts[i].text;
    return "";
  }
  function lower(s) { return String(s).toLowerCase(); }

  // ---------------------------------------------------------------- what is a finding
  function itemFinding(it) {
    var c = (it.check || {}).status;
    return c === "failed" || c === "stale" || it.review === "open";
  }
  function checkText(it) {
    var c = it.check || {}, r = c.result || {};
    if (c.status === "passed" || c.status === "failed" || c.status === "stale") {
      var counts = it.type === "key"
        ? r.rows + " rows, " + r.nulls + " nulls, " + r.distinct + " distinct"
        : r.rows_with_value + " rows with a value, " + r.orphans + " orphans";
      return (c.status === "stale" ? "stale (was " + c.was + "): " : c.status + ": ") + counts;
    }
    return "not checked";
  }
  function whatOf(it) {
    if (it.type === "key") return "key of " + it.table + ": " + ((it.columns || []).join(" + ") || "none") + " (" + it.rule + ")";
    return it.source + "." + it.columns.join("+") + " → " + it.target + "." + (it.target_columns || []).join("+") + " (" + it.rule + ")";
  }

  // ---------------------------------------------------------------- the diagram
  function layout(rv, width) {
    var snap = rv.snapshot, names = Object.keys(snap.tables), rels = snap.relationships || [];
    var byLower = {}; names.forEach(function (n) { byLower[lower(n)] = n; });
    var out = {}; names.forEach(function (n) { out[n] = []; });
    rels.forEach(function (r) { var s = byLower[lower(r.source)], t = byLower[lower(r.target)]; if (s && t && s !== t) out[s].push(t); });
    // level: 0 for a table that refers to nothing, else one more than the highest table it refers to (cycles stop)
    var level = {}; names.forEach(function (n) { level[n] = 0; });
    for (var pass = 0; pass < names.length; pass++) {
      var moved = false;
      names.forEach(function (n) { out[n].forEach(function (t) { if (level[n] < level[t] + 1 && level[t] + 1 < names.length) { level[n] = level[t] + 1; moved = true; } }); });
      if (!moved) break;
    }
    var gapX = 28, minW = 130, maxW = 200;
    var cols = Math.max(1, Math.floor((width + gapX) / (minW + gapX)));
    var narrow = cols === 1, lane = narrow ? 56 : 0;
    var boxW = narrow ? Math.max(120, width - lane) : Math.min(maxW, Math.floor((width - gapX * (cols - 1)) / cols));
    var rows = [], maxLevel = 0;
    names.forEach(function (n) { maxLevel = Math.max(maxLevel, level[n]); });
    for (var l = 0; l <= maxLevel; l++) {
      var these = names.filter(function (n) { return level[n] === l; });
      for (var i = 0; i < these.length; i += cols) rows.push(these.slice(i, i + cols));
    }
    var boxes = {}, y = 4, gapY = cols > 2 ? 92 : 132;    // fewer columns: more labels share a gap
    rows.forEach(function (row) {
      var rowH = 0;
      var used = row.length * boxW + (row.length - 1) * gapX;
      var x = narrow ? lane : Math.max(0, Math.floor((width - used) / 2));
      row.forEach(function (n) {
        var b = { name: n, x: x, y: y, w: boxW, lines: linesOf(rv, n, boxW) };
        b.h = 30 + b.lines.length * 18 + 6;
        boxes[n] = b; rowH = Math.max(rowH, b.h); x += boxW + gapX;
      });
      y += rowH + gapY;
    });
    return { boxes: boxes, height: y - gapY + 8, narrow: narrow, byLower: byLower };
  }

  function linesOf(rv, n, boxW) {
    var t = rv.snapshot.tables[n], cols = Object.keys(t.columns || {}), key = (t.key || []).map(lower);
    var refs = {};
    (rv.snapshot.relationships || []).forEach(function (r) { if (lower(r.source) === lower(n)) r.columns.forEach(function (c) { refs[lower(c)] = 1; }); });
    var marked = cols.filter(function (c) { return key.indexOf(lower(c)) >= 0 || refs[lower(c)]; });
    var other = cols.filter(function (c) { return marked.indexOf(c) < 0; });
    var shown = marked.concat(other.slice(0, Math.max(0, 6 - marked.length)));
    var chars = Math.max(8, Math.floor((boxW - 46) / 7));
    var lines = shown.map(function (c) {
      return { text: c.length > chars ? c.slice(0, chars - 1) + "…" : c,
               tag: key.indexOf(lower(c)) >= 0 ? "key" : (refs[lower(c)] ? "ref" : "") };
    });
    if (cols.length > shown.length) lines.push({ text: "+" + (cols.length - shown.length) + " more columns", more: true });
    return lines;
  }

  function drawDiagram(rv, findings) {
    var host = document.getElementById("diagram");
    var width = Math.max(200, Math.floor(host.clientWidth || 600));
    var L = layout(rv, width), boxes = L.boxes;
    var svg = sv("svg", { width: width, height: L.height, viewBox: "0 0 " + width + " " + L.height, role: "img",
                          "aria-label": "ER diagram: " + Object.keys(boxes).length + " tables, " + (rv.snapshot.relationships || []).length + " relationships" });
    var edges = sv("g", { "class": "edges" }), tables = sv("g", { "class": "tables" }), labels = sv("g", { "class": "labels" });
    svg.appendChild(edges); svg.appendChild(tables); svg.appendChild(labels);
    host.textContent = "";
    host.appendChild(svg);
    var items = {}; (rv.items || []).forEach(function (it) { items[it.id] = it; });

    // tables
    Object.keys(boxes).forEach(function (n) {
      var b = boxes[n], t = rv.snapshot.tables[n], keyless = !(t.key || []).length;
      var g = sv("g", { "class": "box table" + (findings.tables[lower(n)] || keyless ? " finding" : ""), "data-table": n,
                        transform: "translate(" + b.x + "," + b.y + ")" });
      g.appendChild(sv("rect", { width: b.w, height: b.h, rx: 8 }));
      g.appendChild(sv("text", { "class": "name", x: 10, y: 19 }, n.length > Math.floor((b.w - 60) / 7.5) + 3 ? n.slice(0, Math.floor((b.w - 60) / 7.5)) + "…" : n));
      if (keyless) g.appendChild(sv("text", { "class": "tag nokey", x: b.w - 8, y: 19, "text-anchor": "end" }, "no key"));
      g.appendChild(sv("line", { x1: 0, x2: b.w, y1: 27, y2: 27 }));
      b.lines.forEach(function (ln, i) {
        var yy = 27 + 16 + i * 18;
        g.appendChild(sv("text", { "class": ln.more ? "more" : "col", x: 10, y: yy }, ln.text));
        if (ln.tag) g.appendChild(sv("text", { "class": "tag " + ln.tag, x: b.w - 8, y: yy, "text-anchor": "end" }, ln.tag));
      });
      var title = sv("title", {}, n + (keyless ? ": no key" : ": key " + t.key.join(" + ") + " (" + t.key_rule + ")"));
      g.appendChild(title);
      tables.appendChild(g);
    });

    // relationships
    var placed = Object.keys(boxes).map(function (n) { var b = boxes[n]; return { x: b.x - 2, y: b.y - 2, w: b.w + 4, h: b.h + 4 }; });
    var sideCount = {};
    function slot(name, side) { var k = name + "|" + side; sideCount[k] = (sideCount[k] || 0) + 1; return sideCount[k] - 1; }
    (rv.snapshot.relationships || []).forEach(function (r, idx) {
      var s = boxes[L.byLower[lower(r.source)]], t = boxes[L.byLower[lower(r.target)]];
      if (!s || !t) return;
      var id = "rel:" + r.source + "." + r.columns.join("+") + ">" + r.target, it = items[id] || {};
      var cls = "rel" + (itemFinding(it) ? " finding" : "") + (it.review === "rejected" ? " rejected" : "");
      var g = sv("g", { "class": cls, "data-id": id, "data-rule": r.rule });
      var p0, p1, p2, p3;
      if (s === t) {                                    // a table that refers to itself: a loop on its right side
        var k = slot(s.name, "self");
        p0 = [s.x + s.w, s.y + 14 + k * 10]; p3 = [s.x + s.w, s.y + 34 + k * 10];
        p1 = [p0[0] + 46, p0[1] - 18]; p2 = [p3[0] + 46, p3[1] + 18];
      } else if (L.narrow || Math.abs(s.y - t.y) < 1) {  // one column, or the same row: round the left (or the gap) side
        if (Math.abs(s.y - t.y) < 1) {
          var left = s.x < t.x;
          p0 = [left ? s.x + s.w : s.x, s.y + 16]; p3 = [left ? t.x : t.x + t.w, t.y + 16];
          p1 = [p0[0], p0[1] - 30]; p2 = [p3[0], p3[1] - 30];
        } else {
          var ks = slot(s.name, "left"), kt = slot(t.name, "left");
          p0 = [s.x, s.y + 16 + (ks % 3) * 8]; p3 = [t.x, t.y + t.h - 10 - (kt % 3) * 8];
          var bulge = Math.max(10, s.x - 8 - (idx % 4) * 10);
          p1 = [p0[0] - bulge, p0[1]]; p2 = [p3[0] - bulge, p3[1]];
        }
      } else {
        var up = s.y > t.y;
        var ks2 = slot(s.name, up ? "top" : "bottom"), kt2 = slot(t.name, up ? "bottom" : "top");
        var off = function (k) { return [0, -22, 22, -44, 44][k % 5]; };
        p0 = [s.x + s.w / 2 + off(ks2), up ? s.y : s.y + s.h];
        p3 = [t.x + t.w / 2 + off(kt2), up ? t.y + t.h : t.y];
        var dy = (p3[1] - p0[1]) / 2;
        p1 = [p0[0], p0[1] + dy]; p2 = [p3[0], p3[1] - dy];
      }
      g.appendChild(sv("path", { d: "M" + p0 + " C" + p1 + " " + p2 + " " + p3 }));
      // the arrow head at the target end, along the curve's last tangent
      var ang = Math.atan2(p3[1] - p2[1], p3[0] - p2[0]);
      var a = function (d, w) { return [p3[0] - d * Math.cos(ang) + w * Math.sin(ang), p3[1] - d * Math.sin(ang) - w * Math.cos(ang)]; };
      g.appendChild(sv("path", { "class": "head", d: "M" + p3 + " L" + a(9, 4.5) + " L" + a(9, -4.5) + " Z" }));
      g.appendChild(sv("title", {}, whatOf(it.id ? it : { type: "relationship", source: r.source, columns: r.columns, target: r.target,
                                                       target_columns: r.target_columns, rule: r.rule }) + "; " + checkText(it)));
      edges.appendChild(g);

      // the label: the rule and, when checked, the counts; put where it covers no table and no other label
      var c = it.check || {}, res = c.result || {};
      var line2 = (c.status === "passed" || c.status === "failed" || c.status === "stale")
        ? res.rows_with_value + " rows, " + res.orphans + " orphans" + (c.status === "stale" ? " (stale)" : "") : "";
      var line1 = r.rule + (it.review && it.review !== "proposed" ? " · " + it.review : "");
      var lg = sv("g", { "class": "label" + (itemFinding(it) ? " finding" : "") });
      var tx1 = sv("text", { "class": "rule", "text-anchor": "middle" }, line1);
      lg.appendChild(sv("rect", { rx: 5 })); lg.appendChild(tx1);
      var tx2 = null;
      if (line2) { tx2 = sv("text", { "text-anchor": "middle" }, line2); lg.appendChild(tx2); }
      labels.appendChild(lg);                           // in the page first, so the text can be measured
      var lw = Math.ceil(Math.max(tx1.getComputedTextLength() || line1.length * 7,
                                  tx2 ? (tx2.getComputedTextLength() || line2.length * 7) : 0)) + 14, lh = line2 ? 30 : 17;
      var at = function (u) {
        var v = 1 - u;
        return [v * v * v * p0[0] + 3 * v * v * u * p1[0] + 3 * v * u * u * p2[0] + u * u * u * p3[0],
                v * v * v * p0[1] + 3 * v * v * u * p1[1] + 3 * v * u * u * p2[1] + u * u * u * p3[1]];
      };
      var spot = null;
      var tries = [];
      [0, 0.55, -0.55, 1.1, -1.1, 1.6, -1.6].forEach(function (dx) { [0, 0.6, -0.6, 1.2, -1.2].forEach(function (dy) {
        [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.1, 0.9, 0.05, 0.95].forEach(function (u) { tries.push([u, dx * lw, dy * lh]); }); }); });
      tries.some(function (tr) {
        var q = at(tr[0]), box = { x: q[0] + tr[1] - lw / 2, y: q[1] + tr[2] - lh / 2, w: lw, h: lh };
        if (box.x < 0) box.x = 0; if (box.x + lw > width) box.x = width - lw; if (box.y < 0) return false;
        var hit = placed.some(function (o) { return box.x < o.x + o.w + 3 && o.x < box.x + box.w + 3 && box.y < o.y + o.h + 3 && o.y < box.y + box.h + 3; });
        if (!hit) { spot = box; return true; }
        return false;
      });
      if (!spot) {                                      // no room on the curve: the nearest free place in a gap it crosses
        var lo = Math.min(p0[1], p3[1]), hi = Math.max(p0[1], p3[1]), mid = at(0.5);
        for (var gy = lo; gy <= hi - lh && !spot; gy += 6) {
          for (var step = 0; step <= width && !spot; step += 8) {
            [mid[0] - lw / 2 + step, mid[0] - lw / 2 - step].some(function (gx) {
              if (gx < 0 || gx + lw > width) return false;
              var box = { x: gx, y: gy, w: lw, h: lh };
              var hit = placed.some(function (o) { return box.x < o.x + o.w + 3 && o.x < box.x + box.w + 3 && box.y < o.y + o.h + 3 && o.y < box.y + box.h + 3; });
              if (!hit) spot = box;
              return !hit;
            });
          }
        }
      }
      if (!spot) { var q = at(0.5); spot = { x: Math.min(Math.max(0, q[0] - lw / 2), width - lw), y: q[1] - lh / 2, w: lw, h: lh }; }
      placed.push(spot);
      lg.firstChild.setAttribute("x", spot.x); lg.firstChild.setAttribute("y", spot.y);
      lg.firstChild.setAttribute("width", spot.w); lg.firstChild.setAttribute("height", spot.h);
      tx1.setAttribute("x", spot.x + spot.w / 2); tx1.setAttribute("y", spot.y + 12.5);
      if (tx2) { tx2.setAttribute("x", spot.x + spot.w / 2); tx2.setAttribute("y", spot.y + 25.5); }
      lg.setAttribute("data-for", id);
    });
  }

  // ---------------------------------------------------------------- the rest of the card
  function findingsOf(rv) {
    var f = { tables: {} };
    (rv.items || []).forEach(function (it) {
      if (it.type === "key" && itemFinding(it)) f.tables[lower(it.table)] = 1;
    });
    (rv.open_questions || []).forEach(function (q) {
      var m = /^key:(.+)$/.exec(q.about || "") || /^([^.]+)\./.exec(q.about || "");
      if (m) f.tables[lower(m[1])] = 1;
    });
    return f;
  }

  function render(data) {
    var verdict = document.getElementById("verdict");
    mascotsQuiet();
    if (!data || typeof data !== "object") { verdict.textContent = "The answer is not a review_plan answer; it is in the text of the tool result."; return; }
    if (data.error) { verdict.textContent = data.error + (data.hint ? " " + data.hint : ""); return; }
    var rv = data.review;
    if (!rv || !rv.snapshot || !rv.snapshot.tables) { verdict.textContent = "The answer holds no review file; it is in the text of the tool result."; return; }
    answer = data;
    verdict.textContent = data.summary || "";

    var list = document.getElementById("attention-list"); list.textContent = "";
    (data.attention || []).forEach(function (a) { list.appendChild(el("li", a)); });
    document.getElementById("attention").hidden = !list.children.length;

    document.getElementById("er").hidden = false;
    drawDiagram(rv, findingsOf(rv));

    var box = document.getElementById("items"); box.textContent = "";
    (rv.items || []).forEach(function (it) {
      var row = el("div", null, "item" + (itemFinding(it) ? " finding" : ""));
      row.setAttribute("data-item", it.id);
      row.appendChild(el("p", whatOf(it), "what"));
      var c = it.check || {};
      row.appendChild(el("p", "review: " + it.review + (it.reason ? " (" + it.reason + ")" : "") + "; check: " +
                              (c.verdict ? c.status + ", " + c.verdict : checkText(it)),
                         (c.status === "failed" || c.status === "stale") ? "muted warn" : "muted"));
      if (UNDECIDED.indexOf(it.review) >= 0) row.appendChild(decideRow(it));
      box.appendChild(row);
    });
    document.getElementById("list").hidden = !box.children.length;

    var note = typeof data.note === "string" ? data.note : "";
    document.getElementById("note").textContent = note;
    document.getElementById("next").hidden = !note;

    // n136: Onto says the counts, the Thinker the first line that needs attention, the Builder what to do next; every
    // sentence is a string of the answer and is on the card. Glad only when every item was checked and passed and
    // nothing needs attention.
    var all = rv.items || [];
    var passed = all.length > 0 && !(data.attention || []).length &&
                 all.every(function (it) { return (it.check || {}).status === "passed"; });
    mascots({ onto: [data.summary || "", passed ? "celebrate" : "point"],
              thinker: [(data.attention || [])[0] || "", "think"],
              builder: [note, passed ? "heart" : "explain"] }, passed);
  }

  function decideRow(it) {
    var wrap = el("div", null, "decide");
    var pick = el("select"); pick.setAttribute("aria-label", "Decision for " + it.id);
    DECISIONS.forEach(function (d) { if (d !== it.review) { var o = el("option", d); o.value = d; pick.appendChild(o); } });
    var why = el("input"); why.type = "text"; why.placeholder = "reason (optional)"; why.setAttribute("aria-label", "Reason for " + it.id);
    var b = el("button", "Record decision"); b.type = "button"; b.setAttribute("data-item", it.id);
    b.addEventListener("click", function () { decide(it.id, pick.value, why.value, b); });
    wrap.appendChild(pick); wrap.appendChild(why); wrap.appendChild(b);
    return wrap;
  }

  function decide(item, review, reason, button) {
    if (DECISIONS.indexOf(review) < 0 || !answer) return;
    var args = {};
    (ALLOWED[TOOL] || []).forEach(function (k) { if (input[k] != null) args[k] = input[k]; });
    args.previous = answer.review;
    var d = { item: item, review: review }; if (reason) d.reason = String(reason).slice(0, 500);
    args.decisions = [d];
    var note = document.getElementById("call"); note.hidden = false;
    note.textContent = "Asked the host to call review_plan: " + item + " " + review + ".";
    button.disabled = true;
    request("tools/call", { name: TOOL, arguments: args }).then(function (r) {
      var parsed = null; try { parsed = JSON.parse(textOf(r)); } catch (e) { parsed = null; }
      if (parsed && parsed.review) {
        render(parsed);
        note.textContent = "review_plan answered: " + item + " " + review + ". " + (parsed.note || "");
      } else {
        note.textContent = "review_plan answered; the answer is in the text of the tool result.";
        button.disabled = false;
      }
    }, function (e) {
      note.textContent = "The host did not call review_plan: " + (e && e.message ? e.message : "no reason given") + ".";
      button.disabled = false;
    });
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var m = event.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id != null && !m.method && pending[m.id]) {
      var p = pending[m.id]; delete pending[m.id];
      if (m.error) p.reject(new Error(m.error.message || "error")); else p.resolve(m.result);
      return;
    }
    if (m.method === "ui/notifications/tool-input") input = (m.params && m.params.arguments) || {};
    else if (m.method === "ui/notifications/tool-result") {
      var data; try { data = JSON.parse(textOf(m.params)); } catch (e) { data = null; }
      render(data);
    }
    else if (m.method === "ui/notifications/tool-cancelled") { document.getElementById("verdict").textContent = "The review was cancelled."; mascotsQuiet(); }
    else if (m.method === "ui/resource-teardown" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
    else if (m.method === "ping" && m.id != null) send({ jsonrpc: "2.0", id: m.id, result: {} });
  });

  var last = 0, lastWidth = 0;
  function reportSize() {
    var h = Math.ceil(document.documentElement.scrollHeight), w = Math.ceil(document.documentElement.scrollWidth);
    if (h !== last) { last = h; notify("ui/notifications/size-changed", { width: w, height: h }); }
  }
  function onResize() {
    var w = document.getElementById("diagram").clientWidth;
    if (answer && Math.abs(w - lastWidth) > 4) { lastWidth = w; drawDiagram(answer.review, findingsOf(answer.review)); }
    reportSize();
  }
  request("ui/initialize", {
    appInfo: { name: "Krusgraph plan review", version: "1" },
    appCapabilities: { availableDisplayModes: ["inline"] },
    protocolVersion: "__PROTOCOL__"
  }).then(function () {
    notify("ui/notifications/initialized");
    reportSize();
    if (window.ResizeObserver) new ResizeObserver(onResize).observe(document.body);
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
