/* The local demo page (fabric-backend demo). Everything comes from /api/state on 127.0.0.1; the graph is the site's
   Graph (site.js) with the generic layered layout; the figures are the site's mascots (mascots.js), decorative only:
   every status is also text. Accepting a suggestion is a decision taken here, and the page says so. */
(function () {
  var root = document.querySelector('[data-page=local-demo]');
  if (!root || !window.KrusGraph) return;
  var M = window.Mascots, Graph = window.KrusGraph.Graph;
  var state = null, graph = null, selected = null, byId = {};
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function api(method, path, body) {
    return fetch(path, { method: method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined, credentials: 'omit' })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw j; return j; }); });
  }
  function fail(e) { var el = $('error-line'); el.hidden = false; el.textContent = (e && e.error) ? e.error : 'The demo server did not answer. Is `fabric-backend demo` still running?'; }
  function clearFail() { $('error-line').hidden = true; }
  function load() { return api('GET', '/api/state').then(render).catch(fail); }
  function post(path, body) { clearFail(); return api('POST', path, body).then(render).catch(fail); }
  function rule(code) { var r = state && state.plan && state.plan.rules[code]; return r ? r.replace(/`/g, '') : code; }
  function mmss(sec) { sec = Math.max(0, Math.floor(sec)); return Math.floor(sec / 60) + ':' + ('0' + (sec % 60)).slice(-2); }

  /* ------------------------------------------------------------ clock */
  var skew = 0;
  function tick() {
    if (!state) return;
    var now = Date.now() / 1000 - skew, cur = state.steps.filter(function (s) { return s.current; })[0];
    var inStep = cur && cur.entered ? now - cur.entered : 0, total = now - state.started;
    $('clock-step').textContent = mmss(inStep); $('clock-total').textContent = mmss(total);
    document.querySelector('.clock').classList.toggle('over', !!(cur && inStep > cur.minutes * 60));
  }
  setInterval(tick, 1000);

  /* ------------------------------------------------------------ render */
  function render(st) {
    state = st; skew = Date.now() / 1000 - st.now;
    byId = {};
    (st.health && st.health.findings || []).forEach(function (f) { byId[f.id] = f; });
    renderTabs(); renderSource(); renderGraph(); renderStep(); tick();
    if (M) M.mount(root);
  }
  function renderTabs() {
    document.querySelectorAll('.step-tab').forEach(function (b) {
      var n = +b.getAttribute('data-step'), s = state.steps[n - 1];
      b.setAttribute('aria-pressed', s.current ? 'true' : 'false');
      b.disabled = n > 1 && !state.source;
      b.title = s.what;
    });
  }
  function renderSource() {
    var src = state.source;
    $('source-line').textContent = src ? src.label + ' · schema ' + src.schema + ' · ' + src.tables + ' tables' + (src.has_data ? '' : ' · columns only') : 'Not connected yet.';
    $('source-notes').innerHTML = (src ? src.notes : []).map(function (n) { return '<li>' + esc(n) + '</li>'; }).join('');
    $('graph-pill').textContent = src ? (src.kind === 'sample' ? 'synthetic shop data' : src.kind === 'folder' ? 'files on this machine' : src.kind === 'odbc' ? 'your SQL Server, read-only' : 'columns list') : 'no source';
    var list = $('table-list');
    if (!state.plan) { list.innerHTML = ''; return; }
    var colors = ['coral', 'sage', 'lav', 'mustard'];
    list.innerHTML = state.plan.tables.map(function (t, i) {
      var label = !t.key.length ? 'no key' : t.key.length > 1 ? 'composite key' : 'key', code = t.key.length ? t.key_rule : 'K3';
      return '<li><button type="button" data-table="' + esc(t.name) + '"><span class="t-ico c-' + colors[i % 4] + '">' + ICON + '</span><span class="nm">' + esc(t.name) + '</span><span class="rule" title="' + esc('Rule ' + code + ': ' + rule(code)) + '">' + label + '</span></button></li>';
    }).join('');
    list.querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () { if (graph) { graph.selectTable(b.getAttribute('data-table')); $('demo-graph').scrollIntoView({ block: 'nearest', behavior: reduced() ? 'auto' : 'smooth' }); } }); });
  }
  var ICON = '<svg class="g-ico" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><rect x="1.5" y="2.5" width="13" height="11" rx="2.6" fill="currentColor" fill-opacity=".22" stroke="currentColor" stroke-width="1.5"/><path d="M1.5 6.5h13M6.2 6.5v7" stroke="currentColor" stroke-width="1.5"/></svg>';
  function reduced() { return window.matchMedia('(prefers-reduced-motion: reduce)').matches; }

  function openSuggestions() {
    return (state.health ? state.health.findings : []).filter(function (f) { return (f.kind === 'suggestion' || f.kind === 'ambiguous') && !f.accepted && !f.skipped; })
      .map(function (f) { var c = f.next.confirmed; return { source: c.source, source_cols: c.source_cols, target: c.target, target_cols: c.target_cols, rule: 'suggested', finding: f.id }; });
  }
  var follower = null;
  function renderGraph() {
    var area = $('demo-graph');
    area.innerHTML = ''; graph = null; follower = null;
    if (!state.plan) { $('graph-line').textContent = 'Connect a source in step 1. The graph is drawn from the engine\u2019s plan.'; whyDefault(); return; }
    graph = new Graph(area, state.plan, { label: 'Data graph of ' + state.plan.name, suggest: openSuggestions(), autoLayout: true, maxFields: 6 });
    graph.on('select', function (sel) { selected = sel; renderWhy(sel); });
    if (M && M.follower) follower = M.follower(area, { text: 'Explore {table}.' });
    $('graph-line').textContent = state.plan.summary.split('\n')[0] + ' · ' + (state.analysis ? state.analysis.summary.split(';')[1] || '' : '');
    whyDefault();
  }
  $('btn-zoom-in').addEventListener('click', function () { if (graph) graph.zoomBy(1.2); });
  $('btn-zoom-out').addEventListener('click', function () { if (graph) graph.zoomBy(1 / 1.2); });
  $('btn-fit').addEventListener('click', function () { if (graph) graph.fit(); });
  $('btn-mermaid').addEventListener('click', function () {
    if (!state.plan) return;
    var b = $('btn-mermaid'), done = function (ok) { b.textContent = ok ? 'Copied' : 'Copy failed'; setTimeout(function () { b.textContent = 'Copy Mermaid'; }, 1600); };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(state.plan.mermaid).then(function () { done(true); }, function () { done(false); }); else done(false);
  });

  function whyDefault() {
    $('why-body').innerHTML = '<h2>Why this connection?</h2><p class="muted">Select a wire to read the rule that made it, or a table to see its key. Dashed wires are suggestions to review in step 3.</p>' +
      '<div class="note coral"><span data-mascot="onto" data-pose="look" data-label=""></span><div><strong>Onto\u2019s note:</strong> a suggestion, not a guarantee. Names made these links; the plan shows its reasoning so you can overrule it.</div></div>';
    if (M) M.mount($('why-body'));
  }
  function fields(r) {
    var types = {}; state.plan.tables.forEach(function (t) { t.columns.forEach(function (c) { types[t.name + '.' + c.name] = c.type; }); });
    var li = function (t, c) { return '<li><code>' + esc(t + '.' + c) + '</code><span class="type">' + esc(types[t + '.' + c] || '') + '</span></li>'; };
    return '<h3>Field details</h3><ul class="fields">' + r.source_cols.map(function (c) { return li(r.source, c); }).join('') + r.target_cols.map(function (c) { return li(r.target, c); }).join('') + '</ul>';
  }
  function renderWhy(sel) {
    var out = $('why-body');
    if (!sel) return whyDefault();
    if (sel.type === 'table') {
      var t = sel.table, code = t.key.length ? t.key_rule : 'K3', role = state.analysis && state.analysis.roles[t.name];
      out.innerHTML = '<h2>' + esc(t.name) + '</h2><p class="why-head"><span class="why-rule">' + esc(code) + '</span> ' + (t.key.length ? 'key <code>' + esc(t.key.join(' + ')) + '</code>' : 'no key') + '</p>' +
        '<p>' + esc(rule(code)) + '.</p>' + (role ? '<p class="status">Role: <strong>' + esc(role.role) + '</strong> \u2014 ' + esc(role.why) + '</p>' : '') +
        '<h3>Columns</h3><ul class="fields">' + t.columns.map(function (c) { return '<li><code>' + esc(c.name) + '</code>' + (c.key ? ' <span class="muted">key</span>' : c.linked ? ' <span class="muted">linked</span>' : '') + '<span class="type">' + esc(c.type) + '</span></li>'; }).join('') + '</ul>';
      $('graph-line').textContent = t.name + ': ' + (t.key.length ? 'key ' + t.key.join(' + ') + ' by rule ' + code : 'no key (rule K3)');
    } else if (sel.edge.kind === 'suggested') {
      var f = byId[sel.edge.rel.finding];
      out.innerHTML = '<h2>Suggested connection</h2>' + (f ? findingHtml(f, true) : '<p class="muted">Review it in step 3.</p>');
      bindFinding(out);
      $('graph-line').textContent = 'Suggested: ' + sel.edge.rel.source + '.' + sel.edge.rel.source_cols[0] + ' \u2192 ' + sel.edge.rel.target + '.' + sel.edge.rel.target_cols[0] + ' \u00b7 your decision in the panel';
    } else {
      var r = sel.edge.rel, conf = r.rule === 'confirmed';
      out.innerHTML = '<h2><span class="why-rule">' + esc(r.rule) + '</span> Why this connection?</h2><p class="why-path"><code>' + esc(r.source + '.' + r.source_cols.join('+')) + ' \u2192 ' + esc(r.target + '.' + r.target_cols.join('+')) + '</code></p>' +
        '<p>' + (conf ? 'Confirmed by you on this page (Accept in step 3). The data check agreed; the meaning is your call.' : esc(rule(r.rule)) + '. Review it before an API is created on it.') + '</p>' + fields(r) +
        '<p class="status">GraphQL fields: <code>' + esc(r.field) + '</code> on ' + esc(r.source) + ', <code>' + esc(r.reverse) + '</code> on ' + esc(r.target) + '.</p>' +
        '<div class="note coral"><span data-mascot="onto" data-pose="explain" data-label=""></span><div><strong>Onto\u2019s note:</strong> ' + (conf ? 'you accepted this one; accepted is a decision, not a proof.' : 'a suggestion, not a guarantee. Names made this link; you can overrule it.') + '</div></div>';
      $('graph-line').textContent = r.rule + ': ' + r.source + '.' + r.source_cols.join('+') + ' \u2192 ' + r.target + '.' + r.target_cols.join('+');
    }
    if (M) M.mount(out);
  }

  /* ------------------------------------------------------------ steps */
  document.querySelectorAll('.step-tab').forEach(function (b) { b.addEventListener('click', function () { post('/api/step', { step: +b.getAttribute('data-step') }); }); });
  function renderStep() {
    var body = $('step-body'), cur = state.current_step, s = state.steps[cur - 1];
    var head = '<div class="step-head"><span class="step-n ' + ['coral', 'sage', 'lav', 'mustard'][cur - 1] + '">' + cur + '</span><div><h2 style="margin:0">' + esc(s.title) + ' <span class="muted tiny">' + s.minutes + ' min</span></h2><p class="muted" style="margin:2px 0 0">' + esc(s.what) + '</p></div></div>';
    body.innerHTML = head + (cur === 1 ? connectHtml() : cur === 2 ? mapHtml() : cur === 3 ? healthHtml() : valueHtml());
    if (cur === 1) bindConnect(body); else if (cur === 3) bindFinding(body);
    body.querySelectorAll('[data-go]').forEach(function (b) { b.addEventListener('click', function () { post('/api/step', { step: +b.getAttribute('data-go') }); }); });
    body.querySelectorAll('[data-focus]').forEach(function (b) { b.addEventListener('click', function () { if (graph) graph.selectTable(b.getAttribute('data-focus')); }); });
    if (M) M.mount(body);
  }

  function connectHtml() {
    return '<div class="connect-form">' +
      '<p>Pick where the data is. A folder of CSV or Excel files is loaded into a local database in memory; a SQL Server is read with the sign-in in the connection string; a columns list gives the map only.</p>' +
      '<div class="src-kinds" role="group" aria-label="Kind of source">' +
      ['sample|Try without your own data', 'folder|A folder of CSV / Excel files', 'odbc|SQL Server over ODBC', 'columns|A columns list (file)', 'paste|Paste a columns list'].map(function (k) { var p = k.split('|'); return '<button type="button" class="btn ghost small" data-kind="' + p[0] + '" aria-pressed="' + (p[0] === 'sample' ? 'true' : 'false') + '">' + p[1] + '</button>'; }).join('') + '</div>' +
      '<label id="lbl-value" hidden><span id="lbl-value-text">Folder</span><input id="src-value" type="text" autocomplete="off" spellcheck="false" placeholder="C:\\data\\export"></label>' +
      '<label id="lbl-paste" hidden><span>Columns, one per line</span><textarea id="src-paste" rows="8" spellcheck="false" placeholder="Kund.Kundnr\nKund.Namn\nOrder.Ordernr\nOrder.Kundnr\nOrder.Belopp"></textarea></label>' +
      '<label id="lbl-schema" hidden><span>Schema</span><input id="src-schema" type="text" value="dbo" autocomplete="off"></label>' +
      '<p class="muted tiny" id="src-help">The synthetic shop schema from the hosted demo: seven tables, invented names, one column the engine leaves unlinked on purpose.</p>' +
      '<div><button type="button" class="btn" id="btn-connect">Connect</button></div>' +
      '<div class="note sage"><span data-mascot="thinker" data-pose="look" data-label=""></span><div>If the customer only has Excel: export each sheet, or point the demo at the folder with the workbook. The first row is the header; a workbook with several sheets gives one table per sheet.</div></div>' +
      '</div>' + verdictHtml();
  }
  function verdictHtml() {
    var v = state.verdict;
    if (!v) return '';
    var h = v.headline;
    return '<div class="verdict note ' + (h.state === 'enough' ? 'sage' : 'coral') + '" data-verdict="' + esc(h.state) + '"><div><h3 style="margin:0 0 4px">' + esc(h.title) + '</h3><p style="margin:0">' + esc(h.text) + '</p>' +
      (v.items.length ? '<ul class="tiny" style="margin:6px 0 0;padding-left:18px">' + v.items.map(function (i) { return '<li><strong>' + esc(i.title) + '</strong> ' + esc(i.text) + '</li>'; }).join('') + '</ul>' : '') +
      '</div></div>';
  }
  function bindConnect(body) {
    var kind = 'sample';
    var help = { sample: 'The synthetic shop schema from the hosted demo: seven tables, invented names, one column the engine leaves unlinked on purpose.',
      folder: 'Every .csv and .xlsx in the folder becomes a table (file name = table name). Loaded into SQLite in memory on this machine; gone when the demo stops.',
      odbc: 'For example Driver={ODBC Driver 18 for SQL Server};Server=sql01;Database=shopdb;Trusted_Connection=yes;TrustServerCertificate=yes \u2014 a read-only sign-in is enough. The string stays on this machine and is never shown on the page.',
      columns: 'A file with the columns: an INFORMATION_SCHEMA.COLUMNS export, a sheet with Table and Column (Tabell and Kolumn), or lines like Kund.Kundnr. CSV, TXT or XLSX. Plan and map only; no counts.',
      paste: 'Paste the columns as they came: Kund.Kundnr, Kund<tab>Kundnr, Kund: Kundnr, Namn, or a table name followed by its columns. Types are optional. Plan and map only; no counts.' };
    var labels = { folder: 'Folder', odbc: 'ODBC connection string', columns: 'Path to the CSV' };
    var ph = { folder: 'C:\\data\\export', odbc: 'Driver={ODBC Driver 18 for SQL Server};Server=...;Database=...;Trusted_Connection=yes', columns: 'C:\\data\\columns.csv' };
    body.querySelectorAll('[data-kind]').forEach(function (b) {
      b.addEventListener('click', function () {
        kind = b.getAttribute('data-kind');
        body.querySelectorAll('[data-kind]').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
        $('lbl-value').hidden = kind === 'sample' || kind === 'paste'; $('lbl-paste').hidden = kind !== 'paste'; $('lbl-schema').hidden = kind === 'sample' || kind === 'folder';
        $('lbl-value-text').textContent = labels[kind] || ''; $('src-value').placeholder = ph[kind] || ''; $('src-value').type = kind === 'odbc' ? 'password' : 'text';
        $('src-help').textContent = help[kind];
      });
    });
    $('btn-connect').addEventListener('click', function () {
      $('btn-connect').disabled = true; $('btn-connect').textContent = 'Connecting\u2026';
      post('/api/connect', { kind: kind, value: kind === 'paste' ? $('src-paste').value : ($('src-value') ? $('src-value').value : ''), schema: $('src-schema') ? $('src-schema').value : '' })
        .then(function () { return api('GET', '/api/state').then(render); })
        .then(function () { if (state.current_step === 1) { $('btn-connect').disabled = false; $('btn-connect').textContent = 'Connect'; } });
    });
  }

  function mapHtml() {
    if (!state.plan) return '<p class="muted">Connect a source first.</p>';
    var a = state.analysis, roles = a.roles, verdictBox = verdictHtml();
    var byRole = {}; Object.keys(roles).forEach(function (t) { (byRole[roles[t].role] = byRole[roles[t].role] || []).push(t); });
    var roleCards = ['fact', 'dimension', 'bridge', 'isolated', 'other'].filter(function (r) { return byRole[r]; }).map(function (r) {
      return '<div class="q-card"><h3>' + r + ' <span class="muted tiny">' + byRole[r].length + '</span></h3><p class="muted tiny">' + esc(roles[byRole[r][0]].why) + '</p><p>' + byRole[r].map(function (t) { return '<button type="button" class="btn ghost small" data-focus="' + esc(t) + '">' + esc(t) + '</button> '; }).join('') + '</p></div>';
    }).join('');
    var areas = a.areas.map(function (g) { return '<li><strong>' + esc(g.name) + '</strong>: ' + esc(g.tables.join(', ')) + '</li>'; }).join('');
    return verdictBox + '<p class="mono">' + esc(state.plan.summary).replace(/\n/g, '<br>') + '</p><p class="muted">' + esc(a.summary) + '</p>' +
      '<h3>Roles</h3><div class="q-grid">' + roleCards + '</div>' +
      '<h3>Subject areas</h3><ul>' + areas + '</ul>' +
      (state.plan.keyless.length ? '<p class="muted">No key: ' + esc(state.plan.keyless.join(', ')) + ' \u2014 step 3 says what that means.</p>' : '') +
      '<p><button type="button" class="btn" data-go="3">Review plan \u2192</button></p>';
  }

  function findingHtml(f, compact) {
    var cls = 'finding ' + f.severity + (f.accepted ? ' accepted' : '') + (f.skipped ? ' skipped' : '');
    var status = f.accepted ? '<span class="pill sage">accepted here, not verified</span>' : f.skipped ? '<span class="pill">skipped</span>' : '<span class="pill ' + (f.severity === 'problem' ? 'coral' : f.severity === 'suggestion' || f.severity === 'question' ? 'demo' : '') + '">' + esc(f.severity) + '</span>';
    var next = f.next.sql ? '<pre>' + esc(f.next.sql) + '</pre>' : f.next.confirmed ? '<code>confirmed=' + esc(JSON.stringify(f.next.confirmed)) + '</code>' : '<code>keys=' + esc(JSON.stringify(f.next.keys)) + '</code>';
    var buttons = f.can_accept ? '<div class="choice">' +
      (f.accepted ? '<button type="button" class="btn ghost small" data-skip="' + esc(f.id) + '">Undo (skip)</button>' : '<button type="button" class="btn sage small" data-accept="' + esc(f.id) + '">Accept</button><button type="button" class="btn ghost small" data-skip="' + esc(f.id) + '">Skip</button>') + '</div>' : '';
    return '<div class="' + cls + '" data-finding="' + esc(f.id) + '"><h3>' + esc(f.title) + ' ' + status + '</h3>' +
      '<div class="f-row"><b>What we saw</b><span>' + esc(f.saw) + '</span><b>What it means</b><span>' + esc(f.means) + '</span><b>Next step</b><span>' + esc(f.next_text) + '<br>' + next + '</span>' +
      '<b>Evidence</b><span><details' + (compact ? '' : '') + '><summary class="muted tiny">the counting query</summary><pre>' + esc(f.evidence) + '</pre></details></span></div>' + buttons + '</div>';
  }
  function bindFinding(scope) {
    scope.querySelectorAll('[data-accept]').forEach(function (b) { b.addEventListener('click', function () { nod('look'); post('/api/accept', { id: b.getAttribute('data-accept') }); }); });
    scope.querySelectorAll('[data-skip]').forEach(function (b) { b.addEventListener('click', function () { nod('calm'); post('/api/skip', { id: b.getAttribute('data-skip') }); }); });
    scope.querySelectorAll('[data-finding]').forEach(function (d) { d.addEventListener('mouseenter', function () { var f = byId[d.getAttribute('data-finding')]; if (graph && f && graph.nodes[f.table]) graph.highlightTable(f.table); }); d.addEventListener('mouseleave', function () { if (graph) graph.rehighlight(); }); });
  }
  var thinkerPose = 'think';
  function nod(p) { thinkerPose = p; var el = $('thinker'); if (el && M) M.setPose(el, p); }
  function healthHtml() {
    if (!state.health) return '<p class="muted">Connect a source first.</p>';
    var h = state.health, open = h.findings.filter(function (f) { return !f.accepted && !f.skipped; }), done = h.findings.filter(function (f) { return f.accepted || f.skipped; });
    return '<div class="note sage"><span id="thinker" data-mascot="thinker" data-pose="' + thinkerPose + '" data-label=""></span><div><strong>' + esc(h.summary) + '</strong><br>' + esc(h.note) + (h.checked ? '' : ' Without rows, only the names can be judged.') + '</div></div>' +
      (open.length ? '<h3>To review (' + open.length + ')</h3>' + open.map(function (f) { return findingHtml(f); }).join('') : '<p class="muted">Nothing left to review.</p>') +
      (done.length ? '<details><summary>Decided (' + done.length + ')</summary>' + done.map(function (f) { return findingHtml(f); }).join('') + '</details>' : '') +
      '<p><button type="button" class="btn" data-go="4">Show the value \u2192</button> <button type="button" class="btn ghost small" id="btn-reset">Reset decisions</button></p>';
  }
  document.addEventListener('click', function (e) { if (e.target && e.target.id === 'btn-reset') post('/api/reset'); });

  function valueHtml() {
    if (!state.plan) return '<p class="muted">Connect a source first.</p>';
    var cards = state.questions.map(function (q) {
      var table = q.error ? '<p class="muted tiny">' + esc(q.error) + '</p>' : q.note ? '<p class="muted tiny">' + esc(q.note) + '</p>' : !q.rows.length ? '<p class="muted tiny">no rows</p>' :
        '<div class="table-wrap"><table><thead><tr>' + q.columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr></thead><tbody>' + q.rows.map(function (r) { return '<tr>' + r.map(function (c) { return '<td>' + esc(c) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table></div>';
      return '<div class="q-card"><h3>' + esc(q.title) + '</h3><p class="muted tiny">' + esc(q.why) + '</p>' + table + '<details><summary class="muted tiny">SQL, run on this machine</summary><pre class="mono" style="white-space:pre-wrap;font-size:12.5px">' + esc(q.sql) + '</pre></details></div>';
    }).join('');
    var exports = state.exports.map(function (x) { return '<a class="btn ghost small" href="' + esc(x.href) + '" download>' + esc(x.name) + '</a> '; }).join('');
    return '<div class="note lav"><span data-mascot="maker" data-pose="calm" data-label=""></span><div>Five questions proposed from the graph and answered here, with the SQL. The exports are the hand-over: the data dictionary, dbt tests, a prompt for Lovable, the plan and the ER diagram.</div></div>' +
      '<div class="q-grid">' + cards + '</div><h3>Exports</h3><p>' + exports + '</p>' +
      '<p class="muted tiny">Next with the hosted connector: create_backend makes the GraphQL API from this plan, create_semantic_model the Power BI model, create_views the wide views, create_data_agent the data agent.</p>';
  }

  load();
})();
