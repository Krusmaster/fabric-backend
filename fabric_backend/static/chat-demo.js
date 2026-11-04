/* Krusgraph chat demo on the start page (n92, Gustav's decision of 4 November 2026).
   Loaded by site.js on the first click on "Try a demo"; never opens by itself. Buttons only: no free text, no AI, and the
   only request it makes is GET /demo/plan.json, the engine's output on the synthetic shop (fabric_backend/demo.py). Every
   number below comes from that file; what the chat says about creating something comes from tool_status, through the
   button's data attributes (pages.chat_launch_html). No cookie, no localStorage, no logged event. Links open in the same
   tab. Esc and Close close it and give the focus back to the button. Under 560 px the chat covers nearly the whole
   screen, the page behind it does not scroll and is inert, and Tab stays inside. */
(function () {
  'use strict';
  var PLAN_URL = '/demo/plan.json';
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var narrow = window.matchMedia('(max-width: 560px)');
  var NAMES = { onto: 'Onto', thinker: 'Thinker', builder: 'Builder' };
  var launch = null, box = null, log = null, closeBtn = null, P = null, S = null, product = 'Krusgraph';

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  }
  function code(s) { return '<code>' + esc(s) + '</code>'; }
  function list(xs) { return xs.length < 2 ? xs.join('') : xs.slice(0, -1).join(', ') + ' and ' + xs[xs.length - 1]; }
  function plural(n, one, many) { return n + ' ' + (n === 1 ? one : (many || one + 's')); }
  function figure(who, pose) {
    return window.Mascots ? window.Mascots.svg(who, { pose: pose, label: '', gaze: false }) : '';
  }
  function later(ms, fn) { setTimeout(fn, reduced.matches ? 0 : ms); }
  // Scroll the log (never the page) so the new message shows, from its top as far down as fits.
  function show(el) {
    var lr = log.getBoundingClientRect(), er = el.getBoundingClientRect();
    var top = er.top - lr.top + log.scrollTop - 8, bottom = er.bottom - lr.top + log.scrollTop + 8;
    var want = Math.min(top, bottom - log.clientHeight);
    if (want > log.scrollTop) log.scrollTop = want;
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
      '<p class="kgc-foot">Buttons only. No AI, and nothing you click is sent anywhere.</p>';
    document.body.appendChild(box);
    log = box.querySelector('.kgc-log');
    closeBtn = box.querySelector('.kgc-close');
    closeBtn.addEventListener('click', function () { setOpen(false); });
    box.addEventListener('keydown', trapTab);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !box.hidden) { e.preventDefault(); setOpen(false); }
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
      return el.offsetParent !== null || el === document.activeElement;
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

  /* ------------------------------------------------------------------ messages and buttons */
  function you(text) {
    var el = document.createElement('p');
    el.className = 'kgc-you';
    el.textContent = text;
    log.appendChild(el);
    show(el);
  }

  // picks: [{label, why?, rec?, href?, planned?, go?}]. A planned pick runs nothing: it says what exists today.
  function say(who, pose, html, picks, cls, focusFirst) {
    var el = document.createElement('div');
    el.className = 'kgc-msg ' + who + (cls ? ' ' + cls : '');
    el.innerHTML = '<span class="kgc-fig" aria-hidden="true">' + figure(who, pose) + '</span>' +
      '<div class="kgc-bub"><p class="kgc-who">' + NAMES[who] + '</p>' + html + '</div>';
    var first = null;
    if (picks && picks.length) {
      var row = document.createElement('div');
      row.className = 'kgc-picks';
      picks.forEach(function (p) {
        var b = document.createElement(p.href ? 'a' : 'button');
        b.className = 'kgc-pick' + (p.rec ? ' rec' : '') + (p.planned ? ' planned' : '');
        b.setAttribute('data-pick', p.label);
        b.innerHTML = esc(p.label) + (p.planned ? '<i>Planned</i>' : '') + (p.why ? '<small>' + esc(p.why) + '</small>' : '');
        if (p.href) {
          b.href = p.href;
          b.addEventListener('click', function () {
            if (b.pathname === location.pathname && b.hash) setOpen(false, true);    // /#connect: close, let the page scroll there
          });
        } else {
          b.type = 'button';
          b.addEventListener('click', function () {
            if (p.planned) {
              if (b.getAttribute('aria-disabled') === 'true') return;
              b.setAttribute('aria-disabled', 'true');
              say('onto', 'explain', '<p>' + esc(p.planned) + '</p>');
              return;
            }
            log.focus({ preventScroll: true });           // keep the focus in the chat while the buttons go
            row.remove();
            you(p.label);
            p.go();
          });
        }
        if (!first) first = b;
        row.appendChild(b);
      });
      el.appendChild(row);
    }
    log.appendChild(el);
    show(el);
    if (first && focusFirst) first.focus({ preventScroll: true });
    return el;
  }

  function work(who, steps, done) {
    var el = say(who, 'working', '<ul class="kgc-steps">' + steps.map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ul>');
    var items = el.querySelectorAll('li'), i = 0;
    (function next() {
      if (i > 0) items[i - 1].className = 'did';
      if (i === items.length) { later(220, done); return; }
      items[i++].className = 'doing';
      later(440, next);
    })();
  }

  function cheer(el) {
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

  /* ------------------------------------------------------------------ the flow */
  var LEAVE = [{ label: 'Try your own files', href: '/check' }, { label: 'Connect to your agent', href: '/#connect' }];
  function planned() {
    return [
      { label: 'Fix data issues', planned: product + ' finds and counts these today. Proposing a fix you click to apply is planned, and it would leave your source tables as they are.' },
      { label: 'Create a dbt flow', planned: 'Today ' + product + ' writes a dbt schema.yml with tests. Generating a whole project is planned.' }
    ];
  }
  function drafts() { return S.linked ? P.drafts.with_suggestion : P.drafts.as_is; }
  function data(key, what) { return launch.getAttribute('data-' + what + '-' + key) || ''; }

  function suggestions() {
    var left = [
      { key: 'model', label: 'Create a semantic model', why: 'The links are checked, so the model can use them.', go: model },
      { key: 'ontology', label: 'Create an ontology', why: 'Give tables and links your business names.', go: ontology },
      { key: 'products', label: 'Draft data products', why: 'Group the tables, with a contract for each.', go: products }
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

  // The result of a step: nothing was created here; what the agent does in the visitor's Fabric, and its status, are
  // tool_status's (data-does-*, data-status-*, data-tool-* on the button).
  function done(key, html) {
    S[key] = true;
    var creates = data(key, 'does') === 'creates';
    var note = 'This is a demo, so nothing was created. ' + (creates
      ? 'Connected to ' + product + ', your agent creates this in your Fabric workspace when you ask.'
      : 'Connected to ' + product + ', your agent drafts this from your own tables when you ask; the draft creates nothing in Fabric.');
    var el = say('builder', 'celebrate', html + '<p class="kgc-note">' + esc(note) + ' Status of ' + code(data(key, 'tool')) + ': ' +
                 esc(data(key, 'status')) + '.</p>', null, 'win');
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
           (m.date_table ? ' and a ' + code(m.date_table) + ' date table' : '') + '.</p>');
    });
  }
  function ontology() {
    work('builder', ['Writing entity types and keys', 'Binding them to the tables'], function () {
      var o = drafts().ontology;
      done('ontology', '<h3>Ontology ready</h3><p>' + plural(o.entity_types, 'entity type') + ' (' + o.with_key + ' with a key) and ' +
           plural(o.relationship_types, 'relationship type') + '. The ontology item is in preview in Fabric.</p>');
    });
  }
  function products() {
    work('thinker', ['Grouping tables by their links', 'Writing the contracts'], function () {
      var d = drafts().domains, n = d.domains.length;
      var out = d.unassigned.filter(function (t) { return P.keyless.indexOf(t) >= 0; });
      done('products', '<h3>' + plural(n, 'data product') + ' drafted</h3><p>' +
           list(d.domains.map(function (x) { return code(x.name); })) +
           (d.interfaces.length ? ', with ' + (d.interfaces.length === 1 ? 'an interface' : d.interfaces.length + ' interfaces') + ' between them' : '') + '. ' +
           (out.length ? list(out.map(code)) + (out.length === 1 ? ' stays out, because it has no key. ' : ' stay out, because they have no key. ') : '') +
           'You choose the owners, and your admin creates the Fabric domains.</p>');
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
      { label: 'Yes, add the link', why: 'The count supports it, and you decide.', rec: true, go: function () {
        S.linked = true;
        cheer(say('builder', 'celebrate', '<h3>Link added</h3><p>The plan now has ' + plural(drafts().relationships, 'link') + '.</p>', null, 'win'));
        next();
      } },
      { label: 'No, leave it out', go: next }
    ], '', true);
  }

  function scan() {
    var n = P.tables.length, r = P.relationships.length, q = P.suggestions.length;
    work('thinker', ['Reading ' + plural(n, 'table'), 'Finding the keys', 'Counting links against the rows'], function () {
      var rels = P.relationships.map(function (x) {
        return '<li>' + code(x.source + '.' + x.source_cols.join('+')) + ' → ' + code(x.target) + '</li>';
      }).join('');
      say('onto', 'point', '<div class="kgc-facts"><div><b>' + n + '</b>tables</div><div><b>' + r + '</b>links found</div>' +
          '<div><b>' + q + '</b>' + (q === 1 ? 'question' : 'questions') + '</div></div><ul class="kgc-links">' + rels + '</ul>');
      later(500, q ? question : next);
    });
  }

  function failed() {
    say('onto', 'explain', '<p>The example did not load here. The check page shows the same example on sample files.</p>',
        [{ label: 'See the check on sample files', href: '/check?example=sample', rec: true }], '', true);
  }

  function begin() {
    S = { linked: false };
    log.innerHTML = '';
    var start = function () {
      say('onto', 'point', '<p>Hi! This is a demo on an example shop. Shall I check how its tables connect?</p>', [
        { label: 'Check the tables', rec: true, go: scan },
        { label: 'See the check on sample files', href: '/check?example=sample' }
      ]);
    };
    if (P) { start(); return; }
    fetch(PLAN_URL, { credentials: 'omit', cache: 'default' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) {
        if (!j || !j.tables || !j.relationships || !j.drafts || !j.suggestions) throw new Error('plan');
        P = j; start();
      })
      .catch(function () { S = null; failed(); });
  }

  function setOpen(open, keepFocus) {
    box.hidden = !open;
    launch.hidden = open;
    launch.setAttribute('aria-expanded', String(open));
    modal(open);
    if (open) {
      if (!S) begin();
      closeBtn.focus({ preventScroll: true });
    } else if (!keepFocus) {
      launch.focus({ preventScroll: true });
    }
  }

  window.KrusgraphChat = {
    open: function (button) {
      if (!box) {
        launch = button;
        product = button.getAttribute('data-product') || product;
        build();
      }
      setOpen(true);
    }
  };
})();
