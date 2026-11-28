"""MCP Apps, round SC2: verify_build's card as a picture a person reads at a glance.

SC1 (#218) made the verify card list what differs first, in the answer's own sentences. Those sentences are long
("shop_model (semantic model): differs. Definition: 2 difference(s) from the dry run (5 tables, 4 relationships ...
compared): Relationship orders.customer_id -> customers.customer_id is active in the dry run and inactive in Fabric.
And 1 more."), so a person who does not know what a relationship is could not tell at a glance whether the build is
fine. This script draws kg_card.verify (mcp_apps_words.verify_view) instead:

- a header with the overall state as a pill and an icon: all verified (a sage check), some differ (a mustard triangle),
  not checked (a muted dash), and the answer's own summary with its counts;
- one row per built item: an icon of its kind (simple line drawings, no product logo), its name and kind, the state's
  icon and one plain line ("Matches the plan", "2 relationships differ: active and inactive swapped", "Never run —
  run the pipeline once, then check again");
- a differing row has "Show details": what the plan had beside what Fabric has (a relationship as two ends and a line,
  solid when active and dashed when inactive, none when it is not there), the other differences in their own
  sentences, and the counts compared as numbers;
- the fixes the answer names, under "What to do".

Nothing here adds a state or a word the answer does not hold. The icons are drawn with createElementNS from the card's
own inline SVG namespace (as ontoSvg does), each with a text alternative; the disclosures are details/summary, so the
keyboard opens them. Colours follow the site's sage and mustard in light and dark.
"""
from __future__ import annotations

CSS = """
.vf { --ok: light-dark(#3F6A46, #BFDCC3); --okb: light-dark(#E6EFE6, #2C3A2F); --okf: light-dark(#6F9775, #A9C4AC);
  --w: light-dark(#7F5404, #F5D597); --wb: light-dark(#FBF0D9, #43361E); --wf: light-dark(#E3A93B, #EDBB5C); display: grid; gap: 8px; min-width: 0 }
.vf ul { margin: 0; padding-left: 18px } .vf li, .vf-sum, .vf-n { overflow-wrap: anywhere }
.vf-hd { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 10px }
.vf-p { display: inline-flex; align-items: center; gap: 6px; padding: 3px 12px 3px 6px; border-radius: 99px; font-weight: 700; background: var(--kg-card); color: var(--kg-muted) }
.vf-p[data-state="verified"] { background: var(--okb); color: var(--ok) } .vf-p[data-state="differs"] { background: var(--wb); color: var(--w) }
.vf-sum, .vf-k, .vf .vf-r figcaption, .vf-r ul { color: var(--kg-muted); font-size: 13px }
.vf ul.vf-rows { list-style: none; padding: 0; display: grid; gap: 6px }
.vf-r { display: grid; grid-template-columns: 26px minmax(0, 1fr) 20px; gap: 4px 10px; padding: 8px 10px; border: 1px solid var(--kg-line); border-left-width: 4px; border-radius: 10px }
.vf-r[data-state="verified"] { border-left-color: var(--okf) } .vf-r[data-state="differs"] { border-left-color: var(--wf) }
.vf svg { display: block; width: 100%; height: auto } .vf-t { color: var(--kg-muted) } .vf-i { width: 20px }
.vf-n { font-weight: 700 } .vf-l { display: block; font-size: 14px }
.vf-r details { grid-column: 1 / -1 } .vf-r summary { cursor: pointer; color: var(--kg-muted); font-size: 13.5px; font-weight: 600 }
.vf-r figure { margin: 6px 0 0; display: grid; gap: 6px }
.vf-c { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; font-size: 12.5px; color: var(--kg-muted) } .vf-c svg { max-width: 200px }
.vf-e { fill: none; stroke: var(--kg-ink); stroke-width: 1.6 } .vf-off { stroke-dasharray: 4 3 }
.vf-d { fill: var(--kg-bg); stroke: var(--kg-ink) } .vf-x { fill: var(--kg-ink); font: 600 11px var(--kg-font) } .vf-a { fill: var(--kg-muted); font: 11px var(--kg-font) }
.vf-nums span { display: inline-block; margin: 0 6px 4px 0; background: var(--kg-card); border-radius: 6px; padding: 1px 7px; font-size: 13px }
.vf-h { margin: 2px 0 0; font-weight: 650 }
.vf-g { fill: var(--okf) } .vf-y { fill: var(--wf) } .vf-m { fill: none; stroke: var(--kg-bg); stroke-width: 2; stroke-linecap: round }
.vf-ym { stroke: light-dark(#3a2700, #2a2111) } .vf-q, .vf-qm { fill: none; stroke: var(--kg-muted); stroke-width: 1.6 } .vf-qm { stroke-width: 2 }
.vf-kp { fill: none; stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round }
"""

JS = r"""
  // ---- SC2: the verify card as a picture (kg_card.verify): the overall state, a row per item, plan beside built ----
  var VF_W = { "verified": "Verified", "differs": "Differs", "not checked": "Not checked" }, VF_K = {
    semantic_model: "M3 4h14v12H3zM3 8h14M8 4v12", report: "M3 17h14M5 15v-5M9 15V5M13 15V8M17 15v-3",
    ontology: "M8 4a2 2 0 1 0 4 0a2 2 0 1 0-4 0M2 15a2 2 0 1 0 4 0a2 2 0 1 0-4 0M14 15a2 2 0 1 0 4 0a2 2 0 1 0-4 0M9 6l-4 7M11 6l4 7M6 15h8",
    api: "M7 3c-2 0-2 2-2 4s-1 3-2 3c1 0 2 1 2 3s0 4 2 4M13 3c2 0 2 2 2 4s1 3 2 3c-1 0-2 1-2 3s0 4-2 4",
    pipeline: "M1 8h4v4H1zM8 8h4v4H8zM15 8h4v4h-4zM5 10h3M12 10h3", notebook: "M5 2h10v16H5zM8 6h5M8 9h5M8 12h3",
    app: "M3 3h6v6H3zM11 3h6v6h-6zM3 11h6v6H3zM11 11h6v6h-6z", view: "M2 10c3-5 13-5 16 0c-3 5-13 5-16 0zM8 10a2 2 0 1 0 4 0a2 2 0 1 0-4 0",
    data_agent: "M3 4h14v9H9l-4 3v-3H3zM7 8.5h0M10 8.5h0M13 8.5h0", other: "M4 4h12v12H4z" };
  // an SVG with its text alternative; the namespace is the card's own inline SVG's (the code names no address)
  function vfSvg(box, label, cls) {
    var one = document.querySelector("svg"), NS = one ? one.namespaceURI : "", wrap = el("span", NS ? null : label, cls);
    if (!NS) return wrap;
    var s = document.createElementNS(NS, "svg");
    s.setAttribute("viewBox", box); s.setAttribute("role", "img"); s.setAttribute("aria-label", label);
    wrap.add = function (tag, a, text) {
      var e = document.createElementNS(NS, tag);
      for (var k in a) e.setAttribute(k, a[k]);
      if (text != null) e.textContent = text;
      s.appendChild(e); return wrap;
    };
    wrap.add("title", {}, label); wrap.appendChild(s); return wrap;
  }
  function vfIcon(st) {                                          // a check, a triangle or a dash, with the state's word
    var b = vfSvg("0 0 20 20", VF_W[st], "vf-i");
    if (!b.add) return b;
    if (st === "verified") return b.add("circle", { cx: 10, cy: 10, r: 9, "class": "vf-g" }).add("path", { d: "M6 10.5l2.6 2.6 5.2-5.6", "class": "vf-m" });
    if (st === "differs") return b.add("path", { d: "M10 1.8l8.6 15.4H1.4z", "class": "vf-y" }).add("path", { d: "M10 7.5v4.3M10 14.6v.2", "class": "vf-m vf-ym" });
    return b.add("circle", { cx: 10, cy: 10, r: 8.2, "class": "vf-q" }).add("path", { d: "M6.5 10h7", "class": "vf-qm" });
  }
  function vfEdge(e, v) {                                        // two tables and their line: solid active, dashed inactive
    var gone = v === "absent", cut = function (t) { t = String(t || ""); return t.length > 13 ? t.slice(0, 12) + "…" : t; };
    var b = vfSvg("0 0 160 46", e.from + " to " + e.to + ": " + (gone ? "not there" : v));
    if (!b.add) return b;
    b.add("text", { x: 2, y: 11, "class": "vf-x" }, cut(e.from)).add("text", { x: 158, y: 11, "text-anchor": "end", "class": "vf-x" }, cut(e.to));
    if (!gone) b.add("path", { d: "M8 25H146", "class": "vf-e" + (v === "inactive" ? " vf-off" : "") }).add("path", { d: "M146 25l-6-3.5v7z", "class": "vf-a" });
    return b.add("circle", { cx: 6, cy: 25, r: 4, "class": "vf-d" }).add("circle", { cx: 154, cy: 25, r: 4, "class": "vf-d" })
      .add("text", { x: 80, y: 42, "text-anchor": "middle", "class": "vf-a" }, gone ? "not there" : v);
  }
  function vfList(xs, cls) { var ul = el("ul", null, cls); xs.forEach(function (t) { ul.appendChild(el("li", t)); }); return ul; }
  function vfMore(x) {                                           // Show details: plan beside built, the rest, the counts
    var det = el("details"), fig = el("figure"), edges = arr(x.edges).filter(isObj), nums = el("div", null, "vf-nums");
    det.appendChild(el("summary", "Show details"));
    if (edges.length) {
      var cols = el("div", null, "vf-c"); cols.appendChild(el("b", "Plan")); cols.appendChild(el("b", "Built in Fabric"));
      edges.forEach(function (e) { cols.appendChild(vfEdge(e, e.plan)); cols.appendChild(vfEdge(e, e.built)); });
      fig.appendChild(cols); fig.appendChild(el("figcaption", "A solid line is an active relationship, a dashed line an inactive one."));
    }
    var rest = arr(x.rest).concat(edges.map(function (e) { return e.said; })).filter(readable);
    if (rest.length) fig.appendChild(vfList(rest));
    arr(x.numbers).forEach(function (n) { if (Array.isArray(n)) { var c = el("span"); c.appendChild(el("b", n[1])); c.appendChild(document.createTextNode(" " + n[0])); nums.appendChild(c); } });
    if (nums.firstChild) fig.appendChild(nums);
    det.appendChild(fig); return det;
  }
  function verifyView(v, result) {
    var box = el("section", null, "vf"), st = VF_W[v.state] ? v.state : "not checked", hd = el("div", null, "vf-hd"), p = el("span", null, "vf-p"), ul = el("ul", null, "vf-rows");
    box.setAttribute("data-state", st); p.setAttribute("data-state", st);
    var pi = vfIcon(st); if (pi.firstChild && pi.firstChild.nodeType === 1) pi.lastChild.setAttribute("aria-hidden", "true");
    p.appendChild(pi); p.appendChild(el("span", readable(v.head) || VF_W[st])); hd.appendChild(p);
    if (readable(result)) hd.appendChild(el("span", result, "vf-sum"));
    box.appendChild(hd);
    arr(v.items).filter(isObj).forEach(function (x) {
      var s = VF_W[x.state] ? x.state : "not checked", li = el("li", null, "vf-r"), m = el("div");
      li.setAttribute("data-state", s); li.setAttribute("data-kind", String(x.kind || ""));
      var k = vfSvg("0 0 20 20", x.word || "item", "vf-t");
      li.appendChild(k.add ? k.add("path", { d: VF_K[x.kind] || VF_K.other, "class": "vf-kp" }) : k);
      m.appendChild(el("span", x.name, "vf-n")); m.appendChild(el("span", " " + (x.word || ""), "vf-k")); m.appendChild(el("span", x.line, "vf-l"));
      li.appendChild(m); li.appendChild(vfIcon(s));
      if (s === "differs" && (arr(x.edges).length || arr(x.rest).length || arr(x.numbers).length)) li.appendChild(vfMore(x));
      ul.appendChild(li);
    });
    box.appendChild(ul);
    if (Number(v.more) > 0) box.appendChild(el("p", "and " + v.more + " more, in the raw answer", "muted"));
    var fixes = arr(v.fixes).filter(readable);
    if (fixes.length) { box.appendChild(el("p", "What to do", "vf-h")); box.appendChild(vfList(fixes)); }
    return box;
  }
"""
