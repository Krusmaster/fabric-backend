/* The two-company sales example (/example/sales-planning). Every number comes from the server's result JSON, which
   planning.result() computes from the example's sales lines; this script only shows it, keeps the visitor's choices in
   the URL (so a saved link reopens the same result) and draws the chart. Labels go in with textContent. */
(function () {
  'use strict';
  var root = document.querySelector('[data-page=sales-planning]');
  if (!root) return;
  var PATH = location.pathname.replace(/\/$/, '');
  var SAVE_KEY = 'krusgraph.salesExample.saved';
  var data = JSON.parse(document.getElementById('sp-data').textContent);
  var state = { d: Object.assign({}, data.state.decisions), company: data.state.company, weeks: data.state.weeks };
  var $ = function (id) { return document.getElementById(id); };
  var SVGNS = 'http://www.w3.org/2000/svg';

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function scroll(table) {                                          // a wide table scrolls on its own, never the page
    var w = el('div', 'sp-scroll'); w.tabIndex = 0; w.setAttribute('role', 'region');
    w.setAttribute('aria-label', (table.querySelector('caption') || {}).textContent || 'Table'); w.appendChild(table); return w;
  }
  function svg(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  function fmt(n) { return n == null ? '–' : String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ' '); }
  function signed(n) { return (n >= 0 ? '+' : '−') + fmt(Math.abs(n)); }
  function pct(n) { return (n >= 0 ? '+' : '−') + Math.abs(n) + '%'; }
  function query(st) {
    var d = Object.keys(st.d).filter(function (k) { return st.d[k] !== 'open'; }).sort().map(function (k) { return k + ':' + st.d[k]; });
    return (d.length ? 'd=' + encodeURIComponent(d.join(',')) + '&' : '') + 'company=' + st.company + '&weeks=' + st.weeks;
  }
  function store(fn) { try { return fn(window.localStorage); } catch (e) { return null; } }
  function reveal(ids, focusId) {
    ids.forEach(function (id) { $(id).hidden = false; });
    if (focusId) {
      var h = $(focusId);
      h.focus({ preventScroll: true });
      h.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
  }

  /* ------------------------------------------------------------ the question */
  var QUESTION = data.question;
  function norm(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim(); }
  $('sp-ask').addEventListener('submit', function (ev) {
    ev.preventDefault();
    var note = $('sp-ask-note');
    if (norm($('sp-q').value) === norm(QUESTION) || !norm($('sp-q').value)) {
      note.hidden = true;
      reveal(['scope'], 'scope-h');
      return;
    }
    note.textContent = '';
    note.appendChild(document.createTextNode('This example answers one question: “' + QUESTION + '” Your own question is not analysed here. With your own data, the first conversation starts from your question; today that is a '));
    var a = el('a', null, 'pilot'); a.href = '/partners'; note.appendChild(a);
    note.appendChild(document.createTextNode('. '));
    var b = el('button', 'btn ghost small', 'Continue with the example question'); b.type = 'button';
    b.addEventListener('click', function () { $('sp-q').value = QUESTION; note.hidden = true; reveal(['scope'], 'scope-h'); });
    note.appendChild(b);
    note.hidden = false;
  });

  /* ------------------------------------------------------------ 1. what the answer covers */
  function renderScope() {
    var dl = $('sp-scope'); dl.textContent = '';
    var hist = Object.keys(data.history).map(function (c) {
      return data.companies[c] + ': ' + data.history[c].weeks + ' weeks, from ' + data.history[c].first_label;
    }).join('; ');
    [['Question', data.question],
     ['Companies', Object.keys(data.companies).map(function (c) { return data.companies[c]; }).join(' and ')],
     ['Product group', data.scope.membership],
     ['Sold volume', data.scope.definition.join('. ') + '.'],
     ['Unit', data.scope.unit],
     ['History', hist],
     ['Latest data', data.latest.label + ' (the latest complete week)'],
     ['Not included', data.scope.not_included.join('; ') + '.']].forEach(function (r) {
      var row = el('div'); row.appendChild(el('dt', null, r[0])); row.appendChild(el('dd', null, r[1])); dl.appendChild(row);
    });
  }
  root.querySelectorAll('[data-def]').forEach(function (b) {
    b.addEventListener('click', function () {
      if (b.getAttribute('data-def') === 'yes') { $('sp-def-note').hidden = true; start(); return; }
      var n = $('sp-def-note'); n.hidden = false;
      if (!n.querySelector('button')) {
        var go = el('button', 'btn ghost small', 'See the example with this definition'); go.type = 'button';
        go.addEventListener('click', start);
        n.appendChild(document.createTextNode(' ')); n.appendChild(go);
      }
    });
  });
  function start() {
    reveal(['link', 'view', 'forecast', 'meeting'], 'link-h');
    renderChart();                                                     // drawn at its real width now that it is visible
    history.replaceState(null, '', PATH + '?' + query(state));
  }

  /* ------------------------------------------------------------ 2. the product links */
  function renderLinks() {
    var box = $('sp-links'); box.textContent = '';
    var refName = data.scope.reference;
    var ref = data.scope.reference_code;
    var others = data.links.filter(function (l) { return l.company !== ref; });
    var group = data.links.filter(function (l) { return l.company === ref && l.status === 'in group'; });
    var table = el('table', 'sp-link-table');
    var head = el('tr'); ['Company B product', 'In the group?', 'Why'].forEach(function (h) { head.appendChild(el('th', null, h)); });
    var thead = el('thead'); thead.appendChild(head); table.appendChild(thead);
    var tb = el('tbody');
    others.forEach(function (l) {
      var tr = el('tr', l.suggested ? 'sp-decide-row' : '');
      var name = el('td'); name.appendChild(el('strong', null, l.name)); name.appendChild(el('span', 'muted tiny', ' ' + l.product));
      var st = el('td'); st.appendChild(el('span', 'sp-status sp-status-' + l.status.replace(' ', '-'),
        { linked: 'Yes, linked', outside: 'No', open: 'Your decision', 'in group': 'Yes' }[l.status]));
      tr.appendChild(name); tr.appendChild(st); tr.appendChild(el('td', null, l.basis + (l.target && l.status === 'linked' ? ' → ' + nameOf(l.target) : '')));
      tb.appendChild(tr);
    });
    table.appendChild(tb); box.appendChild(scroll(table));

    others.filter(function (l) { return l.suggested; }).forEach(function (l) {
      var card = el('div', 'sp-decide card');
      card.appendChild(el('h3', null, 'Is ' + l.name + ' (Company B) the same product as ' + nameOf(l.suggested) + ' (' + refName + ')?'));
      var ev = el('ul', 'sp-evidence'); l.evidence.forEach(function (t) { ev.appendChild(el('li', null, t)); }); card.appendChild(ev);
      var fs = el('fieldset', 'sp-choices'); fs.appendChild(el('legend', 'visually-hidden', 'Your decision for ' + l.name));
      var current = state.d[l.product] || 'open';
      var opts = [[l.suggested, 'Yes, the same product as ' + nameOf(l.suggested)]];
      group.forEach(function (g) { if (g.product !== l.suggested) opts.push([g.product, 'No, it is ' + g.name]); });
      opts.push(['none', 'No, it is not one of ' + refName + '’s lights']);
      opts.push(['open', 'Leave it open for now']);
      opts.forEach(function (o) {
        var lab = el('label', 'sp-choice'); var r = el('input'); r.type = 'radio'; r.name = 'link-' + l.product; r.value = o[0];
        r.checked = current === o[0];
        r.addEventListener('change', function () { state.d[l.product] = o[0]; update(); });
        lab.appendChild(r); lab.appendChild(document.createTextNode(' ' + o[1])); fs.appendChild(lab);
      });
      card.appendChild(fs);
      var effect = { open: 'Open: its sales are shown on their own in step 3 and are not in the combined numbers.',
                     none: 'Not a light: its sales stay out of the group, like the bell and the lock.' }[current] ||
                   'Linked: its sales count in the group as ' + nameOf(current) + ', from now on in every number below.';
      card.appendChild(el('p', 'sp-effect', effect));
      box.appendChild(card);
    });
  }
  function nameOf(p) { var l = data.links.filter(function (x) { return x.product === p; })[0]; return l ? l.name : p; }

  /* ------------------------------------------------------------ 3. the view: tiles, chart, table, checks */
  function tile(label, value, sub) {
    var t = el('div', 'sp-tile'); t.appendChild(el('span', 'sp-tile-label', label)); t.appendChild(el('strong', 'sp-tile-value', value));
    if (sub) t.appendChild(el('span', 'sp-tile-sub muted', sub));
    return t;
  }
  function renderTiles() {
    var box = $('sp-tiles'); box.textContent = '';
    var p = data.period, range = p.from_label + ' – ' + p.to_label;
    box.appendChild(tile('Sold in the period', fmt(p.total) + ' units', range));
    Object.keys(p.by_company).forEach(function (c) { if (Object.keys(p.by_company).length > 1) box.appendChild(tile(data.companies[c], fmt(p.by_company[c]) + ' units', null)); });
    var ye = p.year_earlier;
    box.appendChild(ye.total != null ? tile('Against a year earlier', signed(ye.change) + ' units', (ye.change_pct != null ? pct(ye.change_pct) + ', ' : '') + 'same weeks a year earlier')
                                     : tile('Against a year earlier', 'Not comparable', ye.why_not));
    var f = data.forecast;
    box.appendChild(f.available ? tile('Next 8 weeks', fmt(f.total_low) + '–' + fmt(f.total_high), '80% range from ' + f.tests + ' past tests')
                                : tile('Next 8 weeks', 'No forecast', 'too little history for this selection'));
  }

  function niceStep(max, n) {
    var raw = max / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * mag;
  }
  function barPath(x, y, w, h, r) {        // 4px rounded data end on top, square at the baseline
    r = Math.min(r, w / 2, h);
    return 'M' + x + ',' + (y + h) + 'V' + (y + r) + 'Q' + x + ',' + y + ' ' + (x + r) + ',' + y + 'H' + (x + w - r) +
           'Q' + (x + w) + ',' + y + ' ' + (x + w) + ',' + (y + r) + 'V' + (y + h) + 'Z';
  }
  var chartIndex = -1, cols = [];
  function renderChart() {
    var host = $('sp-chart'); host.textContent = '';
    var comps = Object.keys(data.companies), f = data.forecast;
    cols = data.rows.map(function (r) { return { kind: 'actual', row: r }; });
    if (f.available) f.points.forEach(function (p) { cols.push({ kind: 'forecast', point: p }); });
    var W = Math.max(280, host.clientWidth || 600), H = W < 520 ? 230 : 290, m = { l: 44, r: 10, t: 22, b: 30 };
    var pw = W - m.l - m.r, ph = H - m.t - m.b, n = cols.length, band = pw / n;
    var maxV = 0;
    cols.forEach(function (c) { maxV = Math.max(maxV, c.kind === 'actual' ? c.row.total : c.point.high); });
    var step = niceStep(maxV || 1, 4), top = Math.ceil((maxV || 1) / step) * step;
    var y = function (v) { return m.t + ph - (v / top) * ph; };
    var s = svg('svg', { viewBox: '0 0 ' + W + ' ' + H, width: '100%', height: H, class: 'sp-svg', tabindex: '0', role: 'group',
                         'aria-label': 'Weekly sold volume' + (f.available ? ' and the eight-week forecast' : '') + '. Use the arrow keys to read each week.',
                         'aria-describedby': 'sp-tip' });
    for (var v = 0; v <= top + 1e-9; v += step) {
      s.appendChild(svg('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: 'sp-grid' }));
      var t = svg('text', { x: m.l - 6, y: y(v) + 4, class: 'sp-axis', 'text-anchor': 'end' }); t.textContent = v >= 1000 ? (v / 1000) + 'K' : String(v); s.appendChild(t);
    }
    var bw = Math.max(1, Math.min(24, band - 2));
    var every = Math.max(1, Math.ceil(n / Math.max(4, Math.floor(pw / 46))));
    cols.forEach(function (c, i) {
      var x = m.l + i * band + (band - bw) / 2;
      if (c.kind === 'actual') {
        var base = 0, parts = comps.filter(function (k) { return c.row[k]; });
        parts.forEach(function (k, j) {
          var v = c.row[k], y0 = y(base + v), h = y(base) - y0 - (j > 0 ? 2 : 0);      // 2px surface gap between segments
          if (h > 0) s.appendChild(svg('path', { d: j === parts.length - 1 ? barPath(x, y0, bw, h, 4) : 'M' + x + ',' + y0 + 'h' + bw + 'v' + h + 'h' + -bw + 'Z',
                                                  class: 'sp-bar sp-' + k }));
          base += v;
        });
      }
      var wk = (c.kind === 'actual' ? c.row.label : c.point.label).replace(/^week (\d+), (\d+)$/, '$1');
      if (i % every === 0) { var tl = svg('text', { x: m.l + i * band + band / 2, y: H - 10, class: 'sp-axis', 'text-anchor': 'middle' }); tl.textContent = 'w' + wk; s.appendChild(tl); }
    });
    if (f.available) {
      var first = data.rows.length, bx = m.l + first * band;
      var pts = f.points.map(function (p, j) { return [m.l + (first + j) * band + band / 2, p]; });
      var area = pts.map(function (q) { return q[0] + ',' + y(q[1].high); }).concat(pts.slice().reverse().map(function (q) { return q[0] + ',' + y(q[1].low); }));
      s.appendChild(svg('polygon', { points: area.join(' '), class: 'sp-band' }));
      s.appendChild(svg('polyline', { points: pts.map(function (q) { return q[0] + ',' + y(q[1].forecast); }).join(' '), class: 'sp-fline' }));
      var last = pts[pts.length - 1];
      s.appendChild(svg('circle', { cx: last[0], cy: y(last[1].forecast), r: 4, class: 'sp-fdot' }));
      s.appendChild(svg('line', { x1: bx, x2: bx, y1: m.t - 14, y2: m.t + ph, class: 'sp-divider' }));
      var ft = svg('text', { x: bx + 4, y: m.t - 6, class: 'sp-axis sp-ftext' }); ft.textContent = 'Forecast →'; s.appendChild(ft);
    }
    var cross = svg('line', { x1: 0, x2: 0, y1: m.t, y2: m.t + ph, class: 'sp-cross', visibility: 'hidden' });
    s.appendChild(cross);
    var hit = svg('rect', { x: m.l, y: m.t, width: pw, height: ph, fill: 'transparent' });
    s.appendChild(hit);
    function at(i) {
      chartIndex = Math.max(0, Math.min(n - 1, i));
      var cx = m.l + chartIndex * band + band / 2;
      cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.setAttribute('visibility', 'visible');
      readout(cols[chartIndex]);
    }
    s.addEventListener('pointermove', function (e) {
      var r = s.getBoundingClientRect(), px = (e.clientX - r.left) * (W / r.width);
      at(Math.floor((px - m.l) / band));
    });
    s.addEventListener('pointerleave', function () { if (document.activeElement !== s) cross.setAttribute('visibility', 'hidden'); });
    s.addEventListener('keydown', function (e) {
      var k = { ArrowRight: 1, ArrowLeft: -1, Home: -1e9, End: 1e9 }[e.key];
      if (k === undefined) return;
      e.preventDefault(); at((chartIndex < 0 ? n - 1 : chartIndex) + k);
    });
    s.addEventListener('focus', function () { at(chartIndex < 0 ? data.rows.length - 1 : chartIndex); });
    host.appendChild(s);
    $('sp-chart-title').textContent = 'Units sold per week' + (f.available ? ', then the forecast' : '');
    var lg = $('sp-legend'); lg.textContent = '';
    comps.forEach(function (k) { var i = el('span', 'sp-key'); i.appendChild(el('i', 'sp-sw sp-' + k)); i.appendChild(document.createTextNode(data.companies[k])); lg.appendChild(i); });
    if (f.available) {
      var a = el('span', 'sp-key'); a.appendChild(el('i', 'sp-sw sp-line')); a.appendChild(document.createTextNode('Forecast')); lg.appendChild(a);
      var b = el('span', 'sp-key'); b.appendChild(el('i', 'sp-sw sp-wash')); b.appendChild(document.createTextNode('80% range')); lg.appendChild(b);
    }
  }
  function readout(c) {
    var tip = $('sp-tip'); tip.textContent = '';
    if (c.kind === 'actual') {
      tip.appendChild(el('strong', null, fmt(c.row.total) + ' units'));
      var parts = Object.keys(data.companies).map(function (k) { return data.companies[k] + ' ' + (c.row[k] == null ? 'no data yet' : fmt(c.row[k])); });
      tip.appendChild(document.createTextNode(' sold in ' + c.row.label + (parts.length > 1 ? ': ' + parts.join(' · ') : '')));
    } else {
      tip.appendChild(el('strong', null, fmt(c.point.forecast) + ' units'));
      tip.appendChild(document.createTextNode(' forecast for ' + c.point.label + ', 80% range ' + fmt(c.point.low) + '–' + fmt(c.point.high)));
    }
  }
  function renderTable() {
    var box = $('sp-table'); box.textContent = '';
    var comps = Object.keys(data.companies), t = el('table');
    t.appendChild(el('caption', 'visually-hidden', 'Units sold per week, then the forecast'));
    var hr = el('tr'); ['Week'].concat(comps.map(function (c) { return data.companies[c]; }), ['Total', 'Forecast', '80% range']).forEach(function (h) { hr.appendChild(el('th', null, h)); });
    var th = el('thead'); th.appendChild(hr); t.appendChild(th);
    var tb = el('tbody');
    data.rows.forEach(function (r) {
      var tr = el('tr'); tr.appendChild(el('td', null, r.label));
      comps.forEach(function (c) { tr.appendChild(el('td', 'num', r[c] == null ? 'no data' : fmt(r[c]))); });
      tr.appendChild(el('td', 'num', fmt(r.total))); tr.appendChild(el('td')); tr.appendChild(el('td')); tb.appendChild(tr);
    });
    if (data.forecast.available) data.forecast.points.forEach(function (p) {
      var tr = el('tr', 'sp-frow'); tr.appendChild(el('td', null, p.label));
      comps.forEach(function () { tr.appendChild(el('td')); }); tr.appendChild(el('td'));
      tr.appendChild(el('td', 'num', fmt(p.forecast))); tr.appendChild(el('td', 'num', fmt(p.low) + '–' + fmt(p.high))); tb.appendChild(tr);
    });
    t.appendChild(tb); box.appendChild(scroll(t));
    if (data.products.length) {
      var pt = el('table', 'sp-products'); pt.appendChild(el('caption', null, 'By product in the period (Company A’s product names)'));
      var ph = el('tr'); ['Product', 'Company', 'Units', 'A year earlier'].forEach(function (h) { ph.appendChild(el('th', null, h)); });
      var pth = el('thead'); pth.appendChild(ph); pt.appendChild(pth);
      var ptb = el('tbody');
      data.products.forEach(function (p) {
        var tr = el('tr'); [p.name, p.company_name].forEach(function (v) { tr.appendChild(el('td', null, v)); });
        tr.appendChild(el('td', 'num', fmt(p.units))); tr.appendChild(el('td', 'num', p.year_earlier == null ? 'not comparable' : fmt(p.year_earlier)));
        ptb.appendChild(tr);
      });
      pt.appendChild(ptb); box.appendChild(scroll(pt));
    }
  }
  function renderOpen() {
    var box = $('sp-open'); box.textContent = '';
    data.open.forEach(function (o) {
      var c = el('div', 'sp-open card soft');
      c.appendChild(el('h3', null, 'Not in these numbers yet: ' + o.name + ' (' + o.company_name + ')'));
      c.appendChild(el('p', null, fmt(o.units_in_period) + ' units in the period; sold since ' + o.first_week + ' (' + o.weeks_sold + ' weeks). '
        + 'Decide its link in step 2 to count it in the group.'));
      if (o.no_forecast_because) c.appendChild(el('p', 'muted', 'No forecast for it on its own: ' + o.no_forecast_because));
      box.appendChild(c);
    });
  }
  function renderChecks() {
    var ul = $('sp-checks'); ul.textContent = '';
    data.checks.forEach(function (c) {
      var li = el('li', c.ok ? 'ok' : 'bad');
      li.appendChild(el('span', 'sp-check-mark', c.ok ? '✓ Holds' : '✗ Does not hold'));
      li.appendChild(el('strong', null, c.name + ': ')); li.appendChild(document.createTextNode(c.result));
      ul.appendChild(li);
    });
  }

  /* ------------------------------------------------------------ 4. the forecast */
  function renderForecast() {
    var box = $('sp-forecast'); box.textContent = '';
    var f = data.forecast, who = Object.keys(data.companies).map(function (c) { return data.companies[c]; }).join(' and ');
    if (!f.available) {
      box.appendChild(el('p', 'sp-headline', 'No forecast for this selection.'));
      box.appendChild(el('p', null, f.reason + ' The history in step 3 still holds.'));
      return;
    }
    box.appendChild(el('p', 'sp-headline', fmt(f.total_low) + '–' + fmt(f.total_high) + ' units in ' + f.points[0].label.replace(/, \d+$/, '') +
      '–' + f.points[f.points.length - 1].label.replace(/^week /, '') + ' (80% range)'));
    var dl = el('dl', 'detail-list');
    [['What it forecasts', 'Units of the group sold per week by ' + who + ', built on ' + f.built_on + '. Sold volume, not demand.'],
     ['Method used', f.method_name + ': ' + f.how + '. Its own figure: ' + fmt(f.total) + ' units.'],
     ['How it was tested', f.tests + ' times: each time a forecast for 8 weeks from the history before that point, compared with what was then sold. '
       + 'The error is the share of units missed over all those weeks. The method with the smallest error is used, also when it is the simplest.'],
     ['The range', 'The middle 80% of how far the actual sales landed from the method’s figure in the ' + f.tests + ' tests, applied to today’s figure. With so few tests it is a rough guide.' +
       (f.leans ? ' In the tests the actual sales came out ' + (f.leans === 'low' ? 'above' : 'below') + ' the method’s figure ' +
        (f.leans === 'low' ? f.actual_above : f.tests - f.actual_above) + ' times out of ' + f.tests + ', which is why the range sits ' +
        (f.leans === 'low' ? 'above' : 'below') + ' it.' : '')]].forEach(function (r) {
      var row = el('div'); row.appendChild(el('dt', null, r[0])); row.appendChild(el('dd', null, r[1])); dl.appendChild(row);
    });
    box.appendChild(dl);
    if (f.elaborate_lost) box.appendChild(el('p', 'sp-note', 'The more elaborate method did not beat a simpler one in these tests, so the simpler one is used.'));
    var t = el('table', 'sp-methods'); t.appendChild(el('caption', null, 'How each method did in the same ' + f.tests + ' tests'));
    var hr = el('tr'); ['Method', 'How it forecasts', 'Error in the tests', ''].forEach(function (h) { hr.appendChild(el('th', null, h)); });
    var th = el('thead'); th.appendChild(hr); t.appendChild(th);
    var tb = el('tbody');
    f.methods.forEach(function (m) {
      var tr = el('tr', m.used ? 'used' : ''); tr.appendChild(el('td', null, m.name)); tr.appendChild(el('td', 'muted', m.how));
      tr.appendChild(el('td', 'num', m.error_pct + '%')); tr.appendChild(el('td', null, m.used ? 'Used' : '')); tb.appendChild(tr);
    });
    t.appendChild(tb); box.appendChild(scroll(t));
    box.appendChild(el('p', 'muted tiny', 'Not included: what to buy or how to staff. The forecast says how many units were likely to be sold if the weeks ahead behave like the weeks it was tested on.'));
  }

  /* ------------------------------------------------------------ 5. the note, saving and reopening */
  function renderSummary() {
    var ul = $('sp-summary'); ul.textContent = '';
    data.summary.forEach(function (s) { ul.appendChild(el('li', null, s)); });
  }
  function link() { return location.origin + PATH + '?' + query(state); }
  function label() {
    var parts = [state.company === 'all' ? 'Both companies' : data.companies[state.company], 'last ' + state.weeks + ' weeks'];
    data.links.filter(function (l) { return l.suggested; }).forEach(function (l) {
      var d = state.d[l.product] || 'open';
      parts.push(l.name + ': ' + (d === 'open' ? 'left open' : d === 'none' ? 'not a light' : 'linked to ' + nameOf(d)));
    });
    return parts.join(', ');
  }
  function renderSaved() {
    var list = store(function (s) { return JSON.parse(s.getItem(SAVE_KEY) || '[]'); }) || [];
    var box = $('sp-saved'), ul = box.querySelector('ul'); ul.textContent = '';
    box.hidden = !list.length;
    list.forEach(function (it, i) {
      var li = el('li'); var a = el('a', null, it.label); a.href = it.url; li.appendChild(a);
      li.appendChild(el('span', 'muted tiny', ' saved ' + it.saved + ' · ' + it.id + ' '));
      var rm = el('button', 'sp-remove', 'Remove'); rm.type = 'button';
      rm.addEventListener('click', function () { list.splice(i, 1); store(function (s) { s.setItem(SAVE_KEY, JSON.stringify(list)); }); renderSaved(); });
      li.appendChild(rm); ul.appendChild(li);
    });
  }
  $('sp-save').addEventListener('click', function () {
    var list = store(function (s) { return JSON.parse(s.getItem(SAVE_KEY) || '[]'); }) || [];
    var url = PATH + '?' + query(state);
    list = list.filter(function (it) { return it.url !== url; });
    list.unshift({ id: data.result_id, url: url, label: label(), saved: new Date().toISOString().slice(0, 10) });
    var ok = store(function (s) { s.setItem(SAVE_KEY, JSON.stringify(list.slice(0, 10))); return true; });
    $('sp-save-note').textContent = ok ? 'Saved in this browser as ' + data.result_id + '. It opens with the same definition, links and filters, from the list at the top of this page or with the link.'
                                       : 'This browser does not keep saved results; copy the link instead.';
    renderSaved();
  });
  $('sp-copy').addEventListener('click', function () {
    var done = function (ok) { $('sp-save-note').textContent = ok ? 'Link copied. It reopens this result with the same choices.' : 'Copying failed; the link is in the address bar.'; };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(link()).then(function () { done(true); }, function () { done(false); });
    else done(false);
  });
  $('sp-download').addEventListener('click', function () {
    var md = ['# Planning note: example with synthetic data', '', 'Question: ' + data.question, 'Choices: ' + label(),
              'Result ' + data.result_id + ', definition ' + data.definition_id + ', data up to ' + data.latest.label, 'Link: ' + link(), '']
      .concat(data.summary.map(function (s) { return '- ' + s; }))
      .concat(['', 'Company A, Company B and all numbers are invented for this example.', '']).join('\n');
    var a = el('a'); a.href = URL.createObjectURL(new Blob([md], { type: 'text/markdown' }));
    a.download = 'planning-note-' + data.result_id + '.md'; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  });

  /* ------------------------------------------------------------ filters and refetch */
  $('sp-company').value = state.company; $('sp-weeks').value = String(state.weeks);
  $('sp-company').addEventListener('change', function () { state.company = this.value; update(); });
  $('sp-weeks').addEventListener('change', function () { state.weeks = parseInt(this.value, 10); update(); });
  var pending = 0;
  function update() {
    var mine = ++pending, body = root.querySelector('.sp-body');
    body.classList.add('loading');                                    // the previous render stays, dimmed, until the new one arrives
    fetch(PATH + '/result.json?' + query(state), { headers: { Accept: 'application/json' } })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; }); })
      .then(function (j) {
        if (mine !== pending) return;
        data = j; renderAll(); body.classList.remove('loading');
        history.replaceState(null, '', PATH + '?' + query(state));
      })
      .catch(function (e) { body.classList.remove('loading'); $('sp-tip').textContent = 'The result could not be loaded: ' + e.message; });
  }
  function renderAll() {
    renderScope(); renderLinks(); renderTiles(); renderChart(); renderTable(); renderOpen(); renderChecks(); renderForecast(); renderSummary();
  }
  var lastW = 0;
  window.addEventListener('resize', function () { var w = $('sp-chart').clientWidth; if (w && w !== lastW) { lastW = w; renderChart(); } });

  renderAll();
  renderSaved();
  if (/[?&](company|weeks|d)=/.test(location.search)) {          // a saved link: straight to the result, with the same choices
    reveal(['scope', 'link', 'view', 'forecast', 'meeting']);
    var n = $('sp-reopened');
    n.textContent = 'Reopened ' + data.result_id + ': the same definition (' + data.definition_id + '), links and filters as when it was saved. Data up to ' + data.latest.label + '.';
    n.hidden = false;
    lastW = $('sp-chart').clientWidth; renderChart();
  }
})();
