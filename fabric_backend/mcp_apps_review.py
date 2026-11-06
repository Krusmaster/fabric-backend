"""MCP Apps, second card (round n124): review_plan's answer as an ER diagram with the decisions still to make.

Behind the same flag as the n119 card (KRUSGRAPH_MCP_APPS, off unless "1"); with the flag off nothing here reaches the
server. It follows `mcp_apps.py` and the specification read there (modelcontextprotocol/ext-apps,
specification/2026-01-26/apps.mdx, Status: Stable): a `ui://` resource served as `text/html;profile=mcp-app` through the
SDK's `Apps` extension, the tool pointing at it with `_meta.ui.resourceUri` and the deprecated flat
`_meta["ui/resourceUri"]`, no `_meta.ui.csp` (the host's restrictive default applies), and the view talking to the host
with JSON-RPC 2.0 over postMessage (`ui/initialize`, `ui/notifications/initialized`, `ui/notifications/tool-input`,
`ui/notifications/tool-result`, `ui/notifications/size-changed`, `tools/call`). No code from that repository is copied.

What the card shows, all of it read from review_plan's answer (since n137 in every form a host may deliver it, see
mcp_apps.READ_JS: structuredContent, the text content as JSON, or either wrapped as {"result": "<JSON text>"}):

- the summary and the answer's `attention` lines;
- an ER diagram drawn as inline SVG from `review.snapshot`: one box per table with its key columns marked "key" and its
  referencing columns marked "ref", one arrow per relationship labelled with its rule and, when the item was checked,
  its counts (rows with a value, orphans); items with a failed or stale check, items left open, keyless tables and
  tables an open question is about are highlighted, rejected relationships are dashed. Since n138 (LAYOUT_JS) the
  tables a table refers to stand above it, and the edges run at right angles through the gaps between tables, so no
  edge crosses a table; each label sits on its own edge, on a track of its own, so no label covers another or a table;
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
            .replace("__MASCOTS__", mascots.section()).replace("__MASCOT_JS__", mascots.JS)
            .replace("__READ_JS__", mcp_apps.READ_JS + mcp_apps.CALL_JS).replace("__LAYOUT_JS__", LAYOUT_JS))


# n138: the ER diagram's layout as a pure function (erLayout), placed into the card. tests/test_n138_card_polish.py
# checks its geometry in a browser for the shop and a 15-table fixture.
LAYOUT_JS = r"""
  // n138: the diagram's layout, pure (no DOM), so that it can be checked on its own. A layered grid: a table that
  // refers to nothing is on the top row, every other one row below the lowest table it refers to, so arrows point up.
  // Tables sit in fixed columns; between two columns, and left and right of them, is a corridor, and above and below
  // every row a channel. An edge leaves its table straight into the next channel, runs along a track of that channel
  // to a corridor, along a track of the corridor past the rows in between, and along a track of the target's channel
  // to the target: every part is in a channel or a corridor, where no table is, so no edge crosses a table. The label
  // sits on the edge's part in the target's channel, on a track of its own height; two labels on one track get
  // intervals that do not meet, so no label covers another or a table.
  // spec: { width, boxes: [{ h }], edges: [{ s, t, lw, lh }] } (s, t: indexes into boxes; lw 0: no label).
  // Gives { width, height, cols, boxW, boxes: [{ x, y, w, h, row, col }], edges: [{ points, label }] }.
  function erLayout(spec) {
    var W = spec.width, N = spec.boxes.length, E = spec.edges;
    var MIN_W = 112, MAX_W = 210, TRACK = 8, CPAD = 7, MIN_GAP = 22, MIN_EDGE = 10, CHPAD = 6, EMPTY_CH = 22;
    var i, j;
    var refs = [], nb = [];
    for (i = 0; i < N; i++) { refs.push([]); nb.push([]); }
    E.forEach(function (e) { if (e.s !== e.t) { refs[e.s].push(e.t); nb[e.s].push(e.t); nb[e.t].push(e.s); } });
    var level = []; for (i = 0; i < N; i++) level.push(0);
    for (var pass = 0; pass < N; pass++) {                 // the longest path upwards; a cycle stops at N - 1
      var moved = false;
      for (i = 0; i < N; i++) refs[i].forEach(function (t) {
        if (level[i] < level[t] + 1 && level[t] + 1 < N) { level[i] = level[t] + 1; moved = true; }
      });
      if (!moved) break;
    }
    var maxLevel = 0, perLevel = {};
    for (i = 0; i < N; i++) { maxLevel = Math.max(maxLevel, level[i]); perLevel[level[i]] = (perLevel[level[i]] || 0) + 1; }
    var widest = 1; Object.keys(perLevel).forEach(function (l) { widest = Math.max(widest, perLevel[l]); });

    function place(cols) {
      var rows = [];
      for (var l = 0; l <= maxLevel; l++) {
        var these = []; for (var b = 0; b < N; b++) if (level[b] === l) these.push(b);
        // a table with many references near the middle of its level; a level wider than the grid wraps
        these.sort(function (a, c) { return nb[c].length - nb[a].length || a - c; });
        for (var k = 0; k < these.length; k += cols) rows.push(these.slice(k, k + cols));
      }
      var row = [], col = [];
      rows.forEach(function (r, ri) {
        var off = Math.floor((cols - r.length) / 2);
        r.forEach(function (b, k) { row[b] = ri; col[b] = off + k; });
      });
      function sweep(order) {                              // each row towards the mean column of its neighbours
        order.forEach(function (ri) {
          var r = rows[ri], want = {};
          r.forEach(function (b) {
            var others = nb[b].filter(function (o) { return row[o] !== ri; });
            want[b] = others.length ? others.reduce(function (s, o) { return s + col[o]; }, 0) / others.length : col[b];
          });
          var sorted = r.slice().sort(function (a, c) { return want[a] - want[c] || col[a] - col[c] || a - c; });
          var prev = -1;
          sorted.forEach(function (b, k) {
            var slot = Math.max(prev + 1, Math.min(Math.round(want[b]), cols - (sorted.length - k)));
            col[b] = slot; prev = slot;
          });
        });
      }
      var down = rows.map(function (r, ri) { return ri; }), up = down.slice().reverse();
      for (var s = 0; s < 3; s++) { sweep(down); sweep(up); }
      return { rows: rows, row: row, col: col };
    }

    function route(g, cols) {
      var load = []; for (var k = 0; k <= cols; k++) load.push(0);
      return E.map(function (e) {
        var sr = g.row[e.s], tr = g.row[e.t], sc = g.col[e.s], tc = g.col[e.t];
        var r = { e: e };
        if (sr > tr) { r.A = sr; r.B = tr + 1; r.sSide = "top"; r.tSide = "bottom"; }
        else if (sr < tr) { r.A = sr + 1; r.B = tr; r.sSide = "bottom"; r.tSide = "top"; }
        else { r.A = r.B = sr; r.sSide = r.tSide = "top"; }
        if (r.A !== r.B) {
          var cand = [];
          if (sc === tc) cand = [sc, sc + 1];
          else for (var c = Math.min(sc, tc) + 1; c <= Math.max(sc, tc); c++) cand.push(c);
          var mid = (sc + tc + 1) / 2;
          cand.sort(function (a, b) { return load[a] - load[b] || Math.abs(a - mid) - Math.abs(b - mid) || a - b; });
          r.corr = cand[0]; load[r.corr]++;
        }
        return r;
      });
    }

    function intervalTracks(items, lo, hi) {               // first fit by start: items on one track never meet
      var tracks = [];
      items.slice().sort(function (a, b) { return lo(a) - lo(b); }).forEach(function (it) {
        for (var k = 0; k < tracks.length; k++) {
          if (tracks[k].every(function (o) { return hi(o) < lo(it) || hi(it) < lo(o); })) { tracks[k].push(it); it.track = k; return; }
        }
        tracks.push([it]); it.track = tracks.length - 1;
      });
      return tracks;
    }

    // the tracks of one channel, top to bottom. A part whose end leaves the channel downwards under another part's room
    // goes below that part, one that leaves upwards above it, so its line does not cross the other's label (first for
    // the parts with a label, then for the rest where that makes no cycle); parts whose rooms meet get tracks of
    // their own.
    function channelTracks(list) {
      var n = list.length, after = [], k, m;
      for (k = 0; k < n; k++) after.push([]);
      function reaches(from, to) {
        var seen = {}, stack = [from];
        while (stack.length) { var x = stack.pop(); if (x === to) return true; if (seen[x]) continue; seen[x] = 1; after[x].forEach(function (y) { stack.push(y); }); }
        return false;
      }
      [true, false].forEach(function (labelled) {
        for (k = 0; k < n; k++) {
          if (!!list[k].label !== labelled) continue;
          for (m = 0; m < n; m++) {
            if (m === k) continue;
            list[m].ends.forEach(function (end) {
              if (end[0] < list[k].lo || end[0] > list[k].hi) return;
              var hi = end[1] === "down" ? k : m, lo = end[1] === "down" ? m : k;   // hi above lo
              if (after[hi].indexOf(lo) < 0 && !reaches(lo, hi)) after[hi].push(lo);
            });
          }
        }
      });
      var indeg = list.map(function () { return 0; });
      after.forEach(function (xs) { xs.forEach(function (y) { indeg[y]++; }); });
      var rank = [], done = [], tracks = [];
      for (var placed = 0; placed < n; placed++) {
        var pick = -1;
        for (k = 0; k < n; k++) if (!done[k] && indeg[k] === 0 && (pick < 0 || list[k].lo < list[pick].lo)) pick = k;
        done[pick] = true;
        var min = 0;
        for (k = 0; k < n; k++) if (done[k] && k !== pick && after[k].indexOf(pick) >= 0) min = Math.max(min, rank[k] + 1);
        for (var t = min; ; t++) {
          tracks[t] = tracks[t] || [];
          if (tracks[t].every(function (o) { return o.hi < list[pick].lo || list[pick].hi < o.lo; })) break;
        }
        rank[pick] = t; list[pick].track = t; tracks[t].push(list[pick]);
        after[pick].forEach(function (y) { indeg[y]--; });
      }
      return tracks.filter(function (t) { return t.length; }).map(function (t, i) { t.forEach(function (s) { s.track = i; }); return t; });
    }

    var cols, g, routes, cw, boxW;
    for (cols = Math.max(1, Math.min(widest, Math.floor((W + MIN_GAP) / (MIN_W + MIN_GAP)))); ; cols--) {
      g = place(cols); routes = route(g, cols);
      cw = [];
      for (var k = 0; k <= cols; k++) {
        var inK = routes.filter(function (r) { return r.corr === k; });
        var n = intervalTracks(inK, function (r) { return Math.min(r.A, r.B); }, function (r) { return Math.max(r.A, r.B); }).length;
        inK.forEach(function (r) { r.ctrack = r.track; });
        cw.push(Math.max(k === 0 || k === cols ? MIN_EDGE : MIN_GAP, n ? n * TRACK + 2 * CPAD : 0));
        cw[k] = { w: cw[k], n: n };
      }
      boxW = Math.floor((W - cw.reduce(function (s, c) { return s + c.w; }, 0)) / cols);
      if (boxW >= MIN_W || cols === 1) break;
    }
    boxW = Math.max(80, Math.min(MAX_W, boxW));
    var used = cw.reduce(function (s, c) { return s + c.w; }, 0) + cols * boxW;
    var x0 = Math.max(0, Math.floor((W - used) / 2));
    var corrX = [], colX = [], x = x0;
    for (k = 0; k <= cols; k++) { corrX.push(x); x += cw[k].w; if (k < cols) { colX.push(x); x += boxW; } }
    function corrTrackX(k, t) { return corrX[k] + (cw[k].w - cw[k].n * TRACK) / 2 + TRACK * (t + 0.5); }
    function corrMid(k) { return corrX[k] + cw[k].w / 2; }

    var nRows = g.rows.length, boxes = [];
    for (i = 0; i < N; i++) boxes.push({ x: colX[g.col[i]], w: boxW, h: spec.boxes[i].h, row: g.row[i], col: g.col[i] });

    // ports: the ends on one side of a table, spread over it in the order of where each edge goes next
    var sides = {};
    routes.forEach(function (r, ri) {
      [["s", r.e.s, r.sSide, r.e.t], ["t", r.e.t, r.tSide, r.e.s]].forEach(function (p) {
        var key = p[1] + "|" + p[2];
        var toward = r.corr != null ? corrMid(r.corr) : boxes[p[3]].x + boxW / 2;
        (sides[key] = sides[key] || []).push({ r: r, end: p[0], toward: toward, ri: ri });
      });
    });
    Object.keys(sides).forEach(function (key) {
      var b = boxes[Number(key.split("|")[0])], list = sides[key];
      list.sort(function (a, c) { return a.toward - c.toward || (a.end === c.end ? a.ri - c.ri : (a.end === "s" ? -1 : 1)); });
      list.forEach(function (p, k) { p.r[p.end + "x"] = Math.round(b.x + b.w * (k + 1) / (list.length + 1)); });
    });

    // channel tracks: each horizontal part, with room for its label where it has one
    // the label goes on the part in the target's channel, or, for an edge through a corridor, on the part in the
    // source's channel when that channel has fewer labels so far: a crowded channel would put lines under labels
    var segs = [], labelsIn = {};
    routes.forEach(function (r) { if (r.A === r.B && r.e.lw > 0) labelsIn[r.A] = (labelsIn[r.A] || 0) + 1; });
    routes.forEach(function (r) {
      var e = r.e;
      if (r.A === r.B) { segs.push({ r: r, ch: r.A, x1: r.sx, x2: r.tx, label: e.lw > 0, part: "B" }); return; }
      var cx = corrTrackX(r.corr, r.ctrack), onA = e.lw > 0 && (labelsIn[r.A] || 0) < (labelsIn[r.B] || 0);
      r.cx = cx;
      if (e.lw > 0) labelsIn[onA ? r.A : r.B] = (labelsIn[onA ? r.A : r.B] || 0) + 1;
      segs.push({ r: r, ch: r.A, x1: r.sx, x2: cx, label: onA, part: "A" });
      segs.push({ r: r, ch: r.B, x1: cx, x2: r.tx, label: e.lw > 0 && !onA, part: "B" });
    });
    segs.forEach(function (s) {
      // where each end of the part leaves the channel: "down" to the row (or corridor) below, "up" to the one above
      var r = s.r, sEnd = r.sSide === "top" ? "down" : "up", tEnd = r.tSide === "top" ? "down" : "up";
      if (r.A === r.B) s.ends = [[s.x1, sEnd], [s.x2, tEnd]];
      else if (s.part === "A") s.ends = [[s.x1, sEnd], [s.x2, r.B < r.A ? "up" : "down"]];
      else s.ends = [[s.x1, r.A > r.B ? "down" : "up"], [s.x2, tEnd]];
      var a = Math.min(s.x1, s.x2), b = Math.max(s.x1, s.x2);
      s.lo = a - 4; s.hi = b + 4; s.h = 9;
      if (s.label) {
        var lw = s.r.e.lw, lx = Math.max(2, Math.min(W - lw - 2, (a + b) / 2 - lw / 2));
        s.lx = lx; s.lo = Math.min(a, lx) - 5; s.hi = Math.max(b, lx + lw) + 5; s.h = s.r.e.lh + 8;
      }
    });
    var chans = [];
    for (var c = 0; c <= nRows; c++) {
      var inC = segs.filter(function (s) { return s.ch === c; });
      var tracks = channelTracks(inC);
      var hs = tracks.map(function (t) { return Math.max.apply(null, t.map(function (s) { return s.h; })); });
      var total = hs.reduce(function (s, h) { return s + h; }, 0);
      chans.push({ segs: inC, hs: hs, h: tracks.length ? total + 2 * CHPAD : (c === 0 || c === nRows ? 4 : EMPTY_CH) });
    }
    var rowH = g.rows.map(function (r) { return Math.max.apply(null, r.map(function (b) { return spec.boxes[b].h; })); });
    var y = 0, rowY = [];
    for (c = 0; c <= nRows; c++) {
      var ch = chans[c], acc = y + CHPAD;
      ch.y = y;
      ch.segs.forEach(function (s) {
        var before = 0; for (var t = 0; t < s.track; t++) before += ch.hs[t];
        s.y = Math.round(acc + before + ch.hs[s.track] / 2);
      });
      y += ch.h;
      if (c < nRows) { rowY.push(y); y += rowH[c]; }
    }
    boxes.forEach(function (b) { b.y = rowY[b.row]; });

    var edges = routes.map(function (r) {
      var sb = boxes[r.e.s], tb = boxes[r.e.t];
      var segA = segs.filter(function (s) { return s.r === r && s.part === "A"; })[0];
      var segB = segs.filter(function (s) { return s.r === r && s.part === "B"; })[0];
      var sy = r.sSide === "top" ? sb.y : sb.y + sb.h, ty = r.tSide === "top" ? tb.y : tb.y + tb.h;
      var pts = segA ? [[r.sx, sy], [r.sx, segA.y], [r.cx, segA.y], [r.cx, segB.y], [r.tx, segB.y], [r.tx, ty]]
                     : [[r.sx, sy], [r.sx, segB.y], [r.tx, segB.y], [r.tx, ty]];
      pts = pts.filter(function (p, k) { return k === 0 || p[0] !== pts[k - 1][0] || p[1] !== pts[k - 1][1]; });
      return { points: pts, seg: segA && segA.label ? segA : segB, label: null };
    });

    // labels: on the edge's part in the target's channel, slid along its own room to cover as few other lines as can be
    function cuts(rect, own) {
      var n = 0;
      edges.forEach(function (ed, k) {
        if (k === own) return;
        for (var m = 1; m < ed.points.length; m++) {
          var p = ed.points[m - 1], q = ed.points[m];
          var x1 = Math.min(p[0], q[0]), x2 = Math.max(p[0], q[0]), y1 = Math.min(p[1], q[1]), y2 = Math.max(p[1], q[1]);
          if (x1 <= rect.x + rect.w + 2 && x2 >= rect.x - 2 && y1 <= rect.y + rect.h + 2 && y2 >= rect.y - 2) n++;
        }
      });
      return n;
    }
    edges.forEach(function (ed, k) {
      var s = ed.seg, e = routes[k].e;
      if (!s.label) return;
      var lw = e.lw, lh = e.lh, a = Math.min(s.x1, s.x2), b = Math.max(s.x1, s.x2);
      var from = Math.max(s.lo + 5, a - lw + 6), to = Math.min(s.hi - 5 - lw, b - 6);
      var best = null;
      for (var lx = from; lx <= to + 0.01; lx += 3) {
        var rect = { x: Math.round(lx), y: s.y - lh / 2, w: lw, h: lh };
        var score = cuts(rect, k) * 1000 + Math.abs(lx - s.lx);
        if (!best || score < best.score) best = { rect: rect, score: score };
      }
      ed.label = best ? best.rect : { x: Math.round(s.lx), y: s.y - lh / 2, w: lw, h: lh };
    });
    edges.forEach(function (ed) { delete ed.seg; });
    return { width: W, height: y, cols: cols, boxW: boxW, boxes: boxes, edges: edges };
  }
"""


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
svg .rel path { fill: none; stroke: var(--kg-edge); stroke-width: 1.5; stroke-linejoin: round }
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
__READ_JS__
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
__LAYOUT_JS__
  function linesOf(rv, n) {
    var t = rv.snapshot.tables[n], cols = Object.keys(t.columns || {}), key = (t.key || []).map(lower);
    var refs = {};
    (rv.snapshot.relationships || []).forEach(function (r) { if (lower(r.source) === lower(n)) r.columns.forEach(function (c) { refs[lower(c)] = 1; }); });
    var marked = cols.filter(function (c) { return key.indexOf(lower(c)) >= 0 || refs[lower(c)]; });
    var other = cols.filter(function (c) { return marked.indexOf(c) < 0; });
    var shown = marked.concat(other.slice(0, Math.max(0, 6 - marked.length)));
    var lines = shown.map(function (c) {
      return { text: c, tag: key.indexOf(lower(c)) >= 0 ? "key" : (refs[lower(c)] ? "ref" : "") };
    });
    if (cols.length > shown.length) lines.push({ text: "+" + (cols.length - shown.length) + " more columns", more: true });
    return lines;
  }
  function cut(s, chars) { return s.length > chars ? s.slice(0, Math.max(1, chars - 1)) + "…" : s; }

  function drawDiagram(rv, findings) {
    var host = document.getElementById("diagram");
    var width = Math.max(200, Math.floor(host.clientWidth || 600));
    var names = Object.keys(rv.snapshot.tables), byLower = {};
    names.forEach(function (n, i) { byLower[lower(n)] = i; });
    var items = {}; (rv.items || []).forEach(function (it) { items[it.id] = it; });
    var svg = sv("svg", { width: width, height: 10, role: "img",
                          "aria-label": "ER diagram: " + names.length + " tables, " + (rv.snapshot.relationships || []).length + " relationships" });
    var edgesG = sv("g", { "class": "edges" }), tablesG = sv("g", { "class": "tables" }), labelsG = sv("g", { "class": "labels" });
    svg.appendChild(edgesG); svg.appendChild(tablesG); svg.appendChild(labelsG);
    host.textContent = "";
    host.appendChild(svg);

    // the relationships with their labels, measured in the page before the layout
    var rels = [];
    (rv.snapshot.relationships || []).forEach(function (r) {
      var s = byLower[lower(r.source)], t = byLower[lower(r.target)];
      if (s == null || t == null) return;
      var id = "rel:" + r.source + "." + r.columns.join("+") + ">" + r.target, it = items[id] || {};
      var c = it.check || {}, res = c.result || {};
      var line2 = (c.status === "passed" || c.status === "failed" || c.status === "stale")
        ? res.rows_with_value + " rows, " + res.orphans + " orphans" + (c.status === "stale" ? " (stale)" : "") : "";
      var line1 = r.rule + (it.review && it.review !== "proposed" ? " · " + it.review : "");
      var lg = sv("g", { "class": "label" + (itemFinding(it) ? " finding" : ""), "data-for": id });
      var tx1 = sv("text", { "class": "rule", "text-anchor": "middle" }, line1);
      lg.appendChild(sv("rect", { rx: 5 })); lg.appendChild(tx1);
      var tx2 = null;
      if (line2) { tx2 = sv("text", { "text-anchor": "middle" }, line2); lg.appendChild(tx2); }
      labelsG.appendChild(lg);
      var lw = Math.ceil(Math.max(tx1.getComputedTextLength() || line1.length * 7,
                                  tx2 ? (tx2.getComputedTextLength() || line2.length * 7) : 0)) + 14;
      rels.push({ r: r, id: id, it: it, s: s, t: t, g: lg, tx1: tx1, tx2: tx2, lw: lw, lh: line2 ? 30 : 17 });
    });
    var lines = names.map(function (n) { return linesOf(rv, n); });
    var L = erLayout({ width: width, boxes: lines.map(function (ls) { return { h: 30 + ls.length * 18 + 6 }; }),
                       edges: rels.map(function (x) { return { s: x.s, t: x.t, lw: x.lw, lh: x.lh }; }) });
    svg.setAttribute("height", L.height); svg.setAttribute("viewBox", "0 0 " + width + " " + L.height);

    // tables
    names.forEach(function (n, i) {
      var b = L.boxes[i], t = rv.snapshot.tables[n], keyless = !(t.key || []).length;
      var g = sv("g", { "class": "box table" + (findings.tables[lower(n)] || keyless ? " finding" : ""), "data-table": n,
                        transform: "translate(" + b.x + "," + b.y + ")" });
      g.appendChild(sv("rect", { width: b.w, height: b.h, rx: 8 }));
      g.appendChild(sv("text", { "class": "name", x: 10, y: 19 }, cut(n, Math.floor((b.w - (keyless ? 64 : 18)) / 7.5))));
      if (keyless) g.appendChild(sv("text", { "class": "tag nokey", x: b.w - 8, y: 19, "text-anchor": "end" }, "no key"));
      g.appendChild(sv("line", { x1: 0, x2: b.w, y1: 27, y2: 27 }));
      var chars = Math.max(6, Math.floor((b.w - 46) / 7));
      lines[i].forEach(function (ln, k) {
        var yy = 27 + 16 + k * 18;
        g.appendChild(sv("text", { "class": ln.more ? "more" : "col", x: 10, y: yy }, ln.more ? ln.text : cut(ln.text, chars)));
        if (ln.tag) g.appendChild(sv("text", { "class": "tag " + ln.tag, x: b.w - 8, y: yy, "text-anchor": "end" }, ln.tag));
      });
      g.appendChild(sv("title", {}, n + (keyless ? ": no key" : ": key " + t.key.join(" + ") + " (" + t.key_rule + ")")));
      tablesG.appendChild(g);
    });

    // relationships: right-angled lines through the gaps, an arrow head into the table referred to
    rels.forEach(function (x, k) {
      var ed = L.edges[k], r = x.r, it = x.it, pts = ed.points;
      var g = sv("g", { "class": "rel" + (itemFinding(it) ? " finding" : "") + (it.review === "rejected" ? " rejected" : ""),
                        "data-id": x.id, "data-rule": r.rule, "data-source": names[x.s], "data-target": names[x.t] });
      g.appendChild(sv("path", { "class": "line", d: pts.map(function (p, m) { return (m ? "L" : "M") + p[0] + "," + p[1]; }).join(" ") }));
      var end = pts[pts.length - 1], prev = pts[pts.length - 2];
      var ang = Math.atan2(end[1] - prev[1], end[0] - prev[0]);
      var a = function (d, w) { return [end[0] - d * Math.cos(ang) + w * Math.sin(ang), end[1] - d * Math.sin(ang) - w * Math.cos(ang)]; };
      g.appendChild(sv("path", { "class": "head", d: "M" + end + " L" + a(9, 4.5) + " L" + a(9, -4.5) + " Z" }));
      g.appendChild(sv("title", {}, whatOf(it.id ? it : { type: "relationship", source: r.source, columns: r.columns, target: r.target,
                                                       target_columns: r.target_columns, rule: r.rule }) + "; " + checkText(it)));
      edgesG.appendChild(g);
      var lb = ed.label, rect = x.g.firstChild;
      rect.setAttribute("x", lb.x); rect.setAttribute("y", lb.y); rect.setAttribute("width", lb.w); rect.setAttribute("height", lb.h);
      x.tx1.setAttribute("x", lb.x + lb.w / 2); x.tx1.setAttribute("y", lb.y + 12.5);
      if (x.tx2) { x.tx2.setAttribute("x", lb.x + lb.w / 2); x.tx2.setAttribute("y", lb.y + 25.5); }
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
    if (!isObj(data)) { verdict.textContent = "The card could not read review_plan's answer; it is in the text of the tool result."; return; }
    if (data.error) { verdict.textContent = readable(data.error) + (readable(data.hint) ? " " + data.hint : ""); return; }
    var rv = data.review;
    if (!isObj(rv) || !isObj(rv.snapshot) || !rv.snapshot.tables) { verdict.textContent = "The answer holds no review file; it is in the text of the tool result."; return; }
    answer = data;
    verdict.textContent = readable(data.summary);

    var list = document.getElementById("attention-list"); list.textContent = "";
    var attention = (Array.isArray(data.attention) ? data.attention : []).filter(function (a) { return !!readable(a); });
    attention.forEach(function (a) { list.appendChild(el("li", a)); });
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

    var note = readable(data.note);
    document.getElementById("note").textContent = note;
    document.getElementById("next").hidden = !note;

    // n136: Onto says the counts, the Thinker the first line that needs attention, the Builder what to do next; every
    // sentence is a string of the answer and is on the card. Glad only when every item was checked and passed and
    // nothing needs attention.
    var all = rv.items || [];
    var passed = all.length > 0 && !attention.length &&
                 all.every(function (it) { return (it.check || {}).status === "passed"; });
    mascots({ onto: [readable(data.summary), passed ? "celebrate" : "point"],
              thinker: [attention[0] || "", "think"],
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
    var ask = "Record " + item + " as " + review + (reason ? " (" + String(reason).slice(0, 120) + ")" : "") + " with review_plan.";
    if (!canCallTools()) { note.textContent = callProblem({ kind: "unsupported" }, TOOL, ask); return; }
    note.textContent = "Asked the host to call review_plan: " + item + " " + review + ".";
    button.disabled = true;
    callTool(TOOL, args, function () { note.textContent = stillWaiting(ask); }).then(function (r) {
      var parsed = answerOf(r);
      if (parsed && isObj(parsed.review)) {
        render(parsed);
        note.textContent = "review_plan answered: " + item + " " + review + ". " + (parsed.note || "");
      } else {
        note.textContent = "review_plan answered; the answer is in the text of the tool result.";
        button.disabled = false;
      }
    }, function (e) {
      note.textContent = callProblem(e, TOOL, ask);
      button.disabled = false;
    });
  }

  window.addEventListener("message", function (event) {
    if (event.source !== window.parent) return;
    var m = event.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id != null && !m.method && pending[m.id]) {
      var p = pending[m.id]; delete pending[m.id];
      if (m.error) p.reject(m.error); else p.resolve(m.result);
      return;
    }
    if (m.method === "ui/notifications/tool-input") input = (m.params && m.params.arguments) || {};
    else if (m.method === "ui/notifications/tool-result") {
      render(answerOf(m.params));
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
  }).then(function (r) {
    hostStarted(r);
    notify("ui/notifications/initialized");
    reportSize();
    if (window.ResizeObserver) new ResizeObserver(onResize).observe(document.body);
  }, function () { document.getElementById("verdict").textContent = "The host did not start the card; the answer is in the text of the tool result."; });
})();
</script>
</body>
</html>
"""
