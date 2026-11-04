/* Krusgraph chat demo (n92, Gustav's decision of 4 November 2026; on every ordinary page, with pictures and a memory
   within the tab since n93). Loaded by site.js on a click on "Try a demo", or to restore a chat that was open on the
   previous page; it never opens by itself on a first visit. Buttons only: no free text, no AI, and the only request it
   makes is GET /demo/plan.json, the engine's output on the synthetic shop (fabric_backend/demo.py). Every number, name
   and picture below comes from that file; what the chat says about creating something comes from tool_status, through
   the button's data attributes (pages.chat_launch_html). It keeps the steps clicked and whether it is open in
   sessionStorage, under one key, in this tab only: known step names, never HTML or text, checked when read. No cookie,
   no localStorage, no logged event. Links open in the same tab and close the chat. Esc and Close close it and give the
   focus back to the button. Under 560 px the chat covers nearly the whole screen, the page behind it does not scroll and
   is inert, and Tab stays inside. */
(function () {
  'use strict';
  var PLAN_URL = '/demo/plan.json';
  var KEY = 'krusgraph.chat';                                   // the one sessionStorage key: {open, steps}
  var STEPS = ['scan', 'yes', 'no', 'model', 'ontology', 'domains', 'fix', 'dbt'];
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var narrow = window.matchMedia('(max-width: 560px)');
  var NAMES = { onto: 'Onto', thinker: 'Thinker', builder: 'Builder' };
  var launch = null, box = null, log = null, closeBtn = null, big = null, P = null, S = null, product = 'Krusgraph';
  var steps = [], quiet = false, gen = 0, pics = [];

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  }
  function code(s) { return '<code>' + esc(s) + '</code>'; }
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
      if (el === box || el.tagName === 'SCRIPT') return;
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
    var from = big._from;
    big.remove();
    big = null;
    Array.prototype.forEach.call(box.children, function (el) { el.removeAttribute('inert'); });
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
  var LEAVE = [{ label: 'Try your own files', href: '/check' },
               { label: 'Connect to your agent', why: 'Opens the set-up guide.', href: '/start' }];
  function planned() {
    return [
      { key: 'fix', label: 'Fix data issues', planned: product + ' finds and counts these today. Proposing a fix you click to apply is planned, and it would leave your source tables as they are.' },
      { key: 'dbt', label: 'Create a dbt flow', planned: 'Today ' + product + ' writes a dbt schema.yml with tests. Generating a whole project is planned.' }
    ];
  }
  function drafts() { return S.linked ? P.drafts.with_suggestion : P.drafts.as_is; }
  function data(key, what) { return launch.getAttribute('data-' + what + '-' + key) || ''; }

  function suggestions() {
    var left = [
      { key: 'model', label: 'Create a semantic model', why: 'The links are checked, so the model can use them.', go: model },
      { key: 'ontology', label: 'Create an ontology', why: 'Give tables and links your business names.', go: ontology },
      { key: 'domains', label: 'Draft data products', why: 'Group the tables, with a contract for each.', go: products }
    ].filter(function (p) { return !S[p.key]; });
    left.forEach(function (p, i) { p.rec = i === 0; if (i) p.why = ''; });
    return left;
  }
  function next() {
    var left = suggestions();
    later(500, function () {
      if (left.length) say('onto', 'point', '<p>What next?</p>', left.concat(planned()), '', true);
      else say('onto', 'explain', '<h3>That is the demo</h3><p>The next step is real: your own files stay in your browser on the check page.</p>',
               LEAVE.concat(planned()), '', true);
    });
  }

  // The result of a step: nothing was created here; what the agent does in the visitor's Fabric, and how far that has
  // been tried, are tool_status's (data-does-* and data-status-* on the button: a plain sentence, no tool's name).
  function done(key, html, pic) {
    S[key] = true;
    var creates = data(key, 'does') === 'creates';
    var note = 'This is a demo, so nothing was created. ' + (creates
      ? 'Connected to ' + product + ', your agent creates this in your Fabric workspace when you ask.'
      : 'Connected to ' + product + ', your agent drafts this from your own tables when you ask; the draft creates nothing in Fabric.');
    var el = say('builder', 'celebrate', html + pic + '<p class="kgc-note">' + esc(note) + ' ' + esc(data(key, 'status')) + '</p>', null, 'win');
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
      done('ontology', '<h3>Ontology ready</h3><p>' + plural(o.entity_types, 'entity type') + ' (' + o.with_key + ' with a key) and ' +
           plural(o.relationship_types, 'relationship type') + '. The ontology item is in preview in Fabric.</p>', pictureOfOntology(o));
    });
  }
  function products() {
    work('thinker', ['Grouping tables by their links', 'Writing the contracts'], function () {
      var d = drafts().domains, n = d.domains.length;
      var out = d.unassigned.filter(function (t) { return P.keyless.indexOf(t) >= 0; });
      done('domains', '<h3>' + plural(n, 'data product') + ' drafted</h3><p>' +
           list(d.domains.map(function (x) { return code(x.name); })) +
           (d.interfaces.length ? ', with ' + (d.interfaces.length === 1 ? 'an interface' : d.interfaces.length + ' interfaces') + ' between them' : '') + '. ' +
           (out.length ? list(out.map(code)) + (out.length === 1 ? ' stays out, because it has no key. ' : ' stay out, because they have no key. ') : '') +
           'You choose the owners, and your admin creates the Fabric domains.</p>', pictureOfDomains(d));
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
    fetch(PLAN_URL, { credentials: 'omit', cache: 'default' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
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
