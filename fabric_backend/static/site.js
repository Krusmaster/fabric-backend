/* Krusgraph site behaviours: navigation, the graph renderer and per-page wiring. No external resources. */
(function () {
  'use strict';
  var M = window.Mascots;

  /* ------------------------------------------------------------------ nav */
  var toggle = document.querySelector('.nav-toggle'), nav = document.getElementById('site-nav');
  if (toggle && nav) {
    var setNav = function (open) { nav.classList.toggle('open', open); document.body.classList.toggle('nav-open', open); toggle.setAttribute('aria-expanded', open ? 'true' : 'false'); };
    toggle.addEventListener('click', function () { setNav(!nav.classList.contains('open')); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && nav.classList.contains('open')) { setNav(false); toggle.focus(); } });
    document.addEventListener('click', function (e) { if (nav.classList.contains('open') && !nav.contains(e.target) && !toggle.contains(e.target)) setNav(false); });
  }
  // <details data-open-wide>: open by default where there is room (the permissions table on /start)
  if (window.matchMedia('(min-width: 720px)').matches) document.querySelectorAll('details[data-open-wide]').forEach(function (d) { d.open = true; });

  /* ------------------------------------------------------------------ graph */
  /* Tables are cards (coloured table icon, key fields marked with a key icon); connections are soft bezier wires in the
     source table's colour with a dot at each end, the rule on a chip mid-curve and the cardinality as text.
     Wide: left to right along customers → orders → order_items → products → categories, with audit_log and addresses on
     a second row under customers. Narrow: one column of full-width cards in chain order; wires between cards that are not
     neighbours run in lanes beside the cards (the longest on the left, the rest nested on the right, so none cross). */
  var CHAIN = ['customers', 'orders', 'order_items', 'products', 'categories'];
  var ROW2 = [['audit_log', 0], ['addresses', 1]];
  var STACK = ['customers', 'orders', 'order_items', 'products', 'categories', 'addresses', 'audit_log'];
  var PAINT_ORDER = ['customers', 'orders', 'order_items', 'products', 'categories', 'addresses', 'audit_log'];
  var COLORS = ['coral', 'sage', 'lav', 'mustard'];
  var CW = 200, GX = 86, GY = 100, NARROW_AT = 700;
  var NS = 'http://www.w3.org/2000/svg';
  var ICON_TABLE = '<svg class="g-ico" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><rect x="1.5" y="2.5" width="13" height="11" rx="2.6" fill="currentColor" fill-opacity=".22" stroke="currentColor" stroke-width="1.5"/><path d="M1.5 6.5h13M6.2 6.5v7" stroke="currentColor" stroke-width="1.5"/></svg>';
  var ICON_KEY = '<svg class="g-key" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="5" cy="8" r="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M8 8h6.2M12.2 8v2.6M14.2 8v2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>';
  function el(tag, attrs, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function colorOf(name, i) { var k = PAINT_ORDER.indexOf(name); return COLORS[(k >= 0 ? k : i) % COLORS.length]; }
  function keyText(t) { return !t.key.length ? 'no key' : t.key.length > 1 ? 'composite key' : 'key'; }
  function keyTip(t, rules) { var code = t.key.length ? t.key_rule : 'K3'; return 'Rule ' + code + (rules && rules[code] ? ': ' + rules[code].replace(/`/g, '') : ''); }

  function Graph(container, data, opts) {
    opts = opts || {};
    var self = this;
    this.container = container; this.data = data; this.opts = opts;
    this.handlers = {}; this.selected = null; this.accepted = {}; this.zoom = null;
    container.classList.add('graph');
    container.setAttribute('role', 'group');
    container.setAttribute('aria-label', opts.label || 'Data graph: tables and the connections between them');
    var sizer = this.sizer = document.createElement('div'); sizer.className = 'g-sizer';
    var scene = this.scene = document.createElement('div'); scene.className = 'g-scene';
    var svg = this.svg = el('svg', { 'class': 'g-edges', 'aria-hidden': 'false' });
    sizer.appendChild(scene); container.appendChild(sizer);
    this.nodes = {};
    var tables = opts.tables ? data.tables.filter(function (t) { return opts.tables.indexOf(t.name) >= 0; }) : data.tables;
    var maxFields = opts.maxFields || 5;
    tables.forEach(function (t, i) {
      var color = colorOf(t.name, i);
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'g-node c-' + color + (t.key.length ? '' : ' keyless'); b.setAttribute('data-table', t.name);
      b.setAttribute('aria-label', t.name + ', ' + (t.key.length ? keyText(t) + ' ' + t.key.join(' + ') + ', rule ' + t.key_rule : 'no key, rule K3') + ', ' + t.columns.length + ' fields');
      var cols = t.columns.slice(0, maxFields);
      b.innerHTML = '<span class="g-node-head">' + ICON_TABLE + '<span class="g-node-name">' + esc(t.name) + '</span>' +
        '</span>' +
        '<span class="g-node-cols" aria-hidden="true">' + cols.map(function (c) {
          return '<span class="g-col' + (c.key ? ' key' : '') + (c.linked && !c.key ? ' linked' : '') + '">' + (c.key ? ICON_KEY : '<i class="g-pad"></i>') +
            '<span class="n">' + esc(c.name) + '</span><span class="t">' + esc(c.type) + '</span></span>';
        }).join('') + (t.columns.length > cols.length ? '<span class="g-col more">+' + (t.columns.length - cols.length) + ' more</span>' : '') + '</span>' +
        (t.key.length ? '' : '<span class="g-node-foot" title="' + esc(keyTip(t, data.rules)) + '">no key · query only</span>');
      scene.appendChild(b);
      self.nodes[t.name] = { el: b, table: t, i: i, color: color };
      b.addEventListener('mouseenter', function () { self.highlightTable(t.name); });
      b.addEventListener('mouseleave', function () { self.rehighlight(); });
      b.addEventListener('focus', function () { self.highlightTable(t.name); self.emit('focus', { type: 'table', table: t, el: b }); });
      b.addEventListener('blur', function () { self.rehighlight(); });
      b.addEventListener('click', function () { self.select({ type: 'table', table: t, el: b }); });
    });
    scene.appendChild(svg);                                   // after the cards: tables come first in tab order (z-index keeps wires under cards)
    this.edges = [];
    data.relationships.forEach(function (r) { if (self.nodes[r.source] && self.nodes[r.target]) self.edges.push({ rel: r, kind: 'rel' }); });
    (opts.suggest || []).forEach(function (s) { if (self.nodes[s.source] && self.nodes[s.target]) self.edges.push({ rel: s, kind: 'suggested' }); });
    this.edges.forEach(function (e) { self.makeEdge(e); });
    this.mascotEls = (opts.mascots || []).map(function (m) {
      var d = document.createElement('div'); d.className = 'g-mascot'; d.setAttribute('aria-hidden', 'true'); d.setAttribute('data-on', m.edge);
      if (m.near) d.setAttribute('data-near', m.near);
      if (m.near) d.style.setProperty('--gaze-x', '-1.4px');
      d.innerHTML = M.svg(m.kind, { pose: m.pose || 'rest', idle: m.idle, label: '' }); scene.appendChild(d); d.kind = m.kind; return d;
    });
    container.addEventListener('keydown', function (e) { if (e.key === 'Escape') { self.clearSelection(); } });
    this.layout();
    var lastW = container.clientWidth;
    var relayout = function () { if (container.clientWidth !== lastW) { lastW = container.clientWidth; self.layout(); } };
    if (window.ResizeObserver) new ResizeObserver(relayout).observe(container); else window.addEventListener('resize', relayout);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { self.layout(); });
  }
  Graph.prototype.on = function (ev, fn) { (this.handlers[ev] = this.handlers[ev] || []).push(fn); return this; };
  Graph.prototype.emit = function (ev, arg) { (this.handlers[ev] || []).forEach(function (f) { f(arg); }); };
  Graph.prototype.edgeId = function (r) { return r.source + '.' + r.source_cols.join('+') + '>' + r.target; };
  Graph.prototype.edgeLabel = function (e) {
    var r = e.rel, from = r.source + '.' + r.source_cols.join(', '), to = r.target + '.' + r.target_cols.join(', ');
    if (e.kind === 'suggested') return this.accepted[e.id] ? 'Accepted here, not verified: ' + from + ' to ' + to
                                                            : 'Suggested connection: ' + from + ' to ' + to + ', not linked by the engine. Review it.';
    return from + ' points at ' + to + ', rule ' + r.rule + ', many ' + r.source + ' to one ' + r.target;
  };
  Graph.prototype.makeEdge = function (e) {
    var self = this, r = e.rel, id = this.edgeId(r);
    var src = this.nodes[r.source];
    var g = el('g', { 'class': 'g-edge c-' + src.color + ' rule-' + r.rule + (e.kind === 'suggested' ? ' suggested' : ''), tabindex: '0', role: 'button', 'data-id': id });
    e.id = id; e.el = g;
    g.setAttribute('aria-label', this.edgeLabel(e));
    e.hit = el('path', { 'class': 'hit' }); e.wire = el('path', { 'class': 'wire' });
    e.dotA = el('circle', { 'class': 'dot', r: 3.6 }); e.dotB = el('circle', { 'class': 'dot', r: 3.6 });
    e.card = el('text', { 'class': 'card-n', 'text-anchor': 'middle' });
    e.tag = el('g', { 'class': 'tag' }); e.tagRect = el('rect', { height: 20, rx: 10 }); e.tagText = el('text', { 'text-anchor': 'middle' });
    e.tag.appendChild(e.tagRect); e.tag.appendChild(e.tagText);
    [e.hit, e.wire, e.dotA, e.dotB, e.card, e.tag].forEach(function (x) { g.appendChild(x); });
    this.setTag(e);
    this.svg.appendChild(g);
    g.addEventListener('mouseenter', function () { self.highlightEdge(e); });
    g.addEventListener('mouseleave', function () { self.rehighlight(); });
    g.addEventListener('focus', function () { self.highlightEdge(e); self.emit('focus', { type: 'edge', edge: e, el: g }); });
    g.addEventListener('blur', function () { self.rehighlight(); });
    g.addEventListener('click', function () { self.select({ type: 'edge', edge: e, el: g }); });
    g.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); self.select({ type: 'edge', edge: e, el: g }); } });
  };
  Graph.prototype.setTag = function (e) {
    var t = e.kind === 'suggested' ? (this.accepted[e.id] ? 'Accepted here (not verified)' : this.opts.autoLayout ? 'suggested' : 'Suggested connection') : e.rel.rule;
    e.tagText.textContent = t; e.tagW = Math.round(t.length * (e.kind === 'suggested' ? 6.6 : 7.4) + 18);
    e.tagRect.setAttribute('width', e.tagW); e.tagRect.setAttribute('x', -e.tagW / 2); e.tagRect.setAttribute('y', -10);
    e.tagText.setAttribute('y', 4);
  };
  Graph.prototype.size_ = function (name) { var n = this.nodes[name]; return { w: n.el.offsetWidth || CW, h: n.el.offsetHeight || 120 }; };
  Graph.prototype.rect = function (name) { var n = this.nodes[name]; return { x: n.x, y: n.y, w: n.w, h: n.h }; };
  /* Any schema (the local demo): rows by depth. Tables nothing points from sit on the first row, a table goes one row
     below the tables it points at, tables with no connection at all go last; within a row, by the average position of
     the neighbours above (fewer crossings); rows wider than the view wrap. */
  Graph.prototype.autoRows = function (perRow) {
    var self = this, names = Object.keys(this.nodes), outs = {}, level = {}, deg = {};
    names.forEach(function (n) { outs[n] = []; deg[n] = 0; });
    this.edges.forEach(function (e) { if (e.kind === 'rel') { outs[e.rel.source].push(e.rel.target); deg[e.rel.source]++; deg[e.rel.target]++; } });
    function lv(n, seen) {
      if (level[n] !== undefined) return level[n];
      if (seen[n]) return 0;
      seen[n] = true; var m = 0;
      outs[n].forEach(function (t) { if (t !== n) m = Math.max(m, lv(t, seen) + 1); });
      level[n] = m; return m;
    }
    names.forEach(function (n) { lv(n, {}); });
    var maxL = 0; names.forEach(function (n) { maxL = Math.max(maxL, level[n]); });
    names.forEach(function (n) { if (!deg[n]) level[n] = maxL + 1; });
    var rows = []; names.forEach(function (n) { (rows[level[n]] = rows[level[n]] || []).push(n); });
    rows = rows.filter(Boolean);
    var pos = {};
    rows.forEach(function (row, i) {
      if (i === 0) row.sort(function (a, b) { return deg[b] - deg[a] || a.localeCompare(b); });
      else {
        var bary = function (n) { var ps = outs[n].filter(function (t) { return pos[t] !== undefined; }).map(function (t) { return pos[t]; }); return ps.length ? ps.reduce(function (x, y) { return x + y; }, 0) / ps.length : 1e6; };
        row.sort(function (a, b) { return bary(a) - bary(b) || deg[b] - deg[a] || a.localeCompare(b); });
      }
      row.forEach(function (n, j) { pos[n] = j; });
    });
    if (!perRow) return rows;
    var wrapped = []; rows.forEach(function (r) { for (var k = 0; k < r.length; k += perRow) wrapped.push(r.slice(k, k + perRow)); });
    return wrapped;
  };
  Graph.prototype.layout = function () {
    var self = this, cw = this.container.clientWidth || 800, names = Object.keys(this.nodes);
    var narrow = this.narrow = cw < NARROW_AT;
    this.container.classList.toggle('narrow', narrow);
    var top = this.mascotEls.length ? (narrow ? 76 : 64) : 22, maxX = 0, maxY = 0;
    var auto = this.opts.autoLayout;
    if (narrow) {
      var order = auto ? [].concat.apply([], this.autoRows()) : STACK.filter(function (n) { return self.nodes[n]; }).concat(names.filter(function (n) { return STACK.indexOf(n) < 0; }));
      var span = function (e) { return Math.abs(order.indexOf(e.rel.source) - order.indexOf(e.rel.target)); };
      var lanes = this.edges.filter(function (e) { return span(e) > 1; }).sort(function (a, b) { return span(b) - span(a); });
      var right = lanes.length > 1 ? lanes.slice(1) : lanes, left = lanes.length > 1 ? [lanes[0]] : [];
      this.edges.forEach(function (e) { e.laneSide = null; });
      left.forEach(function (e) { e.laneSide = 'l'; e.depth = 0; });
      right.forEach(function (e, i) { e.laneSide = 'r'; e.depth = right.length - 1 - i; });   // longest = outermost
      var LW = 26, leftW = left.length ? 30 : 0, rightW = right.length ? 8 + LW * right.length : 0;
      this.lane = { l: leftW, r: rightW };
      var w = Math.min(cw - 24 - leftW - rightW, 420), y = top;
      order.forEach(function (n, i) {
        var node = self.nodes[n]; node.el.style.width = w + 'px'; node.el.style.minHeight = '';
        var s = self.size_(n); node.x = 12 + leftW; node.y = y; node.w = w; node.h = s.h; node.slot = i;
        y += s.h + 68;
      });
    } else if (auto) {
      var y0 = top, perRow = Math.max(2, Math.floor((cw - 32 + GX) / (CW + GX)));
      this.autoRows(perRow).forEach(function (row, ri) {
        var rh = 0;
        row.forEach(function (n, j) {
          var node = self.nodes[n]; node.el.style.width = CW + 'px'; node.el.style.minHeight = ''; var s = self.size_(n);
          node.x = 16 + j * (CW + GX); node.y = y0; node.w = CW; node.h = s.h; node.row = ri + 1; node.slot = j; rh = Math.max(rh, s.h);
        });
        row.forEach(function (n) { self.nodes[n].el.style.minHeight = rh + 'px'; self.nodes[n].h = rh; });
        y0 += rh + GY;
      });
    } else {
      var col = 0, rowH = 0;
      var row1 = CHAIN.filter(function (n) { return self.nodes[n]; }).concat(names.filter(function (n) { return CHAIN.indexOf(n) < 0 && !ROW2.some(function (r) { return r[0] === n; }); }));
      row1.forEach(function (n) {
        var node = self.nodes[n]; node.el.style.width = CW + 'px'; node.el.style.minHeight = ''; var s = self.size_(n);
        node.x = 16 + col * (CW + GX); node.y = top; node.w = CW; node.h = s.h; node.row = 1; node.slot = col++; rowH = Math.max(rowH, s.h);
      });
      row1.forEach(function (n) { self.nodes[n].el.style.minHeight = rowH + 'px'; self.nodes[n].h = rowH; });
      ROW2.forEach(function (p) {
        var node = self.nodes[p[0]]; if (!node) return;
        node.el.style.width = CW + 'px'; var s = self.size_(p[0]);
        node.x = 16 + p[1] * (CW + GX); node.y = top + rowH + GY; node.w = CW; node.h = s.h; node.row = 2;
      });
    }
    names.forEach(function (n) {
      var node = self.nodes[n]; node.el.style.left = node.x + 'px'; node.el.style.top = node.y + 'px';
      maxX = Math.max(maxX, node.x + node.w); maxY = Math.max(maxY, node.y + node.h);
    });
    this.size = { w: maxX + (narrow ? 12 + this.lane.r : 16), h: maxY + 18 + (narrow ? (this.opts.padBottom || 0) : 0) };
    this.scene.style.width = this.size.w + 'px'; this.scene.style.height = this.size.h + 'px';
    this.svg.setAttribute('width', this.size.w); this.svg.setAttribute('height', this.size.h);
    this.ports();
    this.edges.forEach(function (e) { self.route(e); });
    var floor = 0; names.forEach(function (n) { if (self.nodes[n].row === 2) floor = Math.max(floor, self.nodes[n].y + self.nodes[n].h); });
    this.mascotEls.forEach(function (d, i) {
      var e = self.edges.filter(function (x) { return x.id === d.getAttribute('data-on'); })[0], near = self.nodes[d.getAttribute('data-near')];
      if (!e && !near) { d.style.display = 'none'; return; }
      d.style.display = '';
      if (!narrow && near && floor) { // stands on the floor of the empty corner, under its table
        var sf = 104; d.style.width = d.style.height = sf + 'px';
        d.style.left = (near.x + near.w / 2 - sf / 2) + 'px'; d.style.top = (floor - sf * 0.93) + 'px';
      } else if (!narrow && e && e.horizontal) { // sits on the rule chip of a top-row wire
        var sz = d.kind === 'thinker' ? 104 : 100; d.style.width = d.style.height = sz + 'px';
        d.style.left = (e.mid.x - sz / 2) + 'px'; d.style.top = (e.mid.y - 9 - sz * 0.9 + 1) + 'px';
      } else { // narrow: a small row above the first card, clear of its border
        var first = self.nodes[(auto ? [] : STACK).filter(function (n) { return self.nodes[n]; })[0]] || self.nodes[Object.keys(self.nodes)[0]];
        var s2 = 60; d.style.width = d.style.height = s2 + 'px';
        d.style.left = (first.x + first.w * (0.2 + 0.3 * i) - s2 / 2) + 'px'; d.style.top = (first.y - 7 - s2 * 0.95) + 'px';
      }
    });
    this.fit();
  };
  // Spread the wires that leave the same side of a card, ordered by where their other end is, so they never cross.
  Graph.prototype.ports = function () {
    var self = this, sides = {};
    this.edges.forEach(function (e) {
      var S = self.nodes[e.rel.source], T = self.nodes[e.rel.target];
      e.horizontal = !self.narrow && S.row === T.row && (S.row === 1 || self.opts.autoLayout);
      e.lane = !!(self.narrow && e.laneSide);
      if (e.lane) {
        var U = S.y < T.y ? S : T, D = S.y < T.y ? T : S;
        e.up = U; e.down = D;
        [[U, 'u'], [D, 'd']].forEach(function (p) { var k = p[0].table.name + ':' + e.laneSide; (sides[k] = sides[k] || []).push({ e: e, end: p[1], lane: true }); });
        return;
      }
      if (e.horizontal) return;
      var up = S.y < T.y ? S : T, down = S.y < T.y ? T : S;
      e.up = up; e.down = down;
      [[up, 'b', down], [down, 't', up]].forEach(function (p) {
        var k = p[0].table.name + ':' + p[1]; (sides[k] = sides[k] || []).push({ e: e, other: p[2], end: p[1] });
      });
    });
    Object.keys(sides).forEach(function (k) {
      if (sides[k][0].lane) { // lane ends: at the upper card the outer wire leaves highest, at the lower card it arrives lowest
        var ls = sides[k].sort(function (a, b) { return (a.end === 'u' ? b.e.depth - a.e.depth : a.e.depth - b.e.depth); });
        ls.forEach(function (it, i) { it.e['y' + it.end] = 19 + 15 * i; });
        return;
      }
      var list = sides[k].sort(function (a, b) { return (a.other.x + a.other.w / 2) - (b.other.x + b.other.w / 2); });
      list.forEach(function (it, i) { it.e['f' + it.end] = (i + 1) / (list.length + 1); });
    });
  };
  Graph.prototype.route = function (e) {
    var r = e.rel, S = this.nodes[r.source], T = this.nodes[r.target], a, b, c1, c2, many, one;
    var headY = function (n) { return n.y + 21; };
    if (e.horizontal) {
      var L = S.x < T.x ? S : T, R = S.x < T.x ? T : S;
      a = { x: L.x + L.w, y: headY(L) }; b = { x: R.x, y: headY(R) };
      var k = (b.x - a.x) * 0.42;
      c1 = { x: a.x + k, y: a.y + 12 }; c2 = { x: b.x - k, y: b.y + 12 };
      e.card.textContent = (L === T ? '1' : 'many') + ' — ' + (R === T ? '1' : 'many');
    } else if (e.lane) {
      var U = e.up, D = e.down, rs = e.laneSide === 'r';
      var sx = rs ? U.x + U.w : U.x, lx = rs ? sx + 18 + 26 * e.depth : sx - 18;
      a = { x: sx, y: U.y + e.yu }; b = { x: sx, y: D.y + e.yd };
      var dl = 'M' + a.x + ' ' + a.y + ' Q' + lx + ' ' + a.y + ' ' + lx + ' ' + (a.y + 16) + ' L' + lx + ' ' + (b.y - 16) + ' Q' + lx + ' ' + b.y + ' ' + b.x + ' ' + b.y;
      e.wire.setAttribute('d', dl); e.hit.setAttribute('d', dl);
      e.dotA.setAttribute('cx', a.x); e.dotA.setAttribute('cy', a.y); e.dotB.setAttribute('cx', b.x); e.dotB.setAttribute('cy', b.y);
      var my = a.y + (b.y - a.y) * (e.depth ? 0.38 : 0.6);
      e.mid = { x: lx, y: my };
      e.card.textContent = ''; e.card.removeAttribute('transform');
      if (e.kind === 'suggested') { // the wide label sits in the gap just above the lower card, ending at its lane
        var gy = D.y - 34;
        e.tag.setAttribute('transform', 'translate(' + (rs ? lx + 10 - e.tagW / 2 : lx - 10 + e.tagW / 2) + ',' + gy + ')');
      } else {
        e.tag.setAttribute('transform', 'translate(' + lx + ',' + my.toFixed(1) + ')');
        var cx = lx + (rs ? 11 : -11), cy = my + 52;
        e.card.textContent = (U === T ? '1' : 'many') + ' — ' + (D === T ? '1' : 'many');
        e.card.setAttribute('x', cx); e.card.setAttribute('y', cy); e.card.setAttribute('text-anchor', 'middle');
        e.card.setAttribute('transform', 'rotate(90 ' + cx + ' ' + cy + ')');
      }
      return;
    } else {
      a = { x: e.up.x + e.up.w * e.fb, y: e.up.y + e.up.h }; b = { x: e.down.x + e.down.w * e.ft, y: e.down.y };
      var kk = (b.y - a.y) * 0.5;
      c1 = { x: a.x, y: a.y + kk }; c2 = { x: b.x, y: b.y - kk };
      e.card.textContent = (e.up === T ? '1' : 'many') + ' — ' + (e.down === T ? '1' : 'many');
    }
    e.card.removeAttribute('transform');
    if (e.kind === 'suggested') e.card.textContent = '';
    var d = 'M' + a.x + ' ' + a.y + ' C' + c1.x + ' ' + c1.y + ' ' + c2.x + ' ' + c2.y + ' ' + b.x + ' ' + b.y;
    e.wire.setAttribute('d', d); e.hit.setAttribute('d', d);
    e.dotA.setAttribute('cx', a.x); e.dotA.setAttribute('cy', a.y); e.dotB.setAttribute('cx', b.x); e.dotB.setAttribute('cy', b.y);
    var m = bez(a, c1, c2, b, 0.5); e.mid = m;
    var shift = (e.kind === 'suggested' && !e.horizontal && !this.narrow) ? e.tagW / 2 - 14 : 0; // wide label hangs to the right of its wire
    e.tag.setAttribute('transform', 'translate(' + (m.x + shift).toFixed(1) + ',' + m.y.toFixed(1) + ')');
    if (e.horizontal) { e.card.setAttribute('x', m.x); e.card.setAttribute('y', m.y + 26); e.card.setAttribute('text-anchor', 'middle'); }
    else if (this.narrow) { e.card.setAttribute('x', m.x + e.tagW / 2 + 8); e.card.setAttribute('y', m.y + 4); e.card.setAttribute('text-anchor', 'start'); }
    else { e.card.setAttribute('x', m.x); e.card.setAttribute('y', m.y + 26); e.card.setAttribute('text-anchor', 'middle'); }
  };
  function bez(p0, p1, p2, p3, t) { var u = 1 - t; return { x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x, y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y }; }
  // Fit: the whole graph at the container's width (never above 1:1). Zoom: a larger scale, the panel then scrolls.
  Graph.prototype.fit = function () { this.zoom = null; this.applyScale(); };
  Graph.prototype.zoomBy = function (f) { this.zoom = Math.max(0.4, Math.min(1.6, (this.zoom || this.fitScale || 1) * f)); this.applyScale(); };
  Graph.prototype.applyScale = function () {
    var cw = this.container.clientWidth; if (!cw) return;
    var fs = this.fitScale = Math.min(1, (cw - 4) / this.size.w), s = this.zoom || fs;
    this.scale = s;
    this.sizer.style.width = Math.ceil(this.size.w * s) + 'px'; this.sizer.style.height = Math.ceil(this.size.h * s) + 'px';
    this.container.style.height = Math.ceil(this.size.h * fs) + 2 + 'px';
    this.container.classList.toggle('zoomed', s > fs + 0.001);
    this.scene.style.transform = 'scale(' + s.toFixed(3) + ')';
  };
  Graph.prototype.setFields = function () { this.layout(); };
  Graph.prototype.clearHighlight = function () {
    this.container.classList.remove('has-focus');
    this.container.querySelectorAll('.on').forEach(function (x) { x.classList.remove('on'); });
  };
  Graph.prototype.highlightTable = function (name) {
    var self = this; this.clearHighlight(); this.container.classList.add('has-focus');
    this.nodes[name].el.classList.add('on');
    this.edges.forEach(function (e) { if (e.rel.source === name || e.rel.target === name) { e.el.classList.add('on'); self.nodes[e.rel.source].el.classList.add('on'); self.nodes[e.rel.target].el.classList.add('on'); } });
  };
  Graph.prototype.highlightEdge = function (e) {
    this.clearHighlight(); this.container.classList.add('has-focus');
    e.el.classList.add('on'); this.nodes[e.rel.source].el.classList.add('on'); this.nodes[e.rel.target].el.classList.add('on');
  };
  Graph.prototype.rehighlight = function () {
    if (!this.selected) return this.clearHighlight();
    if (this.selected.type === 'table') this.highlightTable(this.selected.table.name); else this.highlightEdge(this.selected.edge);
  };
  Graph.prototype.select = function (sel) {
    this.container.querySelectorAll('.selected').forEach(function (x) { x.classList.remove('selected'); });
    this.selected = sel; sel.el.classList.add('selected'); this.rehighlight(); this.emit('select', sel);
  };
  Graph.prototype.selectTable = function (name) { var n = this.nodes[name]; if (n) this.select({ type: 'table', table: n.table, el: n.el }); };
  Graph.prototype.clearSelection = function () {
    this.container.querySelectorAll('.selected').forEach(function (x) { x.classList.remove('selected'); });
    this.selected = null; this.clearHighlight(); this.emit('select', null);
  };
  Graph.prototype.setAccepted = function (e, on) {
    this.accepted[e.id] = !!on; e.el.classList.toggle('accepted', !!on);
    this.setTag(e); e.el.setAttribute('aria-label', this.edgeLabel(e)); this.route(e);
  };
  Graph.prototype.reset = function () { var self = this; this.clearSelection(); this.edges.forEach(function (e) { if (e.kind === 'suggested') self.setAccepted(e, false); }); this.fit(); };

  function loadPlan(cb) {
    fetch('/demo/plan.json', { credentials: 'omit' }).then(function (r) { return r.json(); }).then(cb).catch(function (err) {
      document.querySelectorAll('[data-plan-error]').forEach(function (x) { x.hidden = false; }); console.error(err);
    });
  }
  function suggestions(data) {
    // Dashed wires: the demo hints that plan.json carries for columns the engine left unlinked. They are labelled as
    // hints, not inference; accepting one is the page-local equivalent of passing confirmed=[...] to the tools.
    return (data.suggestions || []).map(function (s) {
      var u = (data.unlinked || []).filter(function (x) { return x.table === s.table && x.column === s.column; })[0];
      return { source: s.table, source_cols: [s.column], target: s.target, target_cols: s.target_cols, rule: 'suggested', note: u ? u.note : '', why: s.why, origin: s.source };
    });
  }


  function singular(n) { return /ies$/.test(n) ? n.slice(0, -3) + 'y' : /sses$/.test(n) ? n.slice(0, -2) : /s$/.test(n) ? n.slice(0, -1) : n; }
  function article(w) { return /^[aeiou]/.test(w) ? 'an' : 'a'; }
  function colOf(data, table, name) {
    var t = data.tables.filter(function (x) { return x.name === table; })[0];
    return t ? t.columns.filter(function (c) { return c.name === name; })[0] : null;
  }
  // A plain-language reason for a connection the engine made, from its rule. The wording follows infer.RULES.
  function reason(r) {
    var s = singular(r.source), t = singular(r.target), col = r.source_cols.join(' + '), key = r.target_cols.join(' + ');
    var lead = 'Each ' + s.replace(/_/g, ' ') + ' belongs to one ' + t.replace(/_/g, ' ') + '. ';
    if (r.rule === 'R1') return lead + 'The column ' + col + ' is named after the ' + r.target + ' table, and ' + r.target + ' has a single key, ' + key + '.';
    if (r.rule === 'R2') return lead + 'The column ' + col + ' has exactly the same name as the key of ' + r.target + '.';
    if (r.rule === 'R3') return lead + 'All of the composite key columns of ' + r.target + ' appear in ' + r.source + '.';
    if (r.rule === 'R0') return lead + 'The source declares this foreign key.';
    return lead;
  }
  function tableIcon(name, i) { return '<span class="t-ico c-' + colorOf(name, i) + '">' + ICON_TABLE + '</span>'; }

  /* ------------------------------------------------------------------ home */
  var home = document.querySelector('[data-page=home]');
  if (home) loadPlan(function (data) {
    var g = new Graph(document.getElementById('home-graph'), data, {
      label: 'Data graph of the demo shop schema', suggest: suggestions(data),
      mascots: [{ kind: 'onto', edge: 'orders.customer_id>customers', pose: 'look', idle: 'breathe' },
                { kind: 'thinker', edge: 'order_items.product_id>products', pose: 'rest', idle: 'nod' },
                { kind: 'builder', edge: 'products.category_id>categories', near: 'categories', pose: 'look', idle: 'bounce' }]
    });
    var out = document.getElementById('home-why');
    var dflt = out.innerHTML;
    function describe(sel) {
      if (!sel) { out.innerHTML = dflt; return; }
      if (sel.type === 'table') {
        var t = sel.table;
        out.innerHTML = '<strong>' + esc(t.name) + '</strong> · ' + (t.key.length ? esc(keyText(t)) + ' <code>' + esc(t.key.join(' + ')) + '</code>, rule <code>' + t.key_rule + '</code>: ' + esc(data.rules[t.key_rule].replace(/`/g, '')) : 'no key, rule <code>K3</code>: ' + esc(data.rules.K3)) + '.';
      } else if (sel.edge.kind === 'suggested') {
        var q = sel.edge.rel;
        out.innerHTML = '<code>' + esc(q.source + '.' + q.source_cols.join('+')) + '</code> was not linked by the engine (' + esc(q.note) + '). <a href="/explore">Review it in the explorer</a>.';
      } else {
        var r = sel.edge.rel;
        out.innerHTML = '<span class="why-rule">' + r.rule + '</span> <code>' + esc(r.source + '.' + r.source_cols.join('+')) + '</code> → <code>' + esc(r.target + '.' + r.target_cols.join('+')) + '</code>. ' + esc(reason(r));
      }
    }
    g.on('select', describe); g.on('focus', describe);
  });

  /* ------------------------------------------------------------------ start: one step at a time (all three without JS) */
  var startPage = document.querySelector('[data-page=start]');
  if (startPage) {
    document.documentElement.classList.add('js');
    var stepBtns = startPage.querySelectorAll('.start-step'), panes = startPage.querySelectorAll('.start-pane');
    var showStep = function (n) {
      stepBtns.forEach(function (b) { b.setAttribute('aria-pressed', b.getAttribute('data-step') === n ? 'true' : 'false'); });
      panes.forEach(function (p) { p.hidden = p.getAttribute('data-pane') !== n; });
    };
    stepBtns.forEach(function (b) { b.addEventListener('click', function () { showStep(b.getAttribute('data-step')); if (window.location.hash !== '#step-' + b.getAttribute('data-step')) history.replaceState(null, '', '#step-' + b.getAttribute('data-step')); }); });
    var m = /^#step-([123])$/.exec(window.location.hash);
    showStep(m ? m[1] : '1');
  }

  /* ------------------------------------------------------------------ explore */
  var explore = document.querySelector('[data-page=explore]');
  if (explore) loadPlan(function (data) {
    var area = document.getElementById('explore-graph'), panel = document.getElementById('why'), list = document.getElementById('table-list');
    var sug = suggestions(data);
    var g = new Graph(area, data, { label: 'Explorable data graph of the demo shop schema', suggest: sug, padBottom: 52 });   // room for the still helper on touch
    document.getElementById('plan-summary').textContent = data.summary.split('\n')[0] + (sug.length ? ' · ' + sug.length + ' column to review' : '');
    list.innerHTML = data.tables.map(function (t, i) {
      return '<li><button type="button" data-table="' + esc(t.name) + '">' + tableIcon(t.name, i) + '<span class="nm">' + esc(t.name) + '</span><span class="rule" title="' + esc(keyTip(t, data.rules)) + '">' + keyText(t) + '</span></button></li>';
    }).join('');
    list.addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) { g.selectTable(b.getAttribute('data-table')); } });
    document.getElementById('btn-fit').addEventListener('click', function () { g.fit(); });
    document.getElementById('btn-zoom-in').addEventListener('click', function () { g.zoomBy(1.25); });
    document.getElementById('btn-zoom-out').addEventListener('click', function () { g.zoomBy(0.8); });
    document.getElementById('btn-reset').addEventListener('click', function () { g.reset(); render(null); });
    var dflt = panel.innerHTML, line = document.getElementById('explore-line'), lineDflt = line.innerHTML;
    function field(table, name) {
      var c = colOf(data, table, name);
      return '<li><code>' + esc(table + '.' + name) + '</code> <span class="type">' + esc(c ? c.type : '?') + '</span>' + (c && c.key ? ' <span class="muted">key</span>' : '') + '</li>';
    }
    function fields(r) {
      return '<h3>Fields</h3><ul class="fields">' + r.source_cols.map(function (c) { return field(r.source, c); }).join('') +
        r.target_cols.map(function (c) { return field(r.target, c); }).join('') + '</ul>';
    }
    var bm = document.getElementById('btn-mermaid');
    bm.addEventListener('click', function () { // the engine's own erDiagram, from plan.json
      var done = function (ok) { bm.textContent = ok ? 'Copied' : 'Copy failed'; setTimeout(function () { bm.textContent = 'Copy Mermaid'; }, 1600); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(data.mermaid).then(function () { done(true); }, function () { done(false); });
      else { window.prompt('Mermaid ER diagram (select and copy):', data.mermaid); done(true); }
    });
    function rule(code) { return esc(data.rules[code] || '').replace(/`([^`]+)`/g, '<code>$1</code>'); }
    function render(sel) {
      list.querySelectorAll('button').forEach(function (b) { b.classList.toggle('selected', !!(sel && sel.type === 'table' && b.getAttribute('data-table') === sel.table.name)); });
      if (!sel) { panel.innerHTML = dflt; line.innerHTML = lineDflt; M.mount(panel); return; }
      if (sel.type === 'table') {
        var t = sel.table, code = t.key.length ? t.key_rule : 'K3';
        panel.innerHTML = '<h2>' + tableIcon(t.name, data.tables.indexOf(t)) + ' ' + esc(t.name) + '</h2><div class="why-cols"><div>' +
          '<p class="why-head"><span class="why-rule key">' + code + '</span> <strong>' + keyText(t) + '</strong>' + (t.key.length ? ' <code>' + esc(t.key.join(' + ')) + '</code>' : '') + '</p>' +
          '<p>' + esc(data.rules[code].replace(/`/g, '')) + '.</p>' +
          (t.key_rule === 'K1' ? '<p class="status">Composite keys cannot be guessed from names; this one was given as <code>keys={"order_items": ["order_id", "line_no"]}</code>.</p>' : '') +
          (t.key.length ? '' : '<p class="status">Query only: it can reference other tables, but nothing can reference it.</p>') +
          '</div><div><h3>Fields</h3><ul class="fields">' + t.columns.map(function (c) { return '<li><code>' + esc(c.name) + '</code> <span class="type">' + esc(c.type) + '</span>' + (c.key ? ' <span class="muted">key</span>' : c.linked ? ' <span class="muted">linked</span>' : '') + '</li>'; }).join('') + '</ul>' +
          '<p class="status">' + t.rows + ' rows (synthetic).</p></div></div>';
        line.innerHTML = '<strong>' + esc(t.name) + '</strong> · ' + keyText(t) + (t.key.length ? ' <code>' + esc(t.key.join(' + ')) + '</code>' : '') + ' · <a href="#why">details below</a>';
      } else if (sel.edge.kind === 'suggested') {
        var r = sel.edge.rel, acc = g.accepted[sel.edge.id];
        panel.innerHTML = '<h2>Why this connection?</h2><div class="why-cols"><div>' +
          '<p class="why-head"><span class="why-rule ' + (acc ? 'acc' : 'sug') + '">' + (acc ? 'Accepted here (not verified)' : 'Suggested connection') + '</span></p>' +
          '<p class="why-path"><code>' + esc(r.source + '.' + r.source_cols[0]) + ' → ' + esc(r.target + '.' + r.target_cols[0]) + '</code></p>' +
          '<p>The engine left <code>' + esc(r.source + '.' + r.source_cols[0]) + '</code> unlinked: ' + esc(r.note) + '. This dashed wire is a <strong>' + esc(r.origin || 'demo hint') + '</strong>: ' + esc(r.why || '') + '.</p>' +
          fields(r) + '</div><div>' +
          '<div class="note sage"><span data-mascot="thinker" data-pose="' + (acc ? 'rest' : 'think') + '" data-label="The thinker"></span><div><strong>Review this connection.</strong><br>Your choice. Both are valid.' +
          '<div class="choice"><button type="button" class="btn sage small" id="acc" aria-pressed="' + (acc ? 'true' : 'false') + '">Accept</button><button type="button" class="btn ghost small" id="skip">Skip</button></div></div></div>' +
          '<p class="status">' + (acc ? 'Accepted here: drawn as a solid sage line. Accepted is not verified; nothing has checked the data. In the real tools this is <code>confirmed=[…]</code>.' : 'Skip leaves it dashed. The choice lives only in this page.') + '</p></div></div>';
        line.innerHTML = (acc ? 'Accepted here (not verified)' : 'Suggested connection') + ': <code>' + esc(r.source + '.' + r.source_cols[0] + ' → ' + r.target + '.' + r.target_cols[0]) + '</code> · <a href="#why">review it below</a>';
        M.mount(panel);
        panel.querySelector('#acc').addEventListener('click', function () { g.setAccepted(sel.edge, true); render(sel); panel.querySelector('#acc').focus(); });
        panel.querySelector('#skip').addEventListener('click', function () { g.setAccepted(sel.edge, false); render(sel); panel.querySelector('#skip').focus(); });
      } else {
        var rr = sel.edge.rel;
        panel.innerHTML = '<h2>Why this connection?</h2><div class="why-cols"><div>' +
          '<p class="why-head"><span class="why-rule" title="' + esc('Rule ' + rr.rule + ': ' + data.rules[rr.rule].replace(/`/g, '')) + '">' + rr.rule + '</span> <span class="muted">many ' + esc(rr.source) + ' → one ' + esc(singular(rr.target)) + '</span></p>' +
          '<p class="why-path"><code>' + esc(rr.source + '.' + rr.source_cols.join(' + ')) + ' → ' + esc(rr.target + '.' + rr.target_cols.join(' + ')) + '</code></p>' +
          '<p>' + esc(reason(rr)) + '</p><p class="status">Rule ' + rr.rule + ', in the engine’s words: ' + rule(rr.rule) + '.</p>' + '<div class="note coral"><span data-mascot="onto" data-pose="explain" data-label="Onto"></span><div><strong>Onto’s note:</strong> a suggestion, not a guarantee. Names made this link; you can overrule it.</div></div></div><div>' + fields(rr) +
          '<h3>In GraphQL</h3><ul class="fields"><li><code>' + esc(rr.source + '.' + rr.field) + '</code> <span class="type">one</span></li><li><code>' + esc(rr.target + '.' + rr.reverse) + '</code> <span class="type">many</span></li></ul></div></div>';
        line.innerHTML = '<span class="why-rule">' + rr.rule + '</span> <code>' + esc(rr.source + '.' + rr.source_cols.join(' + ') + ' → ' + rr.target + '.' + rr.target_cols.join(' + ')) + '</code> · <a href="#why">why, below</a>';
        M.mount(panel);
      }
    }
    g.on('select', function (sel) {
      render(sel);
      if (sel && window.matchMedia('(max-width: 860px)').matches && panel.scrollIntoView) panel.scrollIntoView({ block: 'nearest', behavior: M.motionOK() ? 'smooth' : 'auto' });
      var h = !sel ? '' : sel.type === 'table' ? '#table=' + encodeURIComponent(sel.table.name) : '#edge=' + encodeURIComponent(sel.edge.id);
      if (history.replaceState) history.replaceState(null, '', location.pathname + location.search + h);
    });
    function fromHash() { // deep links: /explore#table=orders, /explore#edge=orders.customer_id>customers
      var m = /^#(table|edge)=(.+)$/.exec(location.hash || '');
      if (!m) return;
      var v; try { v = decodeURIComponent(m[2]); } catch (err) { return; }     // a mangled link is not an error
      if (m[1] === 'table') g.selectTable(v);
      else { var e = g.edges.filter(function (x) { return x.id === v; })[0]; if (e) g.select({ type: 'edge', edge: e, el: e.el }); }
    }
    fromHash(); window.addEventListener('hashchange', fromHash);
    // Onto: follows the pointer on hover devices; a still helper on touch and for keyboard users.
    var helper = M.follower(area, { text: 'Explore this table.' });
    if (!helper) {
      var still = document.createElement('div'); still.className = 'g-follower visible still'; still.style.left = 'auto'; still.style.right = '4px'; still.style.top = 'auto'; still.style.bottom = '4px';
      still.setAttribute('aria-hidden', 'true'); still.innerHTML = M.svg('onto', { pose: 'rest', label: '' }); area.appendChild(still);
      g.on('select', function (sel) { if (sel && sel.type === 'table' && M.enabled()) { M.setPose(still, 'explain'); M.say(area, sel.el, 'Key and rule below.', { dx: 8, dy: 0 }); setTimeout(function () { M.say(area, sel.el, ''); M.setPose(still, 'rest'); }, 2200); } });
    }
    g.on('focus', function (sel) { // keyboard users get the same help, without a pointer
      if (sel.type === 'table' && M.enabled() && !(area.matches(':hover'))) { M.say(area, sel.el, 'Explore this table.', { dx: 8, dy: 0 }); setTimeout(function () { M.say(area, sel.el, ''); }, 1800); }
    });
  });

  /* ------------------------------------------------------------------ partner workspace */
  var ws = document.querySelector('[data-page=workspace]');
  if (ws) loadPlan(function (data) {
    var g = new Graph(document.getElementById('ws-graph'), data, { label: 'Example graph for the illustrative workspace', tables: ['customers', 'orders', 'order_items', 'products', 'categories'] });
    var out = document.getElementById('ws-why'), dflt = out.textContent;
    g.on('select', function (sel) {
      if (!sel) { out.textContent = dflt; return; }
      if (sel.type === 'table') out.textContent = sel.table.name + ': ' + (sel.table.key.length ? 'key ' + sel.table.key.join(' + ') + ' (' + sel.table.key_rule + ')' : 'no key (K3)');
      else out.textContent = sel.edge.rel.source + '.' + sel.edge.rel.source_cols.join('+') + ' → ' + sel.edge.rel.target + ' (' + sel.edge.rel.rule + ': ' + data.rules[sel.edge.rel.rule] + ')';
    });
  });

  /* ------------------------------------------------------------------ mascot review page */
  var mp = document.querySelector('[data-page=mascots]');
  if (mp) {
    var poses = ['rest', 'look', 'listen', 'point', 'celebrate', 'heart', 'notice', 'think', 'explain', 'aside', 'working', 'failure', 'calm'];
    ['onto', 'thinker', 'builder'].forEach(function (k) {
      var grid = document.getElementById('grid-' + k);
      grid.innerHTML = poses.map(function (p) { return '<div class="m-cell">' + M.svg(k, { pose: p, label: k + ', ' + p }) + '<span class="lbl">' + p + '</span></div>'; }).join('');
    });
    loadPlan(function (data) {
      var area = document.getElementById('m-follow');
      var g = new Graph(area, data, { tables: ['customers', 'orders', 'order_items'], label: 'Small graph for the follower demo' });
      var st = document.getElementById('m-follow-state');
      var f = M.follower(area, { text: 'Explore this table.', onState: function (s) { st.textContent = 'state: ' + s; } });
      if (!f) st.textContent = 'state: still (touch or no hover: Onto helps on tap instead)';
      g.on('select', function (sel) { if (sel && !f) M.say(area, sel.el, 'Explore this table.', { dx: 8 }); });
    });
    // Thinker: notice → consider → explain → your choice
    var tk = document.getElementById('m-think'), tkState = document.getElementById('m-think-state'), wire = document.getElementById('m-wire');
    var seq = [['notice', 'notice'], ['think', 'consider'], ['explain', 'explain: "Review this connection."']], i = 0;
    function stepThinker() { if (i < seq.length) { M.setPose(tk, seq[i][0]); tkState.textContent = 'state: ' + seq[i][1]; i++; setTimeout(stepThinker, M.motionOK() ? 900 : 0); } else { tkState.textContent = 'state: your choice'; document.getElementById('m-choice').hidden = false; } }
    document.getElementById('m-think-start').addEventListener('click', function () { i = 0; document.getElementById('m-choice').hidden = true; wire.setAttribute('class', 'wire-demo'); stepThinker(); });
    document.getElementById('m-accept').addEventListener('click', function () { wire.setAttribute('class', 'wire-demo accepted'); tkState.textContent = 'accepted (thin sage line). Accepted is not verified.'; M.setPose(tk, 'rest'); });
    document.getElementById('m-skip').addEventListener('click', function () { wire.setAttribute('class', 'wire-demo'); tkState.textContent = 'skipped (stays dashed). Both choices are valid.'; M.setPose(tk, 'rest'); });
    // Builder: ready → you start → working → success | failure → calm. Demo states only; no Fabric call is made.
    var bd = document.getElementById('m-build'), bdState = document.getElementById('m-build-state'), ok = document.getElementById('m-ok'), err = document.getElementById('m-err'), cancel = null;
    function run(outcome) {
      if (cancel) cancel(); ok.classList.remove('show'); err.classList.remove('show'); bdState.textContent = 'state: you start';
      cancel = M.build(bd, outcome, { onState: function (s) {
        bdState.textContent = 'state: ' + s + (s === 'calm' ? ' (the status below stays)' : '');
        if (s === 'success') ok.classList.add('show'); if (s === 'failure') err.classList.add('show');
      } });
    }
    document.getElementById('m-sim-ok').addEventListener('click', function () { run('success'); });
    document.getElementById('m-sim-err').addEventListener('click', function () { run('failure'); });
    document.getElementById('m-retry').addEventListener('click', function () { run('success'); });
    document.getElementById('m-details').addEventListener('click', function () { document.getElementById('m-detail-text').hidden = false; });
  }

  window.KrusGraph = { Graph: Graph, loadPlan: loadPlan };
})();
