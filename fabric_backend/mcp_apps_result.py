"""MCP Apps, round n227: what a card shows of an answer, while it waits and when it is done.

The founder tried the cards in claude.ai on 12 November 2026 (deploy src-37ff21adce4ff691). The tool results already
carried plain words in `kg_card` (mcp_apps_words.py), but a button's answer was drawn from the raw `summary` string, an
answer without one said "no summary in it; the whole answer is under Show details", and nothing showed that a tool was
running. This module is the shared script for that, used by every card (mcp_apps.RESULT_JS and RESULT_CSS include it):

- cardWords(d) / wordsView(w): `kg_card` first, everywhere: `result` (one line), `lines` (at most five), `notes`
  (one line each, the list behind Show). summaryOf (mcp_apps.RESULT_JS) is the fallback for an answer without kg_card
  (an older server), and it never says "no summary": oneLine(d) always finds a sentence in the answer itself.
- detailsView(tool, d, text): "Show details" holds readable lines first (label: value, counts for lists), and the raw
  JSON last, behind a second toggle ("Show the raw answer (JSON)").
- waitView(act): the progress state while a tool runs: who is working ("Builder"), what on ("Creating shop_api_3 in
  Fabric…"), an indicator and the elapsed seconds. The cards have no CSS animation (n136): the indicator is three dots
  of which one is lit, stepped by the same one-second timer that counts; with prefers-reduced-motion it stands still
  (all three lit) and only the seconds change. The seconds are how long this card has waited, not a promise.
- ontoSvg(o): an ontology as a static SVG that is readable at 375 px: one entity type per row with its key marked
  (key, no key, key of several columns), and each relationship type as a numbered arrow on the right with its name
  in the legend under the picture (names on the arrows ran over each other at a phone's width). Drawn from the
  answer's `ontology` (mcp_apps_pictures.ontology_from); no layout engine, no script in the SVG.
- sapNote(box, text): "SAP pack: Krusgraph's list of known SAP keys", once per card, the first time the words appear.

Nothing here names a tool to the user: a button's label and `ask` are plain words (mcp_apps_next._step,
mcp_apps_build.action), and the status lines say what is being done, not which tool does it.
"""
from __future__ import annotations

from .mcp_apps_words import SAP_PACK

LINES_MAX = 5

CSS = """
.res-words { display: grid; gap: 4px; min-width: 0 }
.res-line { font-weight: 650; overflow-wrap: anywhere }
.res-line.res-done::before { content: "\\2713\\00a0"; color: var(--kg-ok) }
.res-note summary, .res-details > summary, .res-raw > summary { cursor: pointer; font-size: 13.5px }
.res-note summary { color: var(--kg-ink); font-weight: 500 }
.res-show { color: var(--kg-muted); font-weight: 600; white-space: nowrap }
.res-note[open] .res-show { display: none }
.res-note ul { margin: 2px 0 4px; padding-left: 18px; max-height: 220px; overflow: auto }
.res-note li, .res-words li { overflow-wrap: anywhere }
.res-raw { margin-top: 6px }
.wait { display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; font-size: 14px }
.wait-dots { flex: none; display: inline-flex; gap: 3px }
.wait-dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--kg-line) }
.wait-dots[data-on="0"] i:nth-child(1), .wait-dots[data-on="1"] i:nth-child(2), .wait-dots[data-on="2"] i:nth-child(3),
.wait-dots[data-on="all"] i { background: var(--kg-ink) }
.wait-s { color: var(--kg-muted); font-variant-numeric: tabular-nums }
.wait-more { flex-basis: 100% }
.wait-more:empty { display: none }
.onto-fig { margin: 0; display: grid; gap: 4px; min-width: 0 }
.onto-fig svg { display: block; width: 100%; height: auto; max-width: 420px }
.onto-fig figcaption { color: var(--kg-muted); font-size: 13px }
.onto-box { fill: var(--kg-card); stroke: var(--kg-line) }
.onto-box.onto-nokey, .onto-box.onto-multi { stroke-dasharray: 4 3 }
.onto-name { fill: var(--kg-ink); font: 650 13px var(--kg-font) }
.onto-key { fill: var(--kg-muted); font: 12px var(--kg-font) }
.onto-arc { fill: none; stroke: var(--kg-muted); stroke-width: 1.4 }
.onto-arc.onto-off { stroke-dasharray: 3 3 }
.onto-tip { fill: var(--kg-muted) }
.onto-num { fill: var(--kg-bg); stroke: var(--kg-muted) }
.onto-lab { fill: var(--kg-ink); font: 650 10px var(--kg-font) }
.onto-legend { margin: 0; padding-left: 26px; font-size: 13px; max-height: 200px; overflow: auto }
.onto-legend li { overflow-wrap: anywhere }
.sap-note { color: var(--kg-muted); font-size: 13px }
"""

JS = r"""
  // ---- n227: kg_card first; readable details; the progress state; the ontology as a static SVG -------------------
  var CARD_LINES = __LINES_MAX__, SAP_SAID = __SAP_PACK__;
  function cardWords(d) {
    var w = isObj(d) && isObj(d.kg_card) ? d.kg_card : null;
    if (!w) return null;
    var lines = arr(w.lines).filter(readable).slice(0, CARD_LINES);
    var notes = arr(w.notes).filter(function (n) { return isObj(n) && readable(n.line); });
    if (!readable(w.result) && !lines.length) return null;
    return { result: readable(w.result), lines: lines, notes: notes };
  }
  function noteView(n) {
    var items = arr(n.items).filter(readable);
    if (!items.length) return el("p", n.line, "res-note");
    var det = el("details", null, "res-note"), sm = el("summary");
    sm.appendChild(el("span", n.line + " ")); sm.appendChild(el("span", "Show", "res-show"));
    det.appendChild(sm);
    var ul = el("ul");
    items.forEach(function (x) { ul.appendChild(el("li", x)); });
    if (Number(n.more) > 0) ul.appendChild(el("li", "and " + n.more + " more, in the raw answer"));
    det.appendChild(ul);
    return det;
  }
  function wordsView(w, skipResult, done) {
    var box = el("div", null, "res-words");
    if (w.result && !skipResult) box.appendChild(el("p", w.result, "res-line" + (done ? " res-done" : "")));
    if (w.lines.length) { var ul = el("ul", null, "res"); w.lines.forEach(function (t) { ul.appendChild(el("li", t)); }); box.appendChild(ul); }
    w.notes.forEach(function (n) { box.appendChild(noteView(n)); });
    return box;
  }
  // A sentence from the answer itself, for an answer without kg_card: an answer always has something to say.
  function oneLine(d) {
    if (readable(d.summary)) return String(d.summary).split("\n")[0];
    if (readable(d.verdict)) return d.verdict;
    var s = isObj(d.summary) ? d.summary : null;
    if (s && "relationships_active" in s) {
      var rels = (Number(s.relationships_active) || 0) + (Number(s.relationships_inactive) || 0);
      return "A semantic model: " + plural(Number(s.tables) || 0, "table", "tables") + ", " + plural(rels, "relationship", "relationships") + "." + (d.dry_run === true ? " A dry run: nothing was created." : "");
    }
    if (s && "entity_types" in s) return "An ontology: " + plural(Number(s.entity_types) || 0, "entity type", "entity types") + ", " + (Number(s.with_key) || 0) + " with a key." + (d.dry_run === true ? " A dry run: nothing was created." : "");
    var parts = [];
    Object.keys(d).forEach(function (k) {
      if (parts.length >= 3 || k === "kg_card") return;
      var v = d[k], word = k.replace(/_/g, " ");
      if (Array.isArray(v)) parts.push(v.length + " " + (v.length === 1 && /s$/.test(word) ? word.slice(0, -1) : word));
      else if (typeof v === "number") parts.push(word + ": " + v);
    });
    if (parts.length) return parts.join(", ") + ".";
    var ks = Object.keys(d).filter(function (k) { return k !== "kg_card"; });
    return ks.length ? "The answer has " + plural(ks.length, "part", "parts") + ": " + some(ks, function (k) { return k.replace(/_/g, " "); }) + "." : "The answer is empty.";
  }
  // Readable lines of any answer: a short text as it is, a list as its count, an object as its number of entries.
  function plainLines(d) {
    var out = [];
    Object.keys(d).forEach(function (k) {
      if (k === "kg_card" || k === "actions" || k === "next" || out.length >= 24) return;
      var v = d[k], label = k.replace(/_/g, " ");
      label = label.charAt(0).toUpperCase() + label.slice(1);
      if (typeof v === "string") { if (readable(v) && v.length <= 240) out.push([label, v]); }
      else if (typeof v === "number" || typeof v === "boolean") out.push([label, v === true ? "yes" : v === false ? "no" : String(v)]);
      else if (Array.isArray(v)) out.push([label, String(v.length)]);
      else if (isObj(v)) out.push([label, plural(Object.keys(v).length, "entry", "entries")]);
    });
    return out;
  }
  function detailsView(tool, d, text) {
    var det = el("details", null, "res-details");
    det.appendChild(el("summary", "Show details"));
    if (d) {
      var sm = summaryOf(tool, d), lines = sm.lines.length ? sm.lines : plainLines(d), ul = el("ul", null, "res");
      lines.forEach(function (ln) { var li = el("li"); li.appendChild(el("span", ln[0] + ": ", "res-k")); li.appendChild(document.createTextNode(ln[1])); ul.appendChild(li); });
      if (lines.length) det.appendChild(ul);
    }
    var full = d ? JSON.stringify(d, null, 2) : text;
    if (full) {
      var raw = el("details", null, "res-raw");
      raw.appendChild(el("summary", "Show the raw answer (JSON)"));
      raw.appendChild(el("pre", full.length > 60000 ? full.slice(0, 60000) + "\n… (the rest is in the tool's own answer)" : full));
      det.appendChild(raw);
    }
    return det;
  }
  // Repeated notes become one line each: "24 × Not expressible", the list behind Show (an answer without kg_card).
  function groupedNotes(lines) {
    var groups = {}, order = [];
    lines.forEach(function (ln) {
      if (ln[0] !== "Note") return;
      var k = (/^([A-Z][A-Za-z ]{2,30}):/.exec(ln[1]) || [])[1] || "Note";
      if (!groups[k]) { groups[k] = []; order.push(k); }
      groups[k].push(ln[1]);
    });
    return order.map(function (k) { return { line: plural(groups[k].length, "note", "notes") + ": " + k, items: groups[k] }; });
  }
  function whoRuns(a) {
    if (isObj(a) && (a.kind === "create" || a.kind === "dry_run" || a.kind === "status")) return "Builder";
    if (isObj(a) && /check|review|count|decision|doubled/i.test(String(a.label || ""))) return "Thinker";
    return "Onto";
  }
  function doingOf(a) {
    if (!isObj(a)) return "Working on it…";
    if (readable(a.doing)) return a.doing;
    if (a.kind === "create") return "Creating " + (a.name || "it") + " in Fabric…";
    if (a.kind === "status") return "Checking " + (a.name || "it") + " in Fabric…";
    if (a.kind === "dry_run") return "Preparing the dry run" + (a.name ? " of " + a.name : "") + "…";
    return String(a.label || "Working on it").replace(/[.…\s]+$/, "") + "…";
  }
  function waitView(a) {
    var box = el("div", null, "wait"); box.setAttribute("role", "status");
    var dots = el("span", null, "wait-dots"); dots.setAttribute("aria-hidden", "true");
    for (var i = 0; i < 3; i++) dots.appendChild(el("i"));
    var still = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    dots.setAttribute("data-on", still ? "all" : "0"); box.setAttribute("data-motion", still ? "still" : "steps");
    var t0 = Date.now(), secs = el("span", "0 s", "wait-s"), more = el("span", "", "wait-more muted");
    secs.setAttribute("aria-hidden", "true");                      // the seconds change every second: not read out
    box.appendChild(dots); box.appendChild(el("span", whoRuns(a) + ": " + doingOf(a), "wait-t")); box.appendChild(secs); box.appendChild(more);
    var timer = setInterval(function () {
      var n = Math.round((Date.now() - t0) / 1000);
      secs.textContent = n + " s";
      if (!still) dots.setAttribute("data-on", String(n % 3));
    }, 1000);
    return { el: box, stop: function () { clearInterval(timer); }, note: function (t) { more.textContent = t; } };
  }
  function sapNote(box, text) {                                     // said once per card, the first time the words appear
    if (!/\bSAP pack\b/.test(String(text || "")) || document.querySelector(".sap-note")) return;
    box.appendChild(el("p", SAP_SAID + ".", "sap-note"));
  }
  // The ontology, static: a row per entity type (name, key marked), relationship types as labelled arcs on the right.
  function ontoSvg(o) {
    if (!isObj(o) || !Array.isArray(o.entities) || !o.entities.length) return null;
    // the SVG namespace is read from the card's own inline figures: the card's code names no address
    var inline = document.querySelector("svg"), NS = inline ? inline.namespaceURI : "";
    if (!NS) return null;
    var ents = o.entities.filter(isObj), links = arr(o.links).filter(isObj);
    var W = 343, BOXW = 178, ROW = 46, BOXH = 36, X0 = 1, TOP = 4, LANE = 16;
    function s(tag, attrs, text) {
      var e = document.createElementNS(NS, tag);
      Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
      if (text != null) e.textContent = text;
      return e;
    }
    function cut(t, n) { t = String(t || ""); return t.length > n ? t.slice(0, n - 1) + "…" : t; }
    var at = {};
    ents.forEach(function (x, i) { at[x.name] = i; });
    var drawn = links.filter(function (l) { return l.source_entity in at && l.target_entity in at; });
    // lanes: an arc takes the first lane no drawn arc overlaps in its span of rows
    var lanes = [];
    drawn.forEach(function (l) {
      var a = Math.min(at[l.source_entity], at[l.target_entity]), b = Math.max(at[l.source_entity], at[l.target_entity]), k = 0;
      while (lanes[k] && lanes[k].some(function (r) { return !(b < r[0] || a > r[1]); })) k++;
      (lanes[k] = lanes[k] || []).push([a, b]); l._lane = k;
    });
    var nLanes = Math.max(1, Math.min(lanes.length, 8)), H = TOP * 2 + ents.length * ROW;
    var svg = s("svg", { viewBox: "0 0 " + W + " " + H, role: "img", "class": "onto-svg" });
    var withKey = ents.filter(function (x) { return !!x.key; }).length;
    var desc = plural(ents.length, "entity type", "entity types") + ", " + withKey + " with a key; " + plural(drawn.filter(function (l) { return l.in_ontology !== false; }).length, "relationship type", "relationship types") + ".";
    svg.setAttribute("aria-label", "The ontology: " + desc);
    svg.appendChild(s("title", {}, "The ontology: " + desc));
    ents.forEach(function (x, i) {
      var y = TOP + i * ROW, multi = !x.key && arr(x.key_columns).length > 1;
      var keyText = x.key ? "key: " + x.key : multi ? "key of several columns: " + x.key_columns.join(" + ") : "no key";
      var g = s("g", { "data-entity": x.name, "data-key": x.key ? "key" : multi ? "composite" : "none" });
      g.appendChild(s("rect", { x: X0, y: y, width: BOXW, height: BOXH, rx: 8, "class": "onto-box" + (x.key ? "" : multi ? " onto-multi" : " onto-nokey") }));
      g.appendChild(s("text", { x: X0 + 8, y: y + 15, "class": "onto-name" }, cut(x.name, 24)));
      g.appendChild(s("text", { x: X0 + 8, y: y + 29, "class": "onto-key" }, cut(keyText, 30)));
      g.appendChild(s("title", {}, x.name + " (" + keyText + ")"));
      svg.appendChild(g);
    });
    var nums = [];
    drawn.forEach(function (l, n) {
      var i = at[l.source_entity], j = at[l.target_entity], lane = Math.min(l._lane, nLanes - 1);
      var x1 = X0 + BOXW, xl = x1 + 14 + lane * LANE;
      var y1 = TOP + i * ROW + BOXH / 2 + (i === j ? -8 : (j > i ? 6 : -6)), y2 = TOP + j * ROW + BOXH / 2 + (i === j ? 8 : (j > i ? -6 : 6));
      var g = s("g", { "data-link": l.source_entity + ">" + (l.name || "") + ">" + l.target_entity });
      g.appendChild(s("path", { d: "M" + x1 + " " + y1 + " H" + xl + " V" + y2 + " H" + (x1 + 5), "class": "onto-arc" + (l.in_ontology === false ? " onto-off" : "") }));
      g.appendChild(s("path", { d: "M" + x1 + " " + y2 + " l6 -3.5 v7 z", "class": "onto-tip" }));
      // the label is the relationship's number, on its own lane; the names are in the legend under the picture, so
      // no label runs over another or off the picture at a phone's width
      var ly = (y1 + y2) / 2;
      nums.push(s("circle", { cx: xl, cy: ly, r: 7.5, "class": "onto-num" }));          // drawn last, over every line
      nums.push(s("text", { x: xl, y: ly + 3.5, "text-anchor": "middle", "class": "onto-lab" }, String(n + 1)));
      g.appendChild(s("title", {}, l.source_entity + " " + (l.name || "→") + " " + l.target_entity + (l.in_ontology === false ? " (over several columns: not a relationship type)" : "")));
      svg.appendChild(g);
    });
    nums.forEach(function (e) { svg.appendChild(e); });
    var fig = el("figure", null, "onto-fig");
    fig.appendChild(svg);
    fig.appendChild(el("figcaption", "Solid box: has a key. Dashed box: no key, or a key of several columns. An arrow points at the entity type a relationship leads to."));
    if (drawn.length) {
      var legend = el("ol", null, "onto-legend"); legend.setAttribute("aria-label", "The relationships, by number");
      drawn.forEach(function (l) { legend.appendChild(el("li", l.source_entity + " → " + l.target_entity + (l.name ? ": " + l.name : "") + (l.in_ontology === false ? " (over several columns: not a relationship type)" : ""))); });
      fig.appendChild(legend);
    }
    var list = el("details", null, "res-note"), sm = el("summary");
    sm.appendChild(el("span", "The ontology as a list ")); sm.appendChild(el("span", "Show", "res-show")); list.appendChild(sm);
    var ul = el("ul");
    ents.forEach(function (x) {
      var multi = !x.key && arr(x.key_columns).length > 1;
      ul.appendChild(el("li", x.name + ": " + (x.key ? "key " + x.key : multi ? "key of several columns (" + x.key_columns.join(" + ") + ")" : "no key")));
    });
    links.forEach(function (l) { ul.appendChild(el("li", l.source_entity + " " + (l.name || "→") + " " + l.target_entity + (l.in_ontology === false ? " (over several columns: not a relationship type)" : ""))); });
    list.appendChild(ul); fig.appendChild(list);
    return fig;
  }
"""


def js() -> str:
    import json
    return JS.replace("__LINES_MAX__", str(LINES_MAX)).replace("__SAP_PACK__", json.dumps(SAP_PACK))
