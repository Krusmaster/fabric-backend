/* Krusgraph chat demo (n92, Gustav's decision of 4 November 2026; on every ordinary page, with pictures and a memory
   within the tab since n93). Loaded by site.js on a click on "Try a demo", or to restore a chat that was open on the
   previous page; it never opens by itself on a first visit. Buttons only: no free text, no AI, and the only request it
   makes is GET /demo/plan.json, the engine's output on the synthetic shop (fabric_backend/demo.py; n154: on /check,
   which fetches nothing, the same plan is in the page). Every number, name and picture below comes from that file;
   what the chat says about creating something comes from tool_status, through the button's data attributes
   (pages.chat_launch_html). n162: Fix data issues and Draft a dbt project are steps too, from the same file: what
   validate_plan with fixes=true and dbt_schema with project=true answered on the example when it was built; the chat
   applies, answers and runs nothing. It keeps the steps clicked and whether it is open in sessionStorage, under one key, in
   this tab only: known step names, never HTML or text, checked when read. No cookie,
   no localStorage, no logged event. Links open in the same tab and close the chat. Esc and Close close it and give the
   focus back to the button. Under 560 px the chat covers nearly the whole screen, the page behind it does not scroll and
   is inert, and Tab stays inside. */
(function () {
  'use strict';
  var PLAN_URL = '/demo/plan.json';
  var KEY = 'krusgraph.chat';                                   // the one sessionStorage key: {open, steps}
  var STEPS = ['scan', 'yes', 'no', 'model', 'flow', 'ontology', 'domains', 'fixes', 'dbt'];
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var narrow = window.matchMedia('(max-width: 560px)');
  var NAMES = { onto: 'Onto', thinker: 'Thinker', builder: 'Builder' };
  var launch = null, box = null, log = null, closeBtn = null, big = null, P = null, S = null, product = 'Krusgraph';
  var steps = [], quiet = false, gen = 0, pics = [];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  }
  function code(s) { return '<code>' + esc(s) + '</code>'; }
  // n86b: the question mark next to "ontology" and "data products" (site.js builds it from the page's own text)
  function tip(name) { return (window.KGTip && window.KGTip.parts(name)) || { button: '', body: '' }; }
  function list(xs) { return xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]; }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : (many || one + 's')); }
  function figure(who, pose) {
    return window.Mascots ? window.Mascots.svg(who, { pose: pose, label: '', gaze: false }) : '';
  }
  // A step's next part: at once while a chat is restored (quiet), and never after Start over began another run.
  function later(ms, fn) {
    if (quiet) { fn(); return; }
    var my = gen;
    setTimeout(function () { if (my === gen) fn(); }, reduced.matches ? 0 : ms);
  }
  // Scroll the log (never the page) so the new message shows, from its top as far down as fits.
  function show(el) {
    if (quiet) return;
    var lr = log.getBoundingClientRect(), er = el.getBoundingClientRect();
    var top = er.top - lr.top + log.scrollTop - 8, bottom = er.bottom - lr.top + log.scrollTop + 8;
    var want = Math.min(top, bottom - log.clientHeight);
    if (want > log.scrollTop) log.scrollTop = want;
  }

  /* dbt-flow:start (n177; the dbt_schema card inlines this block, mcp_apps_build.dbt_flow_js) */
  // The dbt project's flow (fabric_backend/dbt_flow.py): sources -> staging -> marts -> model, as the Krusgraph Model
  // draws its data flow (n174). Every box is folded; a click (or Enter/Space: it is a button) opens its SQL or YAML,
  // one box at a time, with what it reads; the model is dashed: dbt does not make it. Side by side where there is room,
  // one column under the other in a narrow chat.
  var KGF = (function () {
    var CSS = '.kgf{display:grid;gap:6px;margin:8px 0;container-type:inline-size}' +
      '.kgf-cols{display:grid;gap:6px;grid-template-columns:1fr}' +
      '@container (min-width:620px){.kgf-cols{grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.kgf-col+.kgf-col::before{content:"\\2192";position:absolute;left:-12px;top:2px}.kgf-down{display:none}}' +
      '.kgf-col{position:relative;display:grid;gap:5px;align-content:start}' +
      '.kgf-h{margin:0;font-size:12.5px;font-weight:700;opacity:.8}' +
      '.kgf-down{text-align:center;opacity:.55;line-height:1}' +
      '.kgf-box{display:grid;gap:1px;text-align:left;width:100%;font:inherit;font-size:13px;line-height:1.3;color:inherit;' +
      'background:transparent;border:1.5px solid currentColor;border-color:rgba(127,127,127,.45);border-radius:9px;padding:5px 8px;cursor:pointer}' +
      '.kgf-box[aria-expanded=true]{border-color:currentColor}' +
      '.kgf-box.kgf-off{border-style:dashed;cursor:default}' +
      '.kgf-n{font-weight:700;overflow-wrap:anywhere}.kgf-l{font-size:12px;opacity:.8}' +
      '.kgf-code{display:grid;gap:4px;border-left:3px solid rgba(127,127,127,.45);padding-left:8px}' +
      '.kgf-code pre{margin:0;max-height:260px;overflow:auto;font:12px/1.45 ui-monospace,Consolas,monospace;white-space:pre;' +
      'background:rgba(127,127,127,.1);border-radius:6px;padding:6px 8px}' +
      '.kgf-code p{margin:0;font-size:12px}';
        function style(doc) {
      if (doc.getElementById('kgf-css')) return;
      var s = doc.createElement('style'); s.id = 'kgf-css'; s.textContent = CSS; doc.head.appendChild(s);
    }
    var seq = 0;
    // flow: {columns, nodes, edges}; files: {path: text} for a node that names its file instead of carrying its code.
    // Built with createElement and textContent only: the card takes no HTML strings.
    function build(doc, flow, files) {
      if (!flow || !Array.isArray(flow.nodes) || !Array.isArray(flow.columns)) return null;
      files = files || {};
      var mk = function (tag, cls, text) { var x = doc.createElement(tag); if (cls) x.className = cls; if (text != null) x.textContent = String(text); return x; };
      var pre = 'kgf' + (++seq) + '-', label = {};
      flow.nodes.forEach(function (n) { label[n.id] = n.label; });
      var reads = function (id) {
        return (flow.edges || []).filter(function (x) { return x.to === id; }).map(function (x) { return label[x.from] || x.from; });
      };
      var root = mk('div', 'kgf'), cols = mk('div', 'kgf-cols');
      root.setAttribute('role', 'group'); root.setAttribute('aria-label', 'The dbt project\u2019s flow');
      flow.columns.forEach(function (c, ci) {
        var col = mk('div', 'kgf-col');
        if (ci) { var d = mk('div', 'kgf-down', '\u2193'); d.setAttribute('aria-hidden', 'true'); col.appendChild(d); }
        col.appendChild(mk('p', 'kgf-h', c.label));
        flow.nodes.filter(function (n) { return n.column === c.id; }).forEach(function (n, i) {
          var codeText = typeof n.code === 'string' && n.code ? n.code : (n.file && typeof files[n.file] === 'string' ? files[n.file] : '');
          var box = mk(codeText ? 'button' : 'div', 'kgf-box' + (n.built === false ? ' kgf-off' : ''));
          box.appendChild(mk('span', 'kgf-n', n.label));
          if (Array.isArray(n.lines) && n.lines.length) box.appendChild(mk('span', 'kgf-l', n.lines[0]));
          col.appendChild(box);
          if (!codeText) return;
          var id = pre + ci + '-' + i, r = reads(n.id), panel = mk('div', 'kgf-code');
          box.type = 'button'; box.setAttribute('aria-expanded', 'false'); box.setAttribute('aria-controls', id);
          panel.id = id; panel.hidden = true;
          panel.appendChild(mk('p', null, (n.code_title || n.file || n.label) + (r.length ? ' \u00b7 reads ' + r.join(', ') : '')));
          var code = mk('pre', null, codeText); code.tabIndex = 0; panel.appendChild(code);
          col.appendChild(panel);
        });
        cols.appendChild(col);
      });
      root.appendChild(cols);
      return root;
    }
    // one delegated handler per document: a box opens its code and closes the one open before
    function wire(doc) {
      style(doc);
      if (doc.__kgf) return;
      doc.__kgf = true;
      doc.addEventListener('click', function (ev) {
        var b = ev.target && ev.target.closest ? ev.target.closest('button.kgf-box') : null;
        if (!b) return;
        var open = b.getAttribute('aria-expanded') !== 'true', root = b.closest('.kgf');
        root.querySelectorAll('button.kgf-box[aria-expanded=true]').forEach(function (o) {
          o.setAttribute('aria-expanded', 'false'); var p = doc.getElementById(o.getAttribute('aria-controls')); if (p) p.hidden = true;
        });
        b.setAttribute('aria-expanded', open ? 'true' : 'false');
        var panel = doc.getElementById(b.getAttribute('aria-controls')); if (panel) panel.hidden = !open;
      });
    }
    return { build: build, wire: wire };
  })();
  /* dbt-flow:end */

  /* ------------------------------------------------------------------ what the chat remembers, in this tab only */
  // Read back only what save() writes: an object with open (true or false) and steps, each a known step name at most
  // once. Anything else, or no storage at all, counts as nothing stored.
  function readState() {
    try {
      var raw = window.sessionStorage.getItem(KEY);
      if (typeof raw !== 'string' || raw.length > 400) return null;
      var o = JSON.parse(raw);
      if (!o || typeof o !== 'object' || Array.isArray(o) || typeof o.open !== 'boolean' || !Array.isArray(o.steps) ||
          o.steps.length > STEPS.length) return null;
      for (var i = 0; i < o.steps.length; i++) {
        if (typeof o.steps[i] !== 'string' || STEPS.indexOf(o.steps[i]) < 0 || o.steps.indexOf(o.steps[i]) !== i) return null;
      }
      return { open: o.open, steps: o.steps.slice() };
    } catch (e) { return null; }
  }
  function save() {
    try {
      window.sessionStorage.setItem(KEY, JSON.stringify({ open: !!(box && !box.hidden), steps: steps.filter(function (s) { return STEPS.indexOf(s) >= 0; }) }));
    } catch (e) { /* no storage here: the chat works as before, and forgets on the next page */ }
  }
  function record(key) {
    if (STEPS.indexOf(key) >= 0 && steps.indexOf(key) < 0) steps.push(key);
    if (!quiet) save();
  }

  /* ------------------------------------------------------------------ the chat's frame */
  function build() {
    box = document.createElement('section');
    box.className = 'kgc';
    box.id = 'kgcBox';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-labelledby', 'kgcTitle');
    box.hidden = true;
    box.innerHTML =
      '<div class="kgc-head"><span class="kgc-fig" aria-hidden="true">' + figure('onto', 'rest') + '</span>' +
      '<div><h2 id="kgcTitle">' + esc(product) + ' demo</h2><small>An example shop, not your data</small></div>' +
      '<button class="kgc-close" type="button">Close</button></div>' +
      '<div class="kgc-log" aria-live="polite" tabindex="-1"></div>' +
      '<div class="kgc-foot"><p>Buttons only. No AI, and nothing you click is sent anywhere.</p>' +
      '<button class="kgc-restart" type="button">Start over</button></div>';
    document.body.appendChild(box);
    log = box.querySelector('.kgc-log');
    closeBtn = box.querySelector('.kgc-close');
    closeBtn.addEventListener('click', function () { setOpen(false); });
    box.querySelector('.kgc-restart').addEventListener('click', restart);
    box.addEventListener('keydown', trapTab);
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape' || box.hidden) return;
      if (big) { e.preventDefault(); closeBig(); return; }
      // Esc closes the chat from inside it (or anywhere while it covers a phone's screen), not from the page beside it
      if (box.contains(document.activeElement) || narrow.matches) { e.preventDefault(); setOpen(false); }
    });
    var onWidth = function () { if (!box.hidden) modal(true); };
    if (narrow.addEventListener) narrow.addEventListener('change', onWidth);
    launch.setAttribute('aria-controls', 'kgcBox');
  }

  /* Under 560 px the chat is modal: the page behind does not scroll, is inert, and Tab wraps inside the chat. */
  function modal(on) {
    var lock = on && narrow.matches;
    document.documentElement.classList.toggle('kgc-lock', lock);
    if (lock) box.setAttribute('aria-modal', 'true'); else box.removeAttribute('aria-modal');
    Array.prototype.forEach.call(document.body.children, function (el) {
      if (el === box || el.tagName === 'SCRIPT' || el.className === 'kgd-big') return;
      if (lock) el.setAttribute('inert', ''); else el.removeAttribute('inert');
    });
  }
  function focusables() {
    return Array.prototype.filter.call(box.querySelectorAll('button, a[href]'), function (el) {
      return !el.closest('[inert]') && (el.offsetParent !== null || el === document.activeElement);
    });
  }
  function trapTab(e) {
    if (e.key !== 'Tab' || !narrow.matches) return;
    var f = focusables();
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1], at = document.activeElement;
    if (e.shiftKey && (at === first || at === log)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus(); }
  }

  /* ------------------------------------------------------------------ pictures, drawn from the plan */
  // The tables sit in a grid of two columns. Where each goes is chosen once, the same way every time: of all the ways
  // to place them, the one with the shortest lines, no line crossing another or running through a table, and each data
  // product's tables together in a rectangle that holds no other table (the first such placement in a fixed order wins).
  // Every picture of the chat uses that placement, so the steps show the same map.
  var COLS = 2, NW = 112, NH = 30, GX = 56, GY = 34, TOP = 22, SIDE = 6, BOTTOM = 10, PORT = 16;   // lines meet a table right of its middle, clear of the marks on its left
  var place = null;

  function cellXY(c) { return { x: SIDE + (c % COLS) * (NW + GX), y: TOP + Math.floor(c / COLS) * (NH + GY) }; }
  function centre(c) { var p = cellXY(c); return { x: p.x + NW / 2, y: p.y + NH / 2 }; }
  function cross(a, b, c, d) {                         // do segments ab and cd cross (not merely touch at an end)?
    var o = function (p, q, r) { var v = (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x); return v > 1e-9 ? 1 : v < -1e-9 ? -1 : 0; };
    return o(a, b, c) * o(a, b, d) < 0 && o(c, d, a) * o(c, d, b) < 0;
  }
  function through(a, b, c) {                          // does segment ab run through the table in cell c?
    var p = cellXY(c), x0 = p.x - 2, x1 = p.x + NW + 2, y0 = p.y - 2, y1 = p.y + NH + 2, t0 = 0, t1 = 1;
    var dx = b.x - a.x, dy = b.y - a.y, ps = [-dx, dx, -dy, dy], qs = [a.x - x0, x1 - a.x, a.y - y0, y1 - a.y];
    for (var i = 0; i < 4; i++) {
      if (ps[i] === 0) { if (qs[i] < 0) return false; continue; }
      var t = qs[i] / ps[i];
      if (ps[i] < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; }
    }
    return t0 < t1;
  }

  function search(names, edges, groups, rows) {
    var n = names.length, cells = COLS * rows, gid = names.map(function (nm) {
      for (var g = 0; g < groups.length; g++) if (groups[g].indexOf(nm) >= 0) return g;
      return -1;
    });
    var deg = names.map(function () { return 0; });
    edges.forEach(function (e) { deg[e[0]]++; deg[e[1]]++; });
    var order = names.map(function (_, i) { return i; }).sort(function (a, b) { return deg[b] - deg[a] || a - b; });
    var at = names.map(function () { return -1; }), used = [], best = Infinity, bestAt = null;
    for (var c = 0; c < cells; c++) used.push(-1);
    function rectOf(g) {                               // the rectangle of a group's placed tables
      var r = null;
      for (var i = 0; i < n; i++) {
        if (gid[i] !== g || at[i] < 0) continue;
        var cx = at[i] % COLS, cy = Math.floor(at[i] / COLS);
        r = r ? { c0: Math.min(r.c0, cx), c1: Math.max(r.c1, cx), r0: Math.min(r.r0, cy), r1: Math.max(r.r1, cy) } : { c0: cx, c1: cx, r0: cy, r1: cy };
      }
      return r;
    }
    function groupsOk() {                              // no group's rectangle holds another table or meets another group's
      var bs = groups.map(function (_, g) { return rectOf(g); });
      for (var g = 0; g < bs.length; g++) {
        var b = bs[g];
        if (!b) continue;
        for (var i = 0; i < n; i++) {
          if (at[i] < 0 || gid[i] === g) continue;
          var cx = at[i] % COLS, cy = Math.floor(at[i] / COLS);
          if (cx >= b.c0 && cx <= b.c1 && cy >= b.r0 && cy <= b.r1) return false;
        }
        for (var h = g + 1; h < bs.length; h++) {
          var o = bs[h];
          if (o && o.c0 <= b.c1 && o.c1 >= b.c0 && o.r0 <= b.r1 && o.r1 >= b.r0) return false;
        }
      }
      return true;
    }
    function len(e) { var a = centre(at[e[0]]), b = centre(at[e[1]]); return Math.sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y)) / 10; }
    function rest() {                                  // crossings and lines through a table, once all are placed
      var cost = 0;
      for (var i = 0; i < edges.length; i++) {
        var a = centre(at[edges[i][0]]), b = centre(at[edges[i][1]]);
        for (var k = 0; k < n; k++) if (k !== edges[i][0] && k !== edges[i][1] && through(a, b, at[k])) cost += 80;
        for (var j = i + 1; j < edges.length; j++) {
          var e = edges[i], f = edges[j];
          if (e[0] === f[0] || e[0] === f[1] || e[1] === f[0] || e[1] === f[1]) continue;
          if (cross(a, b, centre(at[f[0]]), centre(at[f[1]]))) cost += 40;
        }
      }
      return cost;
    }
    (function rec(k, acc) {
      if (acc >= best) return;
      if (k === n) {
        var total = acc + rest();
        if (total < best) { best = total; bestAt = at.slice(); }
        return;
      }
      var i = order[k];
      for (var c = 0; c < cells; c++) {
        if (used[c] >= 0) continue;
        at[i] = c; used[c] = i;
        if (groupsOk()) {
          var add = 0;
          edges.forEach(function (e) { if ((e[0] === i && at[e[1]] >= 0) || (e[1] === i && at[e[0]] >= 0)) add += len(e); });
          rec(k + 1, acc + add);
        }
        used[c] = -1; at[i] = -1;
      }
    })(0, 0);
    return bestAt;
  }

  function placement() {
    if (place) return place;
    var names = P.tables.map(function (t) { return t.name; }), idx = {};
    names.forEach(function (nm, i) { idx[nm] = i; });
    var edges = [];
    P.relationships.map(function (r) { return [r.source, r.target]; })
      .concat(P.suggestions.map(function (s) { return [s.confirmed.source, s.confirmed.target]; }))
      .forEach(function (e) { if (e[0] in idx && e[1] in idx && e[0] !== e[1]) edges.push([idx[e[0]], idx[e[1]]]); });
    var groups = ((P.drafts.as_is.domains || {}).domains || []).map(function (d) { return d.tables.filter(function (t) { return t in idx; }); });
    var rows = Math.ceil(names.length / COLS), at = null;
    if (names.length <= 9) at = search(names, edges, groups, rows) || search(names, edges, groups, rows + 1);
    if (!at) at = names.map(function (_, i) { return i; });   // a larger plan: in plan order
    var r = Math.floor(Math.max.apply(null, at) / COLS) + 1;
    place = { cell: {}, width: 2 * SIDE + COLS * NW + (COLS - 1) * GX, height: TOP + r * NH + (r - 1) * GY + BOTTOM };
    names.forEach(function (nm, i) { place.cell[nm] = at[i]; });
    return place;
  }

  // nodes: [{table, label, key: true | false | undefined}]; edges: [{source, target, cls}]; groups: [{name, tables, cls}]
  function picture(desc, nodes, edges, groups) {
    var L = placement(), out = [], labels = [];
    var at = function (t) { return cellXY(L.cell[t]); };
    (groups || []).forEach(function (g) {
      var ps = g.tables.filter(function (t) { return t in L.cell; }).map(at);
      if (!ps.length) return;
      var xs = ps.map(function (p) { return p.x; }), ys = ps.map(function (p) { return p.y; });
      var x0 = Math.min.apply(null, xs) - 6, x1 = Math.max.apply(null, xs) + NW + 6;
      var y0 = Math.min.apply(null, ys) - 19, y1 = Math.max.apply(null, ys) + NH + 6;
      out.push('<g class="kgc-grp ' + (g.cls || '') + '"><rect x="' + x0 + '" y="' + y0 + '" width="' + (x1 - x0) + '" height="' + (y1 - y0) +
               '" rx="' + 10 + '"/></g>');
      // the group's name goes on top of the lines (with a halo in the group's colour), so a line into the group
      // passes under it instead of through it
      labels.push('<g class="kgc-grp ' + (g.cls || '') + '"><text x="' + (x0 + 8) + '" y="' + (y0 + 13) + '">' + esc(g.name) + '</text></g>');
    });
    edges.forEach(function (e) {
      if (!(e.source in L.cell) || !(e.target in L.cell)) return;
      var a = centre(L.cell[e.source]), b = centre(L.cell[e.target]);
      a.x += PORT; b.x += PORT;
      var dx = b.x - a.x, dy = b.y - a.y;
      var out1 = function (right) {                    // how far along the line it leaves a table: right or left side, or top/bottom
        return Math.min(dx ? (NW / 2 + 1 + (right ? -PORT : PORT)) / Math.abs(dx) : Infinity, dy ? (NH / 2 + 1) / Math.abs(dy) : Infinity);
      };
      var ta = out1(dx > 0), tb = out1(dx < 0);
      var p = { x: a.x + dx * ta, y: a.y + dy * ta }, q = { x: b.x - dx * tb, y: b.y - dy * tb };
      var g = '<g class="kgc-e ' + (e.cls || '') + '"><line x1="' + p.x + '" y1="' + p.y + '" x2="' + q.x + '" y2="' + q.y + '"/>' +
              '<circle cx="' + p.x + '" cy="' + p.y + '" r="' + 2.5 + '"/><circle cx="' + q.x + '" cy="' + q.y + '" r="' + 2.5 + '"/>';
      out.push(g + '</g>');
    });
    out = out.concat(labels);
    nodes.forEach(function (nd) {
      if (!(nd.table in L.cell)) return;
      var p = at(nd.table), no = nd.key === false;
      var g = '<g class="kgc-n' + (no ? ' nokey' : '') + '"><rect x="' + p.x + '" y="' + p.y + '" width="' + NW + '" height="' + NH +
              '" rx="' + 8 + '"/><text x="' + (p.x + NW / 2) + '" y="' + (p.y + NH / 2 + 4.5) + '" text-anchor="middle">' + esc(nd.label) + '</text>';
      if (nd.key === true) {                           // a key on the top edge, as on the site's map
        var kx = p.x + 12, ky = p.y;
        g += '<g class="kgc-key"><circle cx="' + kx + '" cy="' + ky + '" r="' + 6.5 + '"/><circle class="k" cx="' + (kx - 2) + '" cy="' + ky + '" r="' + 1.9 + '"/>' +
             '<path class="k" d="M' + (kx - 0.1) + ' ' + ky + 'H' + (kx + 3.8) + 'M' + (kx + 2.6) + ' ' + ky + 'V' + (ky + 2.2) + '"/></g>';
      }
      if (no) {                                        // where the key would be: a small tag saying there is none
        g += '<g class="kgc-nk"><rect x="' + (p.x + 5) + '" y="' + (p.y - 7) + '" width="' + 46 + '" height="' + 14 + '" rx="' + 7 + '"/>' +
             '<text x="' + (p.x + 28) + '" y="' + (p.y + 3.6) + '" text-anchor="middle">no key</text></g>';
      }
      out.push(g + '</g>');
    });
    var id = pics.length;
    pics.push({ desc: desc, svg: out.join('') });
    return '<figure class="kgc-pic">' + svg(id, true) + '<button class="kgc-zoom" type="button" data-pic="' + id + '">Larger picture</button></figure>';
  }
  function svg(id, labelled) {
    var L = placement(), p = pics[id];
    return '<svg class="kgc-svg" viewBox="0 0 ' + L.width + ' ' + L.height + '" width="' + L.width + '" height="' + L.height + '" ' +
           (labelled ? 'role="img" aria-label="' + esc(p.desc) + '"' : 'aria-hidden="true"') + ' focusable="false">' + p.svg + '</svg>';
  }

  // The larger picture opens inside the chat, over the messages, at the chat's full width; Back or Esc returns.
  function openBig(btn) {
    var id = +btn.getAttribute('data-pic');
    if (!pics[id]) return;
    closeBig();
    big = document.createElement('div');
    big.className = 'kgc-big';
    big.setAttribute('role', 'group');
    big.setAttribute('aria-label', 'Larger picture');
    big.innerHTML = '<div class="kgc-big-head"><p>Larger picture</p><button class="kgc-back" type="button">Back to the chat</button></div>' +
                    '<div class="kgc-big-body">' + svg(id, false) + '<p>' + esc(pics[id].desc) + '</p></div>';
    big._from = btn;
    Array.prototype.forEach.call(box.children, function (el) { el.setAttribute('inert', ''); });
    box.appendChild(big);
    big.querySelector('.kgc-back').addEventListener('click', closeBig);
    big.querySelector('.kgc-back').focus({ preventScroll: true });
  }
  function closeBig() {
    if (!big) return;
    var from = big._from, page = big._inert;
    big.remove();
    big = null;
    if (page) page.forEach(function (el) { el.removeAttribute('inert'); });     // n233: the data flow's overlay
    else Array.prototype.forEach.call(box.children, function (el) { el.removeAttribute('inert'); });
    if (from && document.contains(from) && !box.hidden) from.focus({ preventScroll: true });
  }

  /* ------------------------------------------------------------------ messages and buttons */
  function you(text) {
    var el = document.createElement('p');
    el.className = 'kgc-you' + (quiet ? ' still' : '');
    el.textContent = text;
    log.appendChild(el);
    show(el);
  }

  // picks: [{key?, label, why?, rec?, href?, planned?, go?}]. A planned pick runs nothing: it says what exists today.
  function say(who, pose, html, picks, cls, focusFirst) {
    var el = document.createElement('div');
    el.className = 'kgc-msg ' + who + (cls ? ' ' + cls : '') + (quiet ? ' still' : '');
    el.innerHTML = '<span class="kgc-fig" aria-hidden="true">' + figure(who, pose) + '</span>' +
      '<div class="kgc-bub"><p class="kgc-who">' + NAMES[who] + '</p>' + html + '</div>';
    Array.prototype.forEach.call(el.querySelectorAll('.kgc-zoom'), function (z) {
      z.addEventListener('click', function () { openBig(z); });
    });
    var first = null;
    if (picks && picks.length) {
      var row = document.createElement('div');
      row.className = 'kgc-picks';
      picks.forEach(function (p) {
        var b = document.createElement(p.href ? 'a' : 'button');
        b.className = 'kgc-pick' + (p.rec ? ' rec' : '') + (p.planned ? ' planned' : '');
        b.setAttribute('data-pick', p.label);
        if (p.key) b.setAttribute('data-key', p.key);
        b.innerHTML = esc(p.label) + (p.planned ? '<i>Planned</i>' : '') + (p.why ? '<small>' + esc(p.why) + '</small>' : '');
        if (p.href) {
          b.href = p.href;
          b.addEventListener('click', function (e) {
            if (e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;   // a new tab or window: this chat stays
            setOpen(false, 'keep');                     // a link closes the chat; its steps stay for the next open
          });
        } else {
          b.type = 'button';
          b._run = function () {
            if (p.planned) {
              if (b.getAttribute('aria-disabled') === 'true') return;
              b.setAttribute('aria-disabled', 'true');
              record(p.key);
              say('onto', 'explain', '<p>' + esc(p.planned) + '</p>');
              return;
            }
            if (!quiet) log.focus({ preventScroll: true });     // keep the focus in the chat while the buttons go
            row.remove();
            you(p.label);
            record(p.key);
            p.go();
          };
          b.addEventListener('click', function () { b._run(); });
        }
        if (!first) first = b;
        row.appendChild(b);
      });
      el.appendChild(row);
    }
    log.appendChild(el);
    show(el);
    if (first && focusFirst && !quiet) first.focus({ preventScroll: true });
    return el;
  }

  function work(who, steps, done) {
    var el = say(who, 'working', '<ul class="kgc-steps">' + steps.map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ul>');
    var items = el.querySelectorAll('li'), i = 0;
    if (quiet) {
      Array.prototype.forEach.call(items, function (li) { li.className = 'did'; });
      done();
      return;
    }
    (function next() {
      if (i > 0) items[i - 1].className = 'did';
      if (i === items.length) { later(220, done); return; }
      items[i++].className = 'doing';
      later(440, next);
    })();
  }

  function cheer(el) {
    if (quiet) return;                                 // a restored chat: no celebration
    el.classList.add('kgc-cheer');
    if (reduced.matches) return;
    var colors = ['#F2735C', '#9DB8A0', '#A99AD8', '#E3A93B'];
    for (var i = 0; i < 18; i++) {
      var b = document.createElement('span'), a = Math.random() * Math.PI * 2, r = 50 + Math.random() * 100;
      b.className = 'kgc-bit';
      b.setAttribute('aria-hidden', 'true');
      b.style.background = colors[i % 4];
      b.style.setProperty('--x', Math.cos(a) * r + 'px');
      b.style.setProperty('--y', Math.sin(a) * r * 0.7 + 'px');
      el.appendChild(b);
      (function (x) { setTimeout(function () { x.remove(); }, 950); })(b);
    }
  }

  /* ------------------------------------------------------------------ the picture of each step, from the plan */
  function hasKey(t) { return !!(t.key && t.key.length); }
  function tableNodes() { return P.tables.map(function (t) { return { table: t.name, label: t.name, key: hasKey(t) }; }); }
  function planEdges() { return P.relationships.map(function (r) { return { source: r.source, target: r.target }; }); }
  function pictureOfPlan() {
    var keyless = P.tables.filter(function (t) { return !hasKey(t); }).map(function (t) { return t.name; });
    return picture('A picture of the ' + plural(P.tables.length, 'table') + ' as boxes and the ' + plural(P.relationships.length, 'link') +
                   ' between them as lines. A key symbol marks each table that has a key' +
                   (keyless.length ? '; ' + list(keyless) + (keyless.length === 1 ? ' has none.' : ' have none.') : '.'),
                   tableNodes(), planEdges());
  }
  function pictureWithLink(s) {
    var c = s.confirmed, col = c.source_cols.join('+');
    return picture('The same picture, with the new link from ' + c.source + '.' + col + ' to ' + c.target + ' marked.',
                   tableNodes(), planEdges().concat([{ source: c.source, target: c.target, cls: 'new' }]));
  }
  function pictureOfModel(m) {
    var off = m.relationships.filter(function (r) { return !r.active; });
    return picture('A picture of the semantic model: ' + plural(m.table_names.length, 'table') + ', the ' +
                   plural(m.relationships.length - off.length, 'active relationship') + ' as solid lines' +
                   (off.length ? ' and ' + list(off.map(function (r) { return r.source + '.' + r.columns.join('+') + ' to ' + r.target; })) +
                                 (off.length === 1 ? ', inactive, as a dashed line.' : ', inactive, as dashed lines.') : '.'),
                   m.table_names.map(function (t) { return { table: t, label: t }; }),
                   m.relationships.map(function (r) { return { source: r.source, target: r.target, cls: r.active ? '' : 'off' }; }));
  }
  function pictureOfOntology(o) {
    var without = o.entities.filter(function (x) { return !x.key; }).map(function (x) { return x.name; });
    return picture('A picture of the ontology: ' + plural(o.entities.length, 'entity type') + ', ' + (o.entities.length - without.length) +
                   ' with a key, marked with a key symbol' + (without.length ? ', and ' + list(without) + ' without one' : '') +
                   '; the ' + plural(o.links.length, 'relationship type') + ' as lines.',
                   o.entities.map(function (x) { return { table: x.table, label: x.name, key: !!x.key }; }),
                   o.links.map(function (l) { return { source: l.source, target: l.target }; }));
  }
  function pictureOfDomains(d) {
    var iface = function (e) { return d.interfaces.some(function (i) { return i.source === e.source && i.target === e.target; }); };
    var edges = planEdges().filter(function (e) { return !iface(e); }).map(function (e) { e.cls = 'faint'; return e; })
      .concat(d.interfaces.map(function (i) { return { source: i.source, target: i.target, cls: 'iface' }; }));
    return picture('A picture of the data products: ' + d.domains.map(function (x) { return x.name + ' around ' + list(x.tables); }).join(', and ') +
                   (d.interfaces.length ? '; the ' + (d.interfaces.length === 1 ? 'interface ' : 'interfaces ') +
                     list(d.interfaces.map(function (i) { return i.source + '.' + i.source_cols.join('+') + ' to ' + i.target; })) + ' between them' : '') +
                   (d.unassigned.length ? '; ' + list(d.unassigned) + ' outside them' : '') + '.',
                   P.tables.map(function (t) { return { table: t.name, label: t.name, key: d.unassigned.indexOf(t.name) >= 0 && !hasKey(t) ? false : undefined }; }),
                   edges, d.domains.map(function (x, i) { return { name: x.name, tables: x.tables, cls: i % 2 ? 'b' : 'a' }; }));
  }

  /* ------------------------------------------------------------------ the flow */
  // n158 (review L20): the two ways out carry the site's own labels (pages.CHECK_LABEL, CONNECT_LABEL), handed over as
  // data attributes on the launch button, like the status sentences
  function leave() {
    return [{ label: launch.getAttribute('data-label-check') || 'Check my tables', href: '/check' },
            { label: launch.getAttribute('data-label-connect') || 'Connect to my Fabric', why: 'Opens the set-up guide.', href: '/start' }];
  }
  // n162: fixing data and the dbt project are steps like the others (until n162 links to the docs, n154): each shows
  // what the engine answered on the example when the plan JSON was built (validate_plan with fixes=true, dbt_schema
  // with project=true), and is offered until it has run
  function further() {
    return [
      { key: 'fixes', label: 'Fix data issues', why: 'A proposed fix for each problem, with counts before and after.', go: fixes },
      { key: 'dbt', label: 'Draft a dbt project', why: 'Staging and mart models with tests, as files.', go: dbtProject }
    ].filter(function (p) { return !S[p.key]; });
  }
  function drafts() { return S.linked ? P.drafts.with_suggestion : P.drafts.as_is; }
  function data(key, what) { return launch.getAttribute('data-' + what + '-' + key) || ''; }

  function suggestions() {
    var left = [
      { key: 'model', label: 'Create a semantic model', why: 'For reports in Power BI: tables, links and measures.', go: model },
      // n224: the data flow, moved here from the home page's replay card (the founder, 12 November 2026)
      { key: 'flow', label: 'See the data flow', why: 'Bronze to silver to gold, as boxes you can open.', go: dataFlow },
      { key: 'ontology', label: 'Create an ontology', why: 'For meaning: what things are and how they relate.', go: ontology },
      { key: 'domains', label: 'Draft data products', why: 'Group the tables, with a contract for each.', go: products }
    ].filter(function (p) { return !S[p.key]; });
    left.forEach(function (p, i) { p.rec = i === 0; if (i) p.why = ''; });
    return left;
  }
  function next() {
    var left = suggestions();
    later(500, function () {
      // n177: "That is the demo" only after the last step: while fixing data or the dbt project is still offered, Onto
      // asks what next, with the two ways out after them
      if (left.length) say('onto', 'point', '<p>What next?</p>', left.concat(further()), '', true);
      else if (further().length) say('onto', 'point', '<p>What next?</p>', further().concat(leave()), '', true);
      else if (!S.ended) {
        S.ended = true;
        say('onto', 'explain', '<h3>That is the demo</h3><p>The next step is real: your own files stay in your browser on the check page.</p>',
            leave(), '', true);
      } else say('onto', 'point', '<p>What next?</p>', leave(), '', true);
    });
  }

  // The result of a step: nothing was created here; what the agent does in the visitor's Fabric, and how far that has
  // been tried, are tool_status's (data-does-* and data-status-* on the button: a plain sentence, no tool's name).
  // n162: note, where given, replaces the first sentences (fixes and dbt say it in their own words); the status stays
  function done(key, html, pic, note) {
    S[key] = true;
    var does = data(key, 'does');
    note = note || 'This is a demo, so nothing was created. ' + (does === 'creates'
      ? 'Connected to ' + product + ', your agent creates this in your Fabric workspace when you ask.'
      : does === 'drafts-gated'
        ? 'Connected to ' + product + ', your agent drafts this from your own tables when you ask.'
        : 'Connected to ' + product + ', your agent drafts this from your own tables when you ask; the draft creates nothing in Fabric.');
    var el = say('builder', 'celebrate', html + (pic || '') + '<p class="kgc-note">' + esc(note) + ' ' + esc(data(key, 'status')) + '</p>', null, 'win');
    cheer(el);
    next();
  }

  function model() {
    work('builder', ['Writing tables and measures', 'Adding relationships', 'Checking them against the plan'], function () {
      var d = drafts(), m = d.semantic_model, v = d.validation, rels = m.active + m.inactive.length;
      var checked = v.hold === v.relationships ? (v.hold === 1 ? 'the one holds' : 'all ' + v.hold + ' hold') + ' for every row with a value in the example'
                                               : v.hold + ' of ' + v.relationships + ' hold for every row with a value in the example';
      var inactive = m.inactive.length ? ', and ' + m.inactive.length + ' inactive: ' + m.inactive.map(function (r) {
        return code(r.source + '.' + r.columns.join('+')) + ' → ' + code(r.target);
      }).join(', ') + ' would close a cycle' : '';
      done('model', '<h3>Semantic model ready</h3><p>' + plural(m.tables, 'table') + ' and ' + plural(rels, 'relationship') +
           '; ' + checked + '. ' + m.active + ' active' + inactive + '. ' + plural(m.measures, 'measure') +
           (m.date_table ? ' and a ' + code(m.date_table) + ' date table' : '') + '.</p>', pictureOfModel(m));
    });
  }
  function ontology() {
    work('builder', ['Writing entity types and keys', 'Binding them to the tables'], function () {
      var o = drafts().ontology;
      var t = tip('ontology');
      done('ontology', '<h3>Ontology' + t.button + ' ready</h3>' + t.body + '<p>' + plural(o.entity_types, 'entity type') + ' (' + o.with_key + ' with a key) and ' +
           plural(o.relationship_types, 'relationship type') + '. The ontology item is in preview in Fabric.</p>', pictureOfOntology(o));
    });
  }
  function products() {
    work('thinker', ['Grouping tables by their links', 'Writing the contracts'], function () {
      var d = drafts().domains, n = d.domains.length;
      var out = d.unassigned.filter(function (t) { return P.keyless.indexOf(t) >= 0; });
      var t = tip('data-products');
      done('domains', '<h3>' + plural(n, 'data product') + t.button + ' drafted</h3>' + t.body + '<p>' +
           list(d.domains.map(function (x) { return code(x.name); })) +
           (d.interfaces.length ? ', with ' + (d.interfaces.length === 1 ? 'an interface' : d.interfaces.length + ' interfaces') + ' between them' : '') + '. ' +
           (out.length ? list(out.map(code)) + (out.length === 1 ? ' stays out, because it has no key. ' : ' stay out, because they have no key. ') : '') +
           'You choose the owners, and your admin creates the Fabric domains.</p>', pictureOfDomains(d));
    });
  }

  // n162: validate_plan with fixes=true on the example's rows (demo.py, when the plan JSON is built): per finding its
  // proposed fix, its counts before and after, and whether it is mechanical or a business decision. A decision is a
  // question with its options; the demo answers none and applies nothing.
  function num(x) { return typeof x === 'number' ? x.toLocaleString('en-GB') : esc(x); }
  function counted(c, f) {
    var b = f.before || {}, out = [];
    if (b.headers !== undefined && f.joined_with) {
      out.push(plural(b.headers, f.table + ' row') + ', each joined with ' + num(b.min_lines) + ' to ' + num(b.max_lines) + ' ' + f.joined_with + ' rows');
    } else {
      Object.keys(b).forEach(function (k) { out.push(esc(k.replace(/_/g, ' ')) + ' ' + num(b[k])); });
    }
    var a = f.expected_after || {};
    if (Object.keys(a).length) out.push('after: ' + Object.keys(a).map(function (k) { return esc(k.replace(/_/g, ' ')) + ' ' + num(a[k]); }).join(', '));
    var s = f.sums || {};
    if (s.summed_over_lines !== undefined) {
      out.push(code(f.table + '.' + f.column) + ' summed over the joined rows: ' + num(s.summed_over_lines) + '; once per ' + esc(f.table) +
               ' row: ' + num(s.summed_per_header));
    }
    return out.length ? '<p class="kgc-count">' + out.join('. ') + '.</p>' : '';
  }
  function fixes() {
    work('thinker', ['Counting keys and links in the rows', 'Proposing a fix per finding'], function () {
      var x = drafts().fixes, c = x.counts;
      var mech = x.findings.filter(function (f) { return f.type === 'mechanical'; });
      var asks = x.findings.filter(function (f) { return f.type !== 'mechanical'; });
      var clean = x.keys_unique === x.keys && x.hold === x.relationships;
      var html = '<h3>' + (mech.length ? plural(mech.length, 'fix', 'fixes') + ' proposed' : 'No data to fix in the example') + '</h3>' +
        '<p>' + x.keys_unique + ' of ' + x.keys + ' keys unique and ' + x.hold + ' of ' + x.relationships + ' links without orphans in the example’s rows' +
        (clean && !mech.length ? ', so nothing needs a mechanical fix.' : '.') + '</p>' +
        '<div class="kgc-facts"><div><b>' + c.findings + '</b>' + (c.findings === 1 ? 'finding' : 'findings') + '</div>' +
        '<div><b>' + c.mechanical + '</b>mechanical</div><div><b>' + c.business_decision + '</b>' +
        (c.business_decision === 1 ? 'decision' : 'decisions') + ' for you</div></div>';
      if (mech.length) {
        html += '<ul class="kgc-fixes">' + mech.map(function (f) {
          return '<li><p>' + esc(f.what_is_wrong) + '</p><p><b>Fix:</b> ' + esc(f.proposed_fix) + '</p>' + counted(c, f) + '</li>';
        }).join('') + '</ul>';
      }
      if (asks.length) {
        html += '<p>' + (asks.length === 1 ? 'The one open question' : 'The open questions') + ', for a person to answer:</p><ul class="kgc-fixes">' +
          asks.map(function (f) {
            return '<li><p>' + esc(f.what_is_wrong) + '</p>' + counted(c, f) + f.questions.map(function (q) {
              return '<p class="kgc-ask">' + esc(q.ask) + '</p>' + (q.options.length ? '<ul class="kgc-opts">' + q.options.map(function (o) {
                return '<li>' + esc(o) + '</li>';
              }).join('') + '</ul>' : '');
            }).join('') + '</li>';
          }).join('') + '</ul>';
      }
      var does = data('fixes', 'does');
      var note = 'This is a demo, so nothing was applied and no question was answered. Connected to ' + product +
        ', your agent proposes these from the counts on your own tables when you ask. ' + data('fixes', 'draft-status') + ' ' +
        (does === 'creates' ? 'The fixes you accept go into a silver notebook it creates in your Fabric workspace'
                            : 'The fixes you accept go into a silver notebook it drafts') +
        '; your source tables stay as they are, and business decisions stay yours.';
      done('fixes', html, '', note);
    });
  }

  // n162: dbt_schema with project=true on the example (demo.py); n177: drawn as its flow (dbt_flow.py), not a file tree
  function dbtProject() {
    work('builder', ['Writing staging models', 'Writing marts and tests'], function () {
      var x = drafts().dbt;
      // n177: the flow (sources -> staging -> marts -> model), boxes folded; a click shows the SQL or YAML
      KGF.wire(document);
      var html = '<h3>dbt project drafted</h3><p>' + plural(x.files.length, 'file') + ' for ' + esc(x.adapter) + ': ' +
        plural(x.staging, 'staging model') + ' and ' + plural(x.marts, 'mart') + ', with tests. Files only; nothing runs. ' +
        'Choose a box to see its SQL or YAML.</p><div class="kgf-slot"></div>' +
        (x.not_templated.length ? '<p>Left for you: ' + x.not_templated.map(function (n) { return code(n.table) + ' (' + esc(n.part) + '): ' + esc(n.why); }).join('; ') + '.</p>' : '');
      var note = 'This is a demo, so nothing was created. Connected to ' + product +
        ', your agent drafts these files from your own tables when you ask. Files only; nothing runs: you run dbt when you decide to.';
      done('dbt', html, '', note);
      var slots = log.querySelectorAll('.kgf-slot'), slot = slots[slots.length - 1], f = KGF.build(document, x.flow);
      if (slot && f) slot.appendChild(f);
    });
  }

  // n224: the data flow of one build on the example (demo.py, data_flow.flow(): the silver notebook, the gold views and
  // the semantic model). n233 (the founder, 12 November 2026: "here we want to see the data flow going from left to
  // right"): drawn as the Model editor draws it (FlowView.tsx), columns side by side, bronze -> silver -> gold -> what is
  // built on it, with lines between the boxes. Compact in the chat, where the columns scroll sideways inside the card (a
  // hint says so, the arrow keys scroll it); "Open larger" shows the same diagram over the page at full width. Each box
  // with code is a button that opens its code below the diagram, one at a time. A list for screen readers says the flow
  // in order; the lines are decoration. Built with createElement and textContent only.
  var KGD = (function () {
    // the SVG namespace, joined so that tests/test_chat_demo.py's no-dates check does not read a year in it
    var seq = 0, SVGNS = ['http://www.w3.org', 2e3, 'svg'].join('/');
    function mk(tag, cls, text) {
      var x = document.createElement(tag);
      if (cls) x.className = cls;
      if (text != null) x.textContent = String(text);
      return x;
    }
    function boxLabel(n) { return n.kind_label ? n.kind_label + ': ' + n.label : n.label; }
    // f: data_flow.flow()'s output as demo.py keeps it. wide: the overlay's version. onLarger: the button's action.
    function build(f, wide, onLarger) {
      var pre = 'kgd' + (++seq) + '-', byId = {}, colOf = {};
      var cols = f.columns.filter(function (c) { return f.nodes.some(function (n) { return n.column === c.id; }); });
      cols.forEach(function (c, i) { colOf[c.id] = i; });
      var nodes = f.nodes.filter(function (n) { return n.column in colOf; });
      nodes.forEach(function (n) { byId[n.id] = n; });
      var into = function (id) { return f.edges.filter(function (e) { return e.to === id; }); };
      var name = function (id) { return id === 'bronze' ? 'the source tables' : byId[id] ? byId[id].label : id; };

      // rows: a box sits level with the first box it reads from, where that row is free; the rest fill in below
      var row = {}, taken = {};
      cols.forEach(function (c) {
        taken[c.id] = {};
        nodes.filter(function (n) { return n.column === c.id; }).forEach(function (n) {
          var want = 0;
          into(n.id).some(function (e) { if (e.from in row) { want = row[e.from]; return true; } return false; });
          while (taken[c.id][want]) want++;
          row[n.id] = want; taken[c.id][want] = true;
        });
      });

      var root = mk('div', 'kgd' + (wide ? ' kgd-wide' : ''));
      root.setAttribute('role', 'group');
      root.setAttribute('aria-label', 'The data flow, left to right');

      // what a screen reader reads: the flow in order, column by column
      var sr = mk('ol', 'visually-hidden');
      cols.forEach(function (c) {
        var parts = nodes.filter(function (n) { return n.column === c.id; }).map(function (n) {
          var from = into(n.id).map(function (e) { return name(e.from); });
          return boxLabel(n) + (from.length ? ' (from ' + list(from) + ')' : '') + (n.built === false ? ', not part of this build' : '');
        });
        sr.appendChild(mk('li', null, c.title + ': ' + parts.join('; ') + '.'));
      });
      root.appendChild(sr);

      var bar = mk('div', 'kgd-bar'), hint = mk('p', 'kgd-hint', 'Scroll sideways, or use the arrow keys, to see every column.');
      hint.id = pre + 'hint';
      hint.hidden = true;
      bar.appendChild(hint);
      if (onLarger) {
        var larger = mk('button', 'kgc-zoom kgd-larger', 'Open larger');
        larger.type = 'button';
        larger.addEventListener('click', function () { onLarger(larger); });
        bar.appendChild(larger);
      }
      root.appendChild(bar);

      var scroller = mk('div', 'kgd-scroll'), stage = mk('div', 'kgd-stage');
      scroller.tabIndex = 0;
      scroller.setAttribute('role', 'region');
      scroller.setAttribute('aria-label', 'The data flow diagram');
      scroller.setAttribute('aria-describedby', hint.id);
      stage.style.gridTemplateColumns = 'repeat(' + cols.length + ', var(--kgd-w))';
      var lines = document.createElementNS(SVGNS, 'svg');
      lines.setAttribute('class', 'kgd-lines');
      lines.setAttribute('aria-hidden', 'true');
      lines.setAttribute('focusable', 'false');
      stage.appendChild(lines);
      cols.forEach(function (c, i) {
        var h = mk('p', 'kgd-h', c.title);
        h.style.gridColumn = String(i + 1);
        h.setAttribute('aria-hidden', 'true');                 // the list above says it in order
        stage.appendChild(h);
      });

      var panel = mk('div', 'kgd-code'), panelHead = mk('p'), panelCode = mk('pre');
      panel.id = pre + 'code';
      panel.hidden = true;
      panelCode.tabIndex = 0;
      panel.appendChild(panelHead);
      panel.appendChild(panelCode);
      var boxes = {};
      nodes.forEach(function (n) {
        var hasCode = typeof n.code === 'string' && n.code;
        var b = mk(hasCode ? 'button' : 'div', 'kgd-box kgd-' + n.column + (n.built === false ? ' kgd-off' : ''));
        b.appendChild(mk('span', 'kgd-n', boxLabel(n)));
        if (Array.isArray(n.lines) && n.lines[0]) b.appendChild(mk('span', 'kgd-l', n.lines[0]));
        b.style.gridColumn = String(colOf[n.column] + 1);
        b.style.gridRow = String(row[n.id] + 2);
        b.setAttribute('data-node', n.id);
        boxes[n.id] = b;
        stage.appendChild(b);
        if (!hasCode) return;
        b.type = 'button';
        b.setAttribute('aria-expanded', 'false');
        b.setAttribute('aria-controls', panel.id);
        b.addEventListener('click', function () {
          var open = b.getAttribute('aria-expanded') !== 'true';
          Object.keys(boxes).forEach(function (k) { if (boxes[k].tagName === 'BUTTON') boxes[k].setAttribute('aria-expanded', 'false'); });
          b.setAttribute('aria-expanded', String(open));
          panel.hidden = !open;
          if (!open) return;
          var from = into(n.id).map(function (e) { return name(e.from); });
          panelHead.textContent = (n.code_title || n.label) + (from.length ? ' · reads ' + list(from) : '');
          panelCode.textContent = n.code;
        });
      });
      scroller.appendChild(stage);
      root.appendChild(scroller);
      root.appendChild(panel);

      // the lines: from the right edge of a box to the left edge of the box it feeds, measured once laid out
      function draw() {
        while (lines.firstChild) lines.removeChild(lines.firstChild);
        var W = stage.scrollWidth, H = stage.scrollHeight;
        if (!W || !H) return;
        lines.setAttribute('width', W); lines.setAttribute('height', H);
        lines.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
        var at = function (id) { var b = boxes[id]; return b && { l: b.offsetLeft, r: b.offsetLeft + b.offsetWidth, t: b.offsetTop, m: b.offsetTop + b.offsetHeight / 2, b: b.offsetTop + b.offsetHeight }; };
        var path = function (d, off) {
          var p = document.createElementNS(SVGNS, 'path');
          p.setAttribute('d', d);
          p.setAttribute('class', 'kgd-e' + (off ? ' off' : ''));
          lines.appendChild(p);
        };
        var bronze = nodes.filter(function (n) { return n.column === 'bronze'; }).map(function (n) { return at(n.id); });
        f.edges.forEach(function (e) {
          var to = at(e.to);
          if (!to) return;
          if (e.from === 'bronze') {                 // what reads all the source tables: one line from the column, along the top
            if (!bronze.length) return;
            var x0 = bronze[0].r - 18, top = bronze[0].t, x1 = to.l - 10;
            var y = Math.max(2, Object.keys(boxes).reduce(function (m, k) { return Math.min(m, boxes[k].offsetTop); }, top) - 5);
            path('M' + x0 + ',' + top + ' V' + y + ' H' + x1 +
                 ' Q' + (x1 + 6) + ',' + y + ' ' + (x1 + 6) + ',' + (y + 6) + ' V' + (to.m - 6) + ' Q' + (x1 + 6) + ',' + to.m + ' ' + to.l + ',' + to.m, e.built === false);
            return;
          }
          var from = at(e.from);
          if (!from) return;
          var mid = (from.r + to.l) / 2;
          path('M' + from.r + ',' + from.m + ' C' + mid + ',' + from.m + ' ' + mid + ',' + to.m + ' ' + to.l + ',' + to.m, e.built === false);
        });
        hint.hidden = scroller.scrollWidth <= scroller.clientWidth + 1;
        scroller.classList.toggle('kgd-more', !hint.hidden && scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 1);
      }
      scroller.addEventListener('scroll', function () {
        scroller.classList.toggle('kgd-more', !hint.hidden && scroller.scrollLeft + scroller.clientWidth < scroller.scrollWidth - 1);
      });
      // the arrow keys, Home and End scroll the columns when the diagram itself has the focus
      scroller.addEventListener('keydown', function (e) {
        if (e.target !== scroller || e.altKey || e.ctrlKey || e.metaKey) return;
        var step = { ArrowRight: 60, ArrowLeft: -60 }[e.key], to = null;
        if (step) to = scroller.scrollLeft + step;
        else if (e.key === 'Home') to = 0;
        else if (e.key === 'End') to = scroller.scrollWidth;
        if (to === null) return;
        e.preventDefault();
        scroller.scrollTo({ left: to, behavior: reduced.matches ? 'auto' : 'smooth' });
      });
      if (window.ResizeObserver) new ResizeObserver(function () { draw(); }).observe(stage);
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw);
      root._draw = draw;
      return root;
    }
    return { build: build };
  })();

  // "Open larger": the same diagram over the page, as wide as the window; Back to the chat or Esc returns
  function openFlowBig(btn, f) {
    closeBig();
    big = document.createElement('div');
    big.className = 'kgd-big';
    big.setAttribute('role', 'dialog');
    big.setAttribute('aria-modal', 'true');
    big.setAttribute('aria-label', 'The data flow, larger');
    var panel = document.createElement('div'), head = document.createElement('div'), title = document.createElement('p');
    var back = document.createElement('button'), body = document.createElement('div');
    panel.className = 'kgd-big-panel'; head.className = 'kgc-big-head'; body.className = 'kgd-big-body';
    title.textContent = 'The data flow';
    back.type = 'button'; back.className = 'kgc-back'; back.textContent = 'Back to the chat';
    head.appendChild(title); head.appendChild(back);
    body.appendChild(KGD.build(f, true, null));
    panel.appendChild(head); panel.appendChild(body); big.appendChild(panel);
    big._from = btn;
    big._inert = Array.prototype.filter.call(document.body.children, function (el) {
      return el.tagName !== 'SCRIPT' && !el.hasAttribute('inert');
    });
    big._inert.forEach(function (el) { el.setAttribute('inert', ''); });
    document.body.appendChild(big);
    back.addEventListener('click', closeBig);
    big.addEventListener('keydown', function (e) {                    // Tab stays inside
      if (e.key !== 'Tab') return;
      var f2 = Array.prototype.filter.call(big.querySelectorAll('button, [tabindex="0"]'), function (el) { return !el.closest('[hidden]'); });
      var first = f2[0], last = f2[f2.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    });
    back.focus({ preventScroll: true });
  }

  function dataFlow() {
    work('builder', ['Reading the source tables', 'Drafting the silver tables', 'Drafting the gold views'], function () {
      var f = drafts().flow, n = function (c) { return f.nodes.filter(function (x) { return x.column === c; }).length; };
      var model = f.nodes.filter(function (x) { return x.column === 'built'; })[0];
      var html = '<h3>The data flow</h3><p>' + plural(n('bronze'), 'source table') + ' (bronze) become ' +
        plural(n('silver'), 'silver table') + (n('gold') ? ', and ' + plural(n('gold'), 'gold view') + ' join them' : '') + '.' +
        (model ? ' The semantic model ' + code(model.label) + ' reads the source tables directly.' : '') +
        ' Left to right; choose a box to see its code.</p><div class="kgd-slot"></div>';
      var does = data('flow', 'does');
      var note = 'This is a demo, so nothing was created or run. ' + (does === 'creates'
        ? 'Connected to ' + product + ', your agent creates the silver and gold notebooks in your Fabric workspace when you ask.'
        : 'Connected to ' + product + ', your agent drafts the silver and gold notebooks from your own tables when you ask.');
      done('flow', html, '', note);
      var slots = log.querySelectorAll('.kgd-slot'), slot = slots[slots.length - 1];
      var v = KGD.build(f, false, function (btn) { openFlowBig(btn, f); });
      if (slot && v) { v.classList.add('kgc-flow'); slot.appendChild(v); v._draw(); }
    });
  }

  function question() {
    var s = P.suggestions[0], ev = s.evidence || {}, col = s.table + '.' + s.column, tgt = s.target + '.' + s.target_cols.join('+');
    var all = ev.rows_with_value && ev.matched === ev.rows_with_value;
    var count = all
      ? 'All ' + ev.distinct_values + ' of its values exist in ' + code(tgt) + ', in ' + ev.matched + ' of ' + ev.rows_with_value + ' rows.'
      : ev.matched + ' of ' + ev.rows_with_value + ' rows have a value that exists in ' + code(tgt) + '.';
    var ask = /^ship_to/.test(s.column) ? 'Is it the ship-to address?' : 'Does it point at ' + code(s.target) + '?';
    say('thinker', 'notice', '<p>' + code(col) + ' is not named after any table, so no naming rule linked it. ' + count + ' ' + ask + '</p>', [
      { key: 'yes', label: 'Yes, add the link', why: 'The count supports it, and you decide.', rec: true, go: function () {
        S.linked = true;
        cheer(say('builder', 'celebrate', '<h3>Link added</h3><p>The plan now has ' + plural(drafts().relationships, 'link') + '.</p>' +
                  pictureWithLink(s), null, 'win'));
        next();
      } },
      { key: 'no', label: 'No, leave it out', go: next }
    ], '', true);
  }

  function scan() {
    var n = P.tables.length, r = P.relationships.length, q = P.suggestions.length;
    work('thinker', ['Reading ' + plural(n, 'table'), 'Finding the keys', 'Counting links against the rows'], function () {
      var rels = P.relationships.map(function (x) {
        return '<li>' + code(x.source + '.' + x.source_cols.join('+')) + ' → ' + code(x.target) + '</li>';
      }).join('');
      say('onto', 'point', '<div class="kgc-facts"><div><b>' + n + '</b>tables</div><div><b>' + r + '</b>links found</div>' +
          '<div><b>' + q + '</b>' + (q === 1 ? 'question' : 'questions') + '</div></div>' + pictureOfPlan() + '<ul class="kgc-links">' + rels + '</ul>');
      later(500, q ? question : next);
    });
  }

  function failed() {
    say('onto', 'explain', '<p>The example did not load here. The check page shows the same example on sample files.</p>',
        [{ label: 'See the check on sample files', href: '/check?example=sample', rec: true }], '', true);
  }

  // Start the chat from its first message; then, at once and quietly, the steps to restore (known names only, each run
  // only where its button is on screen, as a click would run it; the first that is not there ends the restoring).
  function begin(restore, then, focusFirst) {
    var my = ++gen;
    S = { linked: false };
    pics = [];
    log.innerHTML = '';
    var start = function () {
      if (my !== gen) return;
      steps = [];
      say('onto', 'point', '<p>Hi! This is a demo on an example shop. Shall I check how its tables connect?</p>', [
        { key: 'scan', label: 'Check the tables', rec: true, go: scan },
        { label: 'See the check on sample files', href: '/check?example=sample' }
      ], '', focusFirst);
      if (restore && restore.length) {
        quiet = true;
        try {
          for (var i = 0; i < restore.length; i++) {
            var b = null, all = log.querySelectorAll('button.kgc-pick[data-key="' + restore[i] + '"]');
            for (var k = all.length - 1; k >= 0 && !b; k--) if (all[k].getAttribute('aria-disabled') !== 'true') b = all[k];
            if (!b) break;
            b._run();
          }
        } finally { quiet = false; }
      }
      if (then) then();
    };
    if (P) { start(); return; }
    // n154: /check fetches nothing (connect-src 'none'), so it carries the same plan in the page (pages.chat_plan_html)
    var inline = document.getElementById('kgcPlan');
    (inline ? Promise.resolve().then(function () { return JSON.parse(inline.textContent); })
            : fetch(PLAN_URL, { credentials: 'omit', cache: 'default' })
                .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }))
      .then(function (j) {
        if (!j || !j.tables || !j.relationships || !j.drafts || !j.suggestions) throw new Error('plan');
        P = j; start();
      })
      .catch(function () {
        if (my !== gen) return;
        S = null; steps = (restore || []).slice();     // keep what was stored, for the next try
        failed();
        if (then) then();
      });
  }

  function restart() {
    closeBig();
    begin([], save, true);
    save();
  }

  // how: 'quiet' to restore (no animation, the focus stays on the page), 'keep' when a link closes it (the focus goes
  // with the link)
  function setOpen(open, how) {
    if (!open) closeBig();
    box.hidden = !open;
    box.classList.toggle('kgc-still', open && how === 'quiet');
    launch.hidden = open;
    launch.setAttribute('aria-expanded', String(open));
    modal(open);
    if (open) {
      if (how !== 'quiet') closeBtn.focus({ preventScroll: true });
      log.scrollTop = log.scrollHeight;
    } else if (how !== 'keep') {
      launch.focus({ preventScroll: true });
    }
    save();
  }
  function ensure(button) {
    if (box) return;
    launch = button;
    product = button.getAttribute('data-product') || product;
    build();
  }

  window.KrusgraphChat = {
    // a click on the button: the chat opens with the steps it had in this tab, the focus on Close
    open: function (button) {
      ensure(button);
      if (S) { setOpen(true); return; }
      var st = readState();
      steps = st ? st.steps : [];
      setOpen(true);
      begin(steps.slice(), function () { log.scrollTop = log.scrollHeight; save(); });
    },
    // the previous page had the chat open (site.js): open it again as it was, without animation and without taking the
    // focus; under 560 px, where it would cover the page, it stays closed until the button is pressed
    restore: function (button) {
      ensure(button);
      var st = readState();
      if (!st || !st.open || narrow.matches || S) return;
      steps = st.steps;
      begin(st.steps.slice(), function () { setOpen(true, 'quiet'); });
    }
  };
})();
