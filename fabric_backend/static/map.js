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
    const lines = {}, slots = {};
    let ring = [], seats = [];
    // n177: the founder, 9 November 2026: order_items → products ran as a long line through the map. Before the lines
    // are drawn, the tables take the seats on the ring that keep linked tables close: the order with the shortest lines
    // and the fewest crossings (every order for up to 8 tables, else swaps until none helps). Same seats, other tables.
    const cross = (p, q, r, t) => {
      const d = (a, b, c) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
      return d(p, q, r) * d(p, q, t) < 0 && d(r, t, p) * d(r, t, q) < 0;
    };
    function cost(order, pairs) {
      const at = {}; order.forEach((t, i) => { at[t] = seats[i]; });
      let c = 0;
      const segs = pairs.map(([a, b]) => [at[a], at[b]]);
      segs.forEach(([a, b]) => { const l = Math.hypot(a[0] - b[0], a[1] - b[1]); c += l * l / 200; });   // a long line costs more than two short ones
      for (let i = 0; i < segs.length; i++) for (let j = i + 1; j < segs.length; j++) if (cross(segs[i][0], segs[i][1], segs[j][0], segs[j][1])) c += 600;
      return c;
    }
    function bestOrder(pairs) {
      const n = ring.length;
      let best = ring.slice(), bestC = cost(best, pairs);
      if (n <= 8) {
        const rest = ring.slice(1), used = new Array(rest.length).fill(false), cur = [ring[0]];
        const go = () => {
          if (cur.length === n) { const c = cost(cur, pairs); if (c < bestC - 1e-6) { bestC = c; best = cur.slice(); } return; }
          for (let i = 0; i < rest.length; i++) if (!used[i]) { used[i] = true; cur.push(rest[i]); go(); cur.pop(); used[i] = false; }
        };
        go();
        return best;
      }
      for (let pass = 0, better = true; better && pass < 40; pass++) {
        better = false;
        for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
          const o = best.slice(); [o[i], o[j]] = [o[j], o[i]];
          const c = cost(o, pairs);
          if (c < bestC - 1e-6) { best = o; bestC = c; better = true; }
        }
      }
      return best;
    }
    function place(rels) {
      if (ring.length < 4) return;
      const pairs = [], seen = new Set();
      rels.forEach((x) => {
        const k = [x.source, x.target].sort().join("|");
        if (x.source !== x.target && pos[x.source] && pos[x.target] && !seen.has(k)) { seen.add(k); pairs.push([x.source, x.target]); }
      });
      if (!pairs.length) return;
      bestOrder(pairs).forEach((t, i) => { pos[t] = seats[i]; slots[t].setAttribute("transform", `translate(${seats[i][0]} ${seats[i][1]})`); });
    }
    this.positions = () => Object.fromEntries(Object.keys(pos).map((t) => [t, pos[t].slice()]));
    function edge(x, cls) {
      const a = pos[x.source], b = pos[x.target];
      if (!a || !b || lines[key(x.source, x.target, x.source_cols)]) return;
      const g = add(edges, "g", { class: "m-edge-g " + cls + (still ? "" : " in") });
      add(g, "line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: "m-edge" });
      if (x.rule) add(g, "text", { x: (a[0] + b[0]) / 2, y: (a[1] + b[1]) / 2 - 5, class: "m-rule", "text-anchor": "middle" }, x.rule);
      // n177: the dashed "?" says what it is on hover (the founder, 9 November 2026); a wide invisible line takes the pointer
      if (/\bm-sug\b/.test(cls)) {
        add(g, "line", { x1: a[0], y1: a[1], x2: b[0], y2: b[1], class: "m-hit" });
        add(g, "title", {}, "Suggested, not in the plan yet: " + x.source + "." + (x.source_cols || []).join(" + ") + " → " + x.target +
            ". The values match rows in " + x.target + ", but no naming rule links them: you decide.");
      }
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
          add(g, "text", { x: 0, y: -27, "text-anchor": "middle", class: "m-dom-tag" }, label);
        });
      });
      // n177: an interface line says so on the line: "interface · product_id"
      (d.interfaces || []).forEach((x) => {
        const g = lines[key(x.source, x.target, x.source_cols)];
        if (!g) return;
        g.classList.add("m-iface");
        const t = g.querySelector(".m-rule"), l = g.querySelector(".m-edge");
        const said = "interface · " + (x.source_cols || []).join(" + ");
        if (t) t.textContent = said;
        else add(g, "text", { x: (+l.getAttribute("x1") + +l.getAttribute("x2")) / 2, y: (+l.getAttribute("y1") + +l.getAttribute("y2")) / 2 - 5, class: "m-rule", "text-anchor": "middle" }, said);
      });
      return tint;
    };
    // n68: focus on the chosen domains (their slugs): their tables, the relationships among them and their interfaces
    // keep full colour, everything else is dimmed by CSS (svg.m-focus); an empty choice shows all again
    this.focus = (d, slugs) => {
      if (!svg) return;
      const chosen = (d && d.domains || []).filter((x) => slugs && slugs.includes(x.slug));
      if (!chosen.length) { svg.classList.remove("m-focus"); svg.querySelectorAll(".m-on").forEach((g) => g.classList.remove("m-on")); return; }
      const tables = new Set(chosen.flatMap((x) => x.tables)), on = new Set(chosen.map((x) => x.slug));
      svg.classList.add("m-focus");
      for (const t in groups) groups[t].classList.toggle("m-on", tables.has(t));
      const ifaces = new Set((d.interfaces || []).filter((x) => on.has(x.consumer) || on.has(x.provider)).map((x) => key(x.source, x.target, x.source_cols)));
      for (const k in lines) { const [src, , dst] = k.split("|"); lines[k].classList.toggle("m-on", (tables.has(src) && tables.has(dst)) || ifaces.has(k)); }
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
          // n177: the outer group carries the position (moved by place()), the inner one the class and its animation
          const at = add(nodes, "g", { transform: `translate(${x} ${y})`, "data-table": t.name });
          const g = add(at, "g", { class: (t.key.length ? "m-node" : "m-node m-nokey") + (still ? "" : " in"), style: still ? "" : `animation-delay:${Math.min(i * 40, 600)}ms` });
          groups[t.name] = g; slots[t.name] = at;
          add(g, "rect", { x: -w / 2, y: -21, width: w, height: 42, rx: 12 });
          add(g, "text", { x: 0, y: -3, "text-anchor": "middle", class: "m-name" }, label);
          add(g, "text", { x: 0, y: 13, "text-anchor": "middle", class: "m-key" }, t.key.length ? "key " + t.key_rule : "no key · K3");
        });
        ring = s.tables.map((t) => t.name); seats = ring.map((t) => pos[t]);
        summary(n + " tables.");
      } else if (s.step === "relationships" && svg) {
        place(s.relationships);
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
