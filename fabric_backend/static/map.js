// The relationship map, drawn the same way on /check and /use-cases (n59): tables on a ring with their key rule, a line
// per relationship with its rule name, a suggestion dashed with "?", an orphaned line marked. Fed the engine's step
// events (browser_check.analyze): "keys", "relationships", "validate", "suggest". The SVG is aria-hidden; the page
// lists the same findings as buttons that mark them with highlight(). With opts.still (prefers-reduced-motion) nothing
// animates in.
(function () {
  "use strict";
  function MapView(box, opts) {
    const still = !!(opts && opts.still), summary = (opts && opts.summary) || (() => {});
    const NS = "http://www.w3.org/2000/svg";
    let svg = null, edges = null, nodes = null, pos = {}, W = 760, H = 460, lit = [];
    const groups = {};
    box.replaceChildren();
    const add = (parent, tag, attrs, text) => { const x = document.createElementNS(NS, tag); for (const k in attrs) x.setAttribute(k, attrs[k]); if (text != null) x.textContent = text; parent.append(x); return x; };
    const key = (s, t, c) => s + "|" + (c || []).join("+").toLowerCase() + "|" + t;
    const lines = {};
    function edge(x, cls) {
      const a = pos[x.source], b = pos[x.target];
      if (!a || !b || lines[key(x.source, x.target, x.source_cols)]) return;
      const g = add(edges, "g", { class: "m-edge-g " + cls + (still ? "" : " in") });
      add(g, "line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: "m-edge" });
      if (x.rule) add(g, "text", { x: (a[0] + b[0]) / 2, y: (a[1] + b[1]) / 2 - 5, class: "m-rule", "text-anchor": "middle" }, x.rule);
      lines[key(x.source, x.target, x.source_cols)] = g;
    }
    // n53: mark one relationship (source, target, columns) or one table; returns whether it is on the map
    this.highlight = (x) => {
      lit.forEach((g) => g.classList.remove("m-hl")); lit = [];
      const g = !x ? null : x.table ? groups[x.table] : lines[key(x.source, x.target, x.source_cols)];
      if (g) { g.classList.add("m-hl"); lit.push(g); }
      return !!g;
    };
    // n63: domain_draft's proposal, drawn when there are two domains or more: each table's box tinted by its domain
    // (tints 0–3, then again) with the domain's name as a small label above it, never colour alone; a relationship
    // between two domains is an interface, drawn thicker. Returns the slug → tint index it used.
    this.domains = (d) => {
      const tint = {};
      if (!svg || !d || (d.domains || []).length < 2) return tint;
      d.domains.forEach((x, i) => {
        tint[x.slug] = i % 4;
        x.tables.forEach((t) => {
          const g = groups[t], p = pos[t];
          if (!g || !p) return;
          g.classList.add("m-dom", "m-dom-" + (i % 4));
          const label = x.name.length > 20 ? x.name.slice(0, 19) + "…" : x.name;
          add(g, "text", { x: p[0], y: p[1] - 27, "text-anchor": "middle", class: "m-dom-tag" }, label);
        });
      });
      (d.interfaces || []).forEach((x) => { const g = lines[key(x.source, x.target, x.source_cols)]; if (g) g.classList.add("m-iface"); });
      return tint;
    };
    this.update = (s) => {
      if (s.step === "keys") {
        const n = s.tables.length;
        H = n > 10 ? 560 : 440;
        svg = document.createElementNS(NS, "svg");
        svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
        svg.setAttribute("aria-hidden", "true");
        edges = add(svg, "g", {}); nodes = add(svg, "g", {});
        box.replaceChildren(svg);
        const rx = W / 2 - 90, ry = H / 2 - 40;
        s.tables.forEach((t, i) => {
          const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
          pos[t.name] = n === 1 ? [W / 2, H / 2] : [W / 2 + rx * Math.cos(a), H / 2 + ry * Math.sin(a)];
          const [x, y] = pos[t.name], label = t.name.length > 18 ? t.name.slice(0, 17) + "…" : t.name, w = Math.max(84, Math.min(170, 8.4 * label.length + 22));
          const g = add(nodes, "g", { class: (t.key.length ? "m-node" : "m-node m-nokey") + (still ? "" : " in"), style: still ? "" : `animation-delay:${Math.min(i * 40, 600)}ms` });
          groups[t.name] = g;
          add(g, "rect", { x: x - w / 2, y: y - 21, width: w, height: 42, rx: 12 });
          add(g, "text", { x, y: y - 3, "text-anchor": "middle", class: "m-name" }, label);
          add(g, "text", { x, y: y + 13, "text-anchor": "middle", class: "m-key" }, t.key.length ? "key " + t.key_rule : "no key · K3");
        });
        summary(n + " tables.");
      } else if (s.step === "relationships" && svg) {
        s.relationships.forEach((x) => edge(x, ""));
        summary(Object.keys(pos).length + " tables, " + s.relationships.length + " relationships found from names.");
      } else if (s.step === "validate" && svg) {
        (s.orphans || []).forEach((x) => { const g = lines[key(x.source, x.target, x.source_cols)]; if (g) g.classList.add("m-bad"); });
      } else if (s.step === "suggest" && svg) {
        (s.suggested || []).forEach((x) => edge({ ...x, rule: "?" }, "m-sug"));
      }
    };
  }

  // where a finding is on the map, most precise first: its relationship, the amount's lines → header, its table
  function where(f) {
    const a = f.amount;
    return [f.link, a && { source: a.line, target: a.header, source_cols: a.line_columns }, a && { table: a.header }, f.table && { table: f.table }].filter(Boolean);
  }

  window.KrusMap = { MapView, where };
})();
