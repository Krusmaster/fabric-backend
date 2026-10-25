/* Krusgraph site behaviours: navigation, the graph renderer and per-page wiring. No external resources. */
(function () {
  'use strict';
  var M = window.Mascots;

  /* ------------------------------------------------------------------ nav */
  var toggle = document.querySelector('.nav-toggle'), nav = document.getElementById('site-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && nav.classList.contains('open')) { nav.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false'); toggle.focus(); } });
  }

  /* ------------------------------------------------------------------ graph */
  var WIDE = { customers: [40, 200], orders: [330, 60], order_items: [620, 60], products: [620, 320], categories: [900, 320], addresses: [330, 330], audit_log: [40, 430] };
  var NARROW = { customers: [20, 20], orders: [250, 20], addresses: [20, 160], order_items: [250, 160], audit_log: [20, 300], products: [250, 300], categories: [250, 440] };
  var NS = 'http://www.w3.org/2000/svg';
  function el(tag, attrs, text) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  function Graph(container, data, opts) {
    opts = opts || {};
    var self = this;
    this.container = container; this.data = data; this.opts = opts;
    this.handlers = {}; this.selected = null; this.accepted = {}; this.fields = false;
    container.classList.add('graph');
    container.setAttribute('role', 'group');
    container.setAttribute('aria-label', opts.label || 'Data graph: tables and the connections between them');
    var scene = this.scene = document.createElement('div'); scene.className = 'g-scene';
    var svg = this.svg = el('svg', { 'class': 'g-edges' });
    container.appendChild(scene);
    this.nodes = {};
    var tables = opts.tables ? data.tables.filter(function (t) { return opts.tables.indexOf(t.name) >= 0; }) : data.tables;
    tables.forEach(function (t, i) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'g-node' + (t.key.length ? '' : ' keyless'); b.setAttribute('data-table', t.name);
      b.setAttribute('aria-label', t.name + (t.key.length ? ', key ' + t.key.join(' + ') + ' by rule ' + t.key_rule : ', no key (rule K3)'));
      var keyTxt = t.key.length ? t.key.join(' + ') : 'no key';
      b.innerHTML = '<span class="g-node-head"><span class="g-node-name">' + esc(t.name) + '</span><span class="g-node-key" title="' + (t.key.length ? 'key by rule ' + t.key_rule : 'rule K3: no key') + '">' + esc(keyTxt) + '</span></span>' +
        '<ul class="g-node-cols" aria-hidden="true">' + t.columns.map(function (c) { return '<li class="' + (c.key ? 'key' : c.linked ? 'linked' : '') + '"><span>' + esc(c.name) + '</span><span class="t">' + esc(c.type) + '</span></li>'; }).join('') + '</ul>';
      scene.appendChild(b);
      self.nodes[t.name] = { el: b, table: t, i: i };
      b.addEventListener('mouseenter', function () { self.highlightTable(t.name); });
      b.addEventListener('mouseleave', function () { self.rehighlight(); });
      b.addEventListener('focus', function () { self.highlightTable(t.name); self.emit('focus', { type: 'table', table: t, el: b }); });
      b.addEventListener('blur', function () { self.rehighlight(); });
      b.addEventListener('click', function () { self.select({ type: 'table', table: t, el: b }); });
    });
    scene.appendChild(svg);
    this.edges = [];
    data.relationships.forEach(function (r) { if (self.nodes[r.source] && self.nodes[r.target]) self.edges.push({ rel: r, kind: 'rel' }); });
    (opts.suggest || []).forEach(function (s) { if (self.nodes[s.source] && self.nodes[s.target]) self.edges.push({ rel: s, kind: 'suggested' }); });
    this.edges.forEach(function (e) { self.makeEdge(e); });
    (opts.mascots || []).forEach(function (m) {
      var d = document.createElement('div'); d.className = 'g-mascot'; d.setAttribute('aria-hidden', 'true'); d.setAttribute('data-on', m.edge);
      d.innerHTML = M.svg(m.kind, { pose: m.pose || 'rest', idle: m.idle, label: '' }); scene.appendChild(d); self.mascotEls = (self.mascotEls || []).concat([d]);
    });
    container.addEventListener('keydown', function (e) { if (e.key === 'Escape') { self.clearSelection(); } });
    this.layout();
    var ro = window.ResizeObserver ? new ResizeObserver(function () { self.layout(true); }) : null;
    if (ro) ro.observe(container); else window.addEventListener('resize', function () { self.layout(true); });
  }
  Graph.prototype.on = function (ev, fn) { (this.handlers[ev] = this.handlers[ev] || []).push(fn); return this; };
  Graph.prototype.emit = function (ev, arg) { (this.handlers[ev] || []).forEach(function (f) { f(arg); }); };
  Graph.prototype.edgeId = function (r) { return r.source + '.' + r.source_cols.join('+') + '>' + r.target; };
  Graph.prototype.makeEdge = function (e) {
    var self = this, r = e.rel, id = this.edgeId(r);
    var g = el('g', { 'class': 'g-edge rule-' + r.rule + (e.kind === 'suggested' ? ' suggested' : ''), tabindex: '0', role: 'button', 'data-id': id });
    var label = e.kind === 'suggested'
      ? 'Suggested connection: ' + r.source + '.' + r.source_cols.join(', ') + ' to ' + r.target + '.' + r.target_cols.join(', ') + ', not linked by the engine. Review it.'
      : r.source + '.' + r.source_cols.join(', ') + ' points at ' + r.target + '.' + r.target_cols.join(', ') + ', rule ' + r.rule;
    g.setAttribute('aria-label', label);
    e.wire = el('path', { 'class': 'wire' }); e.hit = el('path', { 'class': 'hit' });
    e.dot = el('circle', { 'class': 'dot', r: 4.5 }); e.fork = el('path', { 'class': 'fork' });
    e.n1 = el('text', { 'class': 'card-n' }, '1'); e.nN = el('text', { 'class': 'card-n' }, 'n');
    e.tag = el('g', { 'class': 'tag' }); e.tagRect = el('rect', { width: 34, height: 20, rx: 6 }); e.tagText = el('text', { 'text-anchor': 'middle' }, e.kind === 'suggested' ? '?' : r.rule);
    e.tag.appendChild(e.tagRect); e.tag.appendChild(e.tagText);
    [e.hit, e.wire, e.dot, e.fork, e.n1, e.nN, e.tag].forEach(function (x) { g.appendChild(x); });
    this.svg.appendChild(g); e.el = g; e.id = id;
    g.addEventListener('mouseenter', function () { self.highlightEdge(e); });
    g.addEventListener('mouseleave', function () { self.rehighlight(); });
    g.addEventListener('focus', function () { self.highlightEdge(e); self.emit('focus', { type: 'edge', edge: e, el: g }); });
    g.addEventListener('blur', function () { self.rehighlight(); });
    g.addEventListener('click', function () { self.select({ type: 'edge', edge: e, el: g }); });
    g.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); self.select({ type: 'edge', edge: e, el: g }); } });
  };
  Graph.prototype.rect = function (name) {
    var n = this.nodes[name]; return { x: n.x, y: n.y, w: n.el.offsetWidth || 200, h: n.el.offsetHeight || 46 };
  };
  Graph.prototype.layout = function (keepView) {
    var self = this, cw = this.container.clientWidth;
    var map = cw < 640 ? NARROW : WIDE, fallback = 0;
    this.narrow = cw < 640;
    Object.keys(this.nodes).forEach(function (name) {
      var n = self.nodes[name], p = map[name] || [40 + (fallback % 3) * 290, 60 + Math.floor(fallback++ / 3) * 150];
      if (self.fields) p = [Math.round(p[0] * 1.15), Math.round(p[1] * 1.7)];
      n.x = p[0]; n.y = p[1]; n.el.style.left = p[0] + 'px'; n.el.style.top = p[1] + 'px';
    });
    var maxX = 0, maxY = 0;
    Object.keys(this.nodes).forEach(function (name) { var r = self.rect(name); maxX = Math.max(maxX, r.x + r.w); maxY = Math.max(maxY, r.y + r.h); });
    this.size = { w: maxX + 30, h: maxY + 30 };
    this.scene.style.width = this.size.w + 'px'; this.scene.style.height = this.size.h + 'px';
    this.svg.setAttribute('width', this.size.w); this.svg.setAttribute('height', this.size.h);
    this.edges.forEach(function (e) { self.route(e); });
    (this.mascotEls || []).forEach(function (d) {
      var e = self.edges.filter(function (x) { return x.id === d.getAttribute('data-on'); })[0];
      d.style.display = (self.narrow || !e) ? 'none' : '';
      if (e) { // sit on a horizontal wire (left of the rule pill), or stand beside a vertical one
        if (e.horizontal) { d.style.left = (e.mid.x - 26 - 46) + 'px'; d.style.top = (e.mid.y - 50) + 'px'; }
        else { d.style.left = (e.mid.x + 18) + 'px'; d.style.top = (e.mid.y - 58) + 'px'; }
      }
    });
    this.fit();
  };
  Graph.prototype.route = function (e) {
    var r = e.rel, S = this.rect(r.source), T = this.rect(r.target);
    var sc = { x: S.x + S.w / 2, y: S.y + S.h / 2 }, tc = { x: T.x + T.w / 2, y: T.y + T.h / 2 };
    var dx = tc.x - sc.x, dy = tc.y - sc.y, a, b, c1, c2, dirA, dirB;
    var horizontalGap = Math.abs(dx) - (S.w + T.w) / 2, verticalGap = Math.abs(dy) - (S.h + T.h) / 2;
    e.horizontal = horizontalGap > verticalGap;
    if (e.horizontal) {
      var sgn = dx > 0 ? 1 : -1;
      a = { x: sc.x + sgn * S.w / 2, y: sc.y }; b = { x: tc.x - sgn * T.w / 2, y: tc.y };
      var k = Math.max(40, Math.abs(b.x - a.x) / 2);
      c1 = { x: a.x + sgn * k, y: a.y }; c2 = { x: b.x - sgn * k, y: b.y }; dirA = { x: sgn, y: 0 }; dirB = { x: -sgn, y: 0 };
    } else {
      var sg = dy > 0 ? 1 : -1;
      a = { x: sc.x, y: sc.y + sg * S.h / 2 }; b = { x: tc.x, y: tc.y - sg * T.h / 2 };
      var kk = Math.max(40, Math.abs(b.y - a.y) / 2);
      c1 = { x: a.x, y: a.y + sg * kk }; c2 = { x: b.x, y: b.y - sg * kk }; dirA = { x: 0, y: sg }; dirB = { x: 0, y: -sg };
    }
    var d = 'M' + a.x + ' ' + a.y + ' C' + c1.x + ' ' + c1.y + ' ' + c2.x + ' ' + c2.y + ' ' + b.x + ' ' + b.y;
    e.wire.setAttribute('d', d); e.hit.setAttribute('d', d);
    e.dot.setAttribute('cx', b.x); e.dot.setAttribute('cy', b.y);
    // crow's foot at the many side: three short lines fanning from 12px out back to the anchor
    var px = -dirA.y, py = dirA.x, ox = a.x + dirA.x * 12, oy = a.y + dirA.y * 12;
    e.fork.setAttribute('d', 'M' + ox + ' ' + oy + ' L' + (a.x + px * 6) + ' ' + (a.y + py * 6) + ' M' + ox + ' ' + oy + ' L' + a.x + ' ' + a.y + ' M' + ox + ' ' + oy + ' L' + (a.x - px * 6) + ' ' + (a.y - py * 6));
    e.nN.setAttribute('x', a.x + dirA.x * 18 + px * 10); e.nN.setAttribute('y', a.y + dirA.y * 18 + py * 10 + 4);
    e.n1.setAttribute('x', b.x + dirB.x * 14 + px * 10); e.n1.setAttribute('y', b.y + dirB.y * 14 + py * 10 + 4);
    var m = bez(a, c1, c2, b, 0.5); e.mid = m;
    e.tag.setAttribute('transform', 'translate(' + (m.x - 17) + ',' + (m.y - 10) + ')'); e.tagText.setAttribute('x', 17); e.tagText.setAttribute('y', 14);
  };
  function bez(p0, p1, p2, p3, t) { var u = 1 - t; return { x: u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x, y: u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y }; }
  Graph.prototype.fit = function () {
    var cw = this.container.clientWidth, ch = this.container.clientHeight;
    if (!cw || !ch) return;
    var s = Math.min((cw - 20) / this.size.w, (ch - 20) / this.size.h, 1);
    var tx = (cw - this.size.w * s) / 2, ty = (ch - this.size.h * s) / 2;
    this.scale = s;
    this.scene.style.transform = 'translate(' + tx.toFixed(1) + 'px,' + ty.toFixed(1) + 'px) scale(' + s.toFixed(3) + ')';
  };
  Graph.prototype.setFields = function (on) {
    this.fields = !!on; this.container.classList.toggle('show-fields', this.fields);
    var self = this; Object.keys(this.nodes).forEach(function (n) { self.nodes[n].el.querySelector('.g-node-cols').setAttribute('aria-hidden', self.fields ? 'false' : 'true'); });
    this.layout();
  };
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
    this.accepted[e.id] = !!on; e.el.classList.toggle('accepted', !!on); e.tagText.textContent = on ? '✓' : '?';
    e.el.setAttribute('aria-label', (on ? 'Accepted in this page: ' : 'Suggested connection: ') + e.rel.source + '.' + e.rel.source_cols.join(', ') + ' to ' + e.rel.target + '.' + e.rel.target_cols.join(', ') + (on ? ' (not verified)' : ', not linked by the engine. Review it.'));
  };
  Graph.prototype.reset = function () { var self = this; this.clearSelection(); this.edges.forEach(function (e) { if (e.kind === 'suggested') self.setAccepted(e, false); }); this.setFields(false); };

  function loadPlan(cb) {
    fetch('/demo/plan.json', { credentials: 'omit' }).then(function (r) { return r.json(); }).then(cb).catch(function (err) {
      document.querySelectorAll('[data-plan-error]').forEach(function (x) { x.hidden = false; }); console.error(err);
    });
  }
  function suggestions(data) {
    // The one column the engine leaves unlinked in the demo. The target is a *demo suggestion* (the seed stores address
    // ids there), shown dashed; accepting it is the page-local equivalent of passing confirmed=[...] to the tools.
    var map = { 'orders.ship_to_id': { target: 'addresses', target_cols: ['address_id'] } };
    return (data.unlinked || []).map(function (u) {
      var s = map[u.table + '.' + u.column]; if (!s) return null;
      return { source: u.table, source_cols: [u.column], target: s.target, target_cols: s.target_cols, rule: 'suggested', note: u.note, field: s.target.replace(/s$/, ''), reverse: u.table + '_by_' + u.column };
    }).filter(Boolean);
  }

  /* ------------------------------------------------------------------ home */
  var home = document.querySelector('[data-page=home]');
  if (home) loadPlan(function (data) {
    var g = new Graph(document.getElementById('home-graph'), data, {
      label: 'Data graph of the demo shop schema',
      mascots: [{ kind: 'onto', edge: 'order_items.product_id>products', pose: 'look', idle: 'breathe' },
                { kind: 'thinker', edge: 'orders.customer_id>customers', pose: 'rest' },
                { kind: 'builder', edge: 'products.category_id>categories', pose: 'rest' }]
    });
    var out = document.getElementById('home-why');
    var dflt = out.innerHTML;
    function describe(sel) {
      if (!sel) { out.innerHTML = dflt; return; }
      if (sel.type === 'table') {
        var t = sel.table;
        out.innerHTML = '<strong>' + esc(t.name) + '</strong> · ' + (t.key.length ? 'key <code>' + esc(t.key.join(' + ')) + '</code> by rule <code>' + t.key_rule + '</code>: ' + esc(data.rules[t.key_rule]) : 'no key by rule <code>K3</code>: ' + esc(data.rules.K3)) + '.';
      } else {
        var r = sel.edge.rel;
        out.innerHTML = '<code>' + esc(r.source + '.' + r.source_cols.join('+')) + '</code> → <code>' + esc(r.target + '.' + r.target_cols.join('+')) + '</code> by rule <code>' + r.rule + '</code>: ' + esc(data.rules[r.rule]) + '.';
      }
    }
    g.on('select', describe); g.on('focus', describe);
  });

  /* ------------------------------------------------------------------ explore */
  var explore = document.querySelector('[data-page=explore]');
  if (explore) loadPlan(function (data) {
    var area = document.getElementById('explore-graph'), panel = document.getElementById('why'), list = document.getElementById('table-list');
    var sug = suggestions(data);
    var g = new Graph(area, data, { label: 'Explorable data graph of the demo shop schema', suggest: sug });
    document.getElementById('plan-summary').textContent = data.summary.split('\n')[0] + (sug.length ? ' · ' + sug.length + ' column to review' : '');
    list.innerHTML = data.tables.map(function (t) {
      return '<li><button type="button" data-table="' + esc(t.name) + '"><span>' + esc(t.name) + '</span><span class="rule">' + (t.key.length ? t.key_rule : 'K3') + '</span></button></li>';
    }).join('');
    list.addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) { g.selectTable(b.getAttribute('data-table')); } });
    document.getElementById('btn-fit').addEventListener('click', function () { g.fit(); });
    var bf = document.getElementById('btn-fields');
    bf.addEventListener('click', function () { var on = bf.getAttribute('aria-pressed') !== 'true'; bf.setAttribute('aria-pressed', on ? 'true' : 'false'); g.setFields(on); });
    document.getElementById('btn-reset').addEventListener('click', function () { g.reset(); bf.setAttribute('aria-pressed', 'false'); render(null); });
    var dflt = panel.innerHTML;
    function rule(code) { return '<p>' + esc(data.rules[code] || '') + '</p>'; }
    function render(sel) {
      list.querySelectorAll('button').forEach(function (b) { b.classList.toggle('selected', !!(sel && sel.type === 'table' && b.getAttribute('data-table') === sel.table.name)); });
      if (!sel) { panel.innerHTML = dflt; M.mount(panel); return; }
      if (sel.type === 'table') {
        var t = sel.table;
        panel.innerHTML = '<h2>' + esc(t.name) + '</h2>' +
          (t.key.length ? '<span class="why-rule key">' + t.key_rule + '</span>' + rule(t.key_rule) + '<dl><dt>Key</dt><dd>' + esc(t.key.join(' + ')) + '</dd>'
                        : '<span class="why-rule">K3</span>' + rule('K3') + '<dl><dt>Key</dt><dd>none</dd>') +
          '<dt>Columns</dt><dd>' + t.columns.map(function (c) { return esc(c.name) + ' <span class="muted">' + esc(c.type) + '</span>'; }).join('<br>') + '</dd>' +
          '<dt>Rows</dt><dd>' + t.rows + ' <span class="muted">(synthetic)</span></dd></dl>' +
          (t.key_rule === 'K1' ? '<p class="status">Composite keys cannot be guessed from names; this one was given as <code>keys={"order_items": ["order_id", "line_no"]}</code>.</p>' : '') +
          (t.key.length ? '' : '<p class="status">Query only: it can reference other tables, but nothing can reference it.</p>');
      } else if (sel.edge.kind === 'suggested') {
        var r = sel.edge.rel, acc = g.accepted[sel.edge.id];
        panel.innerHTML = '<h2>Review this connection</h2><span class="why-rule ' + (acc ? 'acc' : 'sug') + '">' + (acc ? 'accepted' : 'not linked') + '</span>' +
          '<p><code>' + esc(r.source + '.' + r.source_cols[0]) + '</code>: ' + esc(r.note) + '. The engine leaves it unlinked and tells you so.</p>' +
          '<dl><dt>Demo suggestion</dt><dd>' + esc(r.target + '.' + r.target_cols[0]) + '</dd><dt>Why</dt><dd class="muted" style="font-family:inherit">the synthetic seed stores address ids in this column</dd></dl>' +
          '<div class="note sage"><span data-mascot="thinker" data-pose="' + (acc ? 'rest' : 'think') + '" data-label="The thinker"></span><div><strong>Review this connection.</strong><br>Your choice. Both are valid.' +
          '<div class="choice"><button type="button" class="btn sage small" id="acc">Accept</button><button type="button" class="btn ghost small" id="skip">Skip</button></div></div></div>' +
          '<p class="status">' + (acc ? 'Accepted here: drawn as a thin sage line. Accepted is not verified — nothing has checked the data. In the real tools this is <code>confirmed=[…]</code>.' : 'Skipped: the connection stays dashed. The choice lives only in this page.') + '</p>';
        M.mount(panel);
        panel.querySelector('#acc').addEventListener('click', function () { g.setAccepted(sel.edge, true); render(sel); });
        panel.querySelector('#skip').addEventListener('click', function () { g.setAccepted(sel.edge, false); render(sel); });
      } else {
        var rr = sel.edge.rel;
        panel.innerHTML = '<h2>Why this connection?</h2><span class="why-rule">' + rr.rule + '</span>' + rule(rr.rule) +
          '<dl><dt>From</dt><dd>' + esc(rr.source + '.' + rr.source_cols.join(' + ')) + '</dd><dt>To</dt><dd>' + esc(rr.target + '.' + rr.target_cols.join(' + ')) + '</dd>' +
          '<dt>Cardinality</dt><dd>many ' + esc(rr.source) + ' → one ' + esc(rr.target) + '</dd>' +
          '<dt>GraphQL</dt><dd>' + esc(rr.source) + '.' + esc(rr.field) + '<br>' + esc(rr.target) + '.' + esc(rr.reverse) + '</dd></dl>' +
          '<div class="note coral"><span data-mascot="onto" data-pose="explain" data-label="Onto"></span><div><strong>Onto’s note:</strong> a suggestion, not a guarantee. Names made this link; you can overrule it.</div></div>';
        M.mount(panel);
      }
    }
    g.on('select', render);
    // Onto: follows the pointer on hover devices; a still helper on touch and for keyboard users.
    var helper = M.follower(area, { text: 'Explore this table.' });
    if (!helper) {
      var still = document.createElement('div'); still.className = 'g-follower visible'; still.style.left = 'auto'; still.style.right = '8px'; still.style.top = 'auto'; still.style.bottom = '8px';
      still.setAttribute('aria-hidden', 'true'); still.innerHTML = M.svg('onto', { pose: 'rest', gaze: false, label: '' }); area.appendChild(still);
      g.on('select', function (sel) { if (sel && sel.type === 'table' && M.enabled()) { M.setPose(still, 'explain'); M.say(area, sel.el, 'Explore this table.', { dx: 8, dy: 0 }); setTimeout(function () { M.say(area, sel.el, ''); M.setPose(still, 'rest'); }, 2200); } });
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
    var poses = ['rest', 'look', 'point', 'celebrate', 'heart', 'notice', 'think', 'explain', 'aside', 'working', 'failure', 'calm'];
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
