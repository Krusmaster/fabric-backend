/* AP1: the guided chat at /app (fabric_backend/guided_app.py). Every answer is the start tool's, read with the person's
   own sign-in through POST /app/api/step; this file only draws it: a mascot's bubble per answer, the person's choice as
   their own bubble, the choices as buttons. No model, no free-form reply: a typed name is sent as `text` and matched on
   the server by fixed rules. Text from the server is set with textContent, never as markup. New bubbles are announced
   by the log's aria-live; after a tap the focus moves to the next buttons so the path works from the keyboard.
   AP2 (guided_build.py, POST /app/api/build): Decide as cards (the start tool's own buttons, recorded as taps), the dry
   run of each item with "Show definition" and the exact target, a confirm dialog that lists each item by name before
   Create, Create item by item with its progress and links, and verify_build's result ("Checked by rules, not by AI").
   AP3 (guided_care.py, POST /app/api/care): when the person has built data products, Onto greets with a "Since last
   time" report per product, each section naming its source, and at most three fixes as buttons; a fix that writes
   shows a preview, then a confirm dialog naming the item, and sends the preview's token back. "Update the build in
   place" is AP2's dry run with the product's id. */
(function () {
  'use strict';
  var log = document.getElementById('app-log');
  var input = document.getElementById('app-input');
  var data = document.getElementById('app-lines');
  if (!log || !input || !data) return;
  var LINES = {};
  try { LINES = JSON.parse(data.textContent || '{}'); } catch (e) { LINES = {}; }
  var NAMES = LINES.names || { onto: 'Onto', thinker: 'Thinker', builder: 'Builder' };
  var POSE = { onto: 'point', thinker: 'think', builder: 'explain' };
  var state = {};
  var busy = false;
  var greeted = false;        // AP2b: one greeting: the start tool's own "Hi! ...", else the coach's line before it
  var target = null;          // AP2: where to build ({workspace, lakehouse}); null: the source's workspace
  var update = [];            // AP2: items the person chose to update in place (a dry run first)
  var careProduct = null;     // AP3: the data product an update in place is for (its id, as the server gave it)

  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') n.textContent = attrs[k];
      else if (k === 'cls') n.className = attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }

  function face(who, pose) {
    var f = el('span', { cls: 'app-face', 'aria-hidden': 'true' });
    if (window.Mascots && window.Mascots.svg) f.innerHTML = window.Mascots.svg(who, { pose: pose || POSE[who], label: '', gaze: false });
    return f;
  }

  function scrollDown(node) {
    if (node && node.scrollIntoView) node.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  // A mascot's bubble: the name, then each part (a string becomes a paragraph).
  function say(who, parts, extra) {
    who = NAMES[who] ? who : 'onto';
    var bub = el('div', { cls: 'app-bub' }, [el('span', { cls: 'app-who', text: NAMES[who] })]);
    (parts || []).forEach(function (p) { if (p) bub.appendChild(typeof p === 'string' ? el('p', { text: p }) : p); });
    var li = el('li', { cls: 'app-msg ' + who + (extra ? ' ' + extra : '') }, [face(who), bub]);
    log.appendChild(li);
    scrollDown(li);
    return li;
  }

  function you(text) {
    var li = el('li', { cls: 'app-you', text: text });
    log.appendChild(li);
    return li;
  }

  function clearInput() { input.replaceChildren(); }

  function chip(b, onPick) {
    var label = el('span', { text: b.label });
    var btn = el('button', { type: 'button', cls: 'app-chip' + (b.primary ? ' primary' : '') + (b.selected ? ' suggested' : '') },
      [label, b.hint ? el('small', { text: b.hint }) : null]);
    if (b.disabled) { btn.disabled = true; btn.setAttribute('aria-disabled', 'true'); btn.title = b.disabled; }
    btn.addEventListener('click', function () { onPick(b); });
    return btn;
  }

  // The buttons under the log: one group with a legend, and the box for a typed name where a list is long.
  function offer(legend, buttons, typed) {
    clearInput();
    var set = el('fieldset', { cls: 'app-chips' }, [el('legend', { text: legend })]);
    buttons.forEach(function (b) { set.appendChild(chip(b, pick)); });
    input.appendChild(set);
    if (typed) {
      var id = 'app-type-' + Date.now();
      var box = el('input', { id: id, type: 'text', autocomplete: 'off', spellcheck: 'false', enterkeyhint: 'go' });
      var go = el('button', { type: 'button', cls: 'app-chip', text: 'Use this name' });
      var send = function () {
        var t = box.value.trim();
        if (!t || busy) return;
        input.dataset.focus = '1';
        you(t);
        run(Object.assign({}, typed, { text: t }));
      };
      go.addEventListener('click', send);
      box.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); send(); } });
      input.appendChild(el('div', { cls: 'app-type' }, [el('label', { for: id, text: 'Or type the name (it is matched exactly, then by its beginning)' }), box, go]));
    }
    var first = input.querySelector('button:not([disabled])');
    if (first && input.dataset.focus === '1') first.focus({ preventScroll: true });
  }

  function pick(b) {
    if (busy) return;
    input.dataset.focus = '1';
    you(b.label);
    if (b.act) { b.act(); return; }
    var a = b.arguments || {};
    if (a.step === 'dry_run') { dryRun(); return; }
    run(a);
  }

  function setBusy(on) {
    busy = on;
    input.setAttribute('aria-busy', on ? 'true' : 'false');
    input.querySelectorAll('button, input').forEach(function (b) { if (on) b.disabled = true; });
  }

  function kpis(c) {
    var items = [
      [c.tables, 'tables read', ''],
      [c.links, 'links proposed', ''],
      [(c.hold || 0) + ' of ' + (c.checks || 0), 'checks hold against the rows', c.checks && c.hold === c.checks ? 'ok' : (c.checks ? 'bad' : '')],
      [c.open_decisions, c.open_decisions === 1 ? 'needs you' : 'need you', c.open_decisions ? 'bad' : 'ok'],
      [c.doubled_totals, 'totals would count twice', c.doubled_totals ? 'bad' : 'ok']
    ];
    var ul = el('ul', { cls: 'check-kpis', 'aria-label': 'The check, counted' });
    items.forEach(function (x) {
      if (x[0] === undefined || x[0] === null) return;
      ul.appendChild(el('li', { cls: x[2] }, [el('span', { cls: 'check-kpi-v', text: String(x[0]) }), el('span', { cls: 'check-kpi-l', text: x[1] })]));
    });
    return ul;
  }

  function linksTable(m) {
    var links = (m && m.links) || [];
    var tables = (m && m.tables) || [];
    var d = el('details', null, [el('summary', { text: 'The map: ' + tables.length + ' tables, ' + links.length + ' links' })]);
    var keys = el('table', { cls: 'check-list' }, [el('caption', { text: 'Keys' }),
      el('thead', null, [el('tr', null, [el('th', { scope: 'col', text: 'Table' }), el('th', { scope: 'col', text: 'Key' }), el('th', { scope: 'col', text: 'Rule' })])])]);
    var kb = el('tbody');
    tables.forEach(function (t) { kb.appendChild(el('tr', null, [el('td', { text: t.name }), el('td', { text: (t.key || []).join(' + ') || 'no key' }), el('td', { text: t.rule || '' })])); });
    keys.appendChild(kb);
    var rel = el('table', { cls: 'check-list' }, [el('caption', { text: 'Links, counted against the rows' }),
      el('thead', null, [el('tr', null, ['From', 'To', 'Rule', 'Rows'].map(function (h) { return el('th', { scope: 'col', text: h }); }))])]);
    var rb = el('tbody');
    links.forEach(function (r) {
      var state = r.state === 'passed' ? ['ok', 'holds'] : r.state === 'failed' ? ['bad', (r.orphans || 0) + ' not found'] : ['', 'not counted'];
      rb.appendChild(el('tr', null, [
        el('td', { text: r.source + '.' + (r.source_cols || []).join('+') }),
        el('td', { text: r.target + '.' + (r.target_cols || []).join('+') }),
        el('td', { text: r.rule || '' }),
        el('td', { cls: state[0], text: state[1] })]));
    });
    rel.appendChild(rb);
    d.appendChild(el('div', { cls: 'app-table' }, [keys]));
    d.appendChild(el('div', { cls: 'app-table' }, [rel]));
    return d;
  }

  function show(v, sent) {
    if (!greeted) {
      greeted = true;
      if (!/^Hi\b/.test(v.say || '')) say('onto', [LINES.hello]);
    }
    if (v.error) {
      say('thinker', [LINES.error || 'That did not work.', v.error, v.hint || ''], 'error');
      offer('What now?', [{ label: 'Try again', arguments: sent }, { label: 'Start over', arguments: {} }]);
      return;
    }
    state = Object.assign({}, v.chosen || {});
    if (v.match) {
      say('onto', [v.match.say]);
    } else if (v.stage === 'check') {
      var parts = [LINES.check, el('p', { cls: 'app-line', text: v.say })];
      if (v.counts) parts.push(kpis(v.counts));
      if (v.lines && v.lines.length) parts.push(el('ul', null, v.lines.map(function (x) { return el('li', { text: x }); })));
      if (v.review_error) parts.push(v.review_error);
      if (v.map) parts.push(linksTable(v.map));
      if (v.rules && v.rules.length) parts.push(el('details', null, [el('summary', { text: 'The rules behind the links' }),
        el('ul', null, v.rules.map(function (x) { return el('li', { text: x }); }))]));
      say('thinker', parts);
      say('builder', [v.next || LINES.next, v.closing || LINES.nothing]);
      offer('What now?', (v.buttons || []).concat([{ label: 'Check another schema', arguments: { workspace: state.workspace, source: state.source, step: 'schema' } },
        { label: 'Start over', arguments: { step: 'workspace' } }]));
      return;
    } else if (v.stage === 'decide') {
      showDecide(v);
      return;
    } else {
      var p = [v.say];
      if (v.line) p.push(el('p', { cls: 'app-line', text: v.line }));
      if (v.own_line) p.push(el('p', { cls: 'muted', text: v.own_line }));
      if (v.choices_error) p.push(v.choices_error);
      say(v.who, p);
    }
    var buttons = ((v.match && v.match.go) || []).concat(v.choices || [], v.buttons || []);
    if (!buttons.length) buttons = [{ label: 'Start over', arguments: { step: 'workspace' } }];
    var legend = v.stage === 'workspace' ? 'Choose a workspace' : v.stage === 'source' ? 'Choose a source' :
      v.stage === 'schema' ? 'Choose a schema' : 'Your answer';
    var typed = (v.choices && v.choices.length) ? Object.assign({}, state, { step: v.stage }) : null;
    offer(legend, buttons, typed);
  }

  // ---------------------------------------------------------------- AP2: Decide ----------------------------------
  function badge(text, cls) { return el('span', { cls: 'app-badge' + (cls ? ' ' + cls : ''), text: text }); }

  function decisionCard(d) {
    var sec = el('section', { cls: 'app-dec' + (d.decided ? ' decided' : ''), 'aria-label': d.question });
    sec.appendChild(el('p', { cls: 'app-dec-q', text: d.question }));
    if (d.rule) sec.appendChild(el('p', { cls: 'muted tiny', text: 'Proposed by the rule ' + d.rule + (d.rule_words ? ': ' + d.rule_words : '') + '.' }));
    if (d.evidence && d.evidence.length) sec.appendChild(el('ul', null, d.evidence.map(function (x) { return el('li', { text: x }); })));
    if (d.decided) sec.appendChild(badge(d.decided, 'mine'));
    var opts = el('div', { cls: 'app-dec-opts', role: 'group', 'aria-label': 'Your answer' });
    (d.options || []).forEach(function (o) {
      var btn = el('button', { type: 'button', cls: 'app-chip' + (o.selected ? ' suggested' : '') }, [el('span', { text: o.label }), el('small', { text: o.words })]);
      if (o.selected) { btn.setAttribute('aria-pressed', 'true'); btn.disabled = true; }
      btn.addEventListener('click', function () {
        if (busy) return;
        input.dataset.focus = '1';
        you(o.label + ': ' + (d.what || d.item) + '.');
        run({ workspace: state.workspace, source: state.source, schema: state.schema, step: 'decide', decide: { item: d.item, review: o.review } });
      });
      opts.appendChild(btn);
    });
    sec.appendChild(opts);
    return sec;
  }

  function showDecide(v) {
    var parts = [LINES.decide || '', el('p', { cls: 'app-line', text: v.say })];
    (v.decisions || []).forEach(function (d) { parts.push(decisionCard(d)); });
    if (v.decided && v.decided.length) parts.push(el('ul', { cls: 'app-decided' }, v.decided.map(function (x) { return el('li', { text: x }); })));
    if (v.review_error) parts.push(v.review_error);
    say('thinker', parts);
    var buttons = (v.buttons || []).map(function (b) { return Object.assign({}, b, { hint: b.why || '' }); });
    buttons.push({ label: 'Back to the check', arguments: { workspace: state.workspace, source: state.source, schema: state.schema, step: 'check' } });
    offer('What now?', buttons);
    if (!(v.decisions || []).length || !v.open) return;
    var first = log.querySelector('li:last-child .app-dec-opts button:not([disabled])');
    if (first && input.dataset.focus === '1') first.focus({ preventScroll: true });
  }

  // ---------------------------------------------------------------- AP2: the build API -----------------------------
  function api(body) {
    return fetch('/app/api/build', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    }).then(function (r) {
      if (r.status === 401) { window.location.assign('/app/login'); return new Promise(function () {}); }
      return r.json().catch(function () { return { error: 'The answer could not be read.' }; });
    }).catch(function () { return { error: 'Krusgraph could not be reached.' }; });
  }

  function failed(v, again) {
    say('thinker', [LINES.error || 'That did not work.', v.error, v.hint || ''], 'error');
    offer('What now?', [{ label: 'Try again', act: again }, { label: 'Back to Decide', arguments: { workspace: state.workspace, source: state.source, schema: state.schema, step: 'decide' } }]);
  }

  // ---------------------------------------------------------------- AP2: the dry run -------------------------------
  function dryRun() {
    var reading = say('builder', [el('p', { cls: 'app-busy', text: 'Preparing the dry run of each item' })]);
    setBusy(true);
    var body = { action: 'dry_run', workspace: state.workspace, source: state.source, schema: state.schema, update: update };
    if (target) body.target = target;
    if (careProduct) body.product = careProduct;
    api(body).then(function (v) {
      reading.querySelector('.app-busy').classList.remove('app-busy');
      setBusy(false);
      if (v.error) { failed(v, dryRun); return; }
      showDry(v);
    });
  }

  function itemRow(x) {
    var li = el('li', { cls: 'app-item a-' + x.action });
    li.appendChild(el('div', { cls: 'app-item-h' }, [el('strong', { text: x.name }), el('span', { cls: 'muted', text: x.label }), badge(x.badge, x.action)]));
    if (x.words) li.appendChild(el('p', { text: x.words }));
    if (x.consent) {
      li.appendChild(el('p', { cls: 'warn', text: [x.consent.error, x.consent.hint].filter(Boolean).join(' ') }));
      if (x.consent.steps) li.appendChild(el('ol', null, x.consent.steps.map(function (s) { return el('li', { text: s }); })));
    }
    if (x.definition) {
      li.appendChild(el('details', null, [el('summary', { text: 'Show definition' }), el('pre', { cls: 'app-def', tabindex: '0', text: x.definition })]));
    }
    if (x.created && x.created.length) {
      li.appendChild(el('ul', { cls: 'app-links', 'aria-label': 'Open in Fabric' }, x.created.map(function (c) {
        return el('li', null, [el('a', { href: c.url, target: '_blank', rel: 'noopener noreferrer', text: 'Open ' + c.name + ' in Fabric' })]);
      })));
    }
    if (x.steps && x.steps.length) {
      li.appendChild(el('details', null, [el('summary', { text: 'Left to do in Fabric' }), el('ol', null, x.steps.map(function (s) { return el('li', { text: s }); }))]));
    }
    return li;
  }

  var lastDry = null;
  function showDry(v) {
    lastDry = v;
    var t = v.target || {};
    var parts = [LINES.build || '', el('p', { cls: 'app-line', text: v.say })];
    parts.push(el('p', null, [el('span', { cls: 'muted', text: 'Builds in: ' }), el('strong', { cls: 'app-target', text: t.line || '' })]));
    if (t.words && t.words.length) parts.push(el('details', null, [el('summary', { text: 'Where exactly, and why' }), el('ul', null, t.words.map(function (x) { return el('li', { text: x }); }))]));
    parts.push(el('ul', { cls: 'app-items', 'aria-label': 'What the dry run would write' }, (v.items || []).map(itemRow)));
    if (v.decided && v.decided.length) parts.push(el('ul', { cls: 'app-decided', 'aria-label': 'Decided by you' }, v.decided.map(function (x) { return el('li', { text: 'Decided by you: ' + x }); })));
    if (v.left_out && v.left_out.length) parts.push('Left out by your decisions: ' + v.left_out.join('; ') + '.');
    if (v.access) parts.push(el('p', { cls: 'muted tiny', text: v.access }));
    parts.push(el('p', { cls: 'muted', text: LINES.dry_run || v.note }));
    say('builder', parts);
    var buttons = [];
    var n = (v.creates || []).length;
    if (n) buttons.push({ label: 'Create ' + (n === 1 ? 'this item' : 'these ' + n + ' items') + '…', primary: true, act: function () { askConfirm(v); } });
    (v.items || []).forEach(function (x) {
      if (x.action === 'choose') buttons.push({ label: 'Update ' + x.name + ' in place', hint: 'A dry run first', act: function () { if (update.indexOf(x.kind) < 0) update.push(x.kind); dryRun(); } });
    });
    buttons.push({ label: 'Change where to build', act: places });
    buttons.push({ label: 'Back to Decide', arguments: { workspace: state.workspace, source: state.source, schema: state.schema, step: 'decide' } });
    offer('What now?', buttons);
  }

  // ---------------------------------------------------------------- AP2: where to build ----------------------------
  function places() {
    setBusy(true);
    api({ action: 'places' }).then(function (v) {
      setBusy(false);
      if (v.error) { failed(v, places); return; }
      say('onto', ['Where shall I build? The source stays where it is; the build can go to another workspace.']);
      offer('Choose the build workspace', (v.workspaces || []).map(function (w) {
        var mine = w.name === state.workspace;
        return { label: w.name, hint: mine ? 'the source\'s workspace: builds into ' + state.source : '', act: function () {
          if (mine) { target = null; update = []; dryRun(); } else { lakehouses(w); }
        } };
      }));
    });
  }

  function lakehouses(w) {
    setBusy(true);
    api({ action: 'lakehouses', workspace: w.id }).then(function (v) {
      setBusy(false);
      if (v.error) { failed(v, function () { lakehouses(w); }); return; }
      say('onto', ['Which lakehouse in ' + w.name + ' gets the silver tables and the gold views?']);
      var b = (v.lakehouses || []).map(function (name) {
        return { label: name, act: function () { target = { workspace: w.id, lakehouse: name }; update = []; dryRun(); } };
      });
      b.push({ label: 'Let Krusgraph choose', hint: 'the first lakehouse by name, or one it makes (the dry run says which)', act: function () { target = { workspace: w.id }; update = []; dryRun(); } });
      offer('Choose the lakehouse', b);
    });
  }

  // ---------------------------------------------------------------- AP2: confirm, then Create ------------------------
  var dialog = null;
  function askConfirm(v) {
    var opener = document.activeElement;
    if (dialog) dialog.remove();
    var items = v.creates || [];
    var badges = {};
    (v.items || []).forEach(function (x) { badges[x.name] = x.badge; });
    var h = el('h2', { id: 'app-confirm-h', tabindex: '-1', text: 'Create ' + (items.length === 1 ? 'this item' : 'these ' + items.length + ' items') + ' in Fabric?' });
    var cancel = el('button', { type: 'button', cls: 'app-chip', text: 'Cancel' });
    var go = el('button', { type: 'button', cls: 'app-chip primary', text: 'Yes, create them' });
    dialog = el('dialog', { cls: 'app-dialog', 'aria-labelledby': 'app-confirm-h', 'aria-describedby': 'app-confirm-d' }, [
      h,
      el('p', { id: 'app-confirm-d', text: 'In ' + ((v.target || {}).line || '') + ', as you, with your own Microsoft sign-in. Krusgraph writes only these, in this order, and deletes nothing.' }),
      el('ol', { cls: 'app-confirm-list' }, items.map(function (x) {
        return el('li', null, [el('strong', { text: x.name }), ' ', el('span', { cls: 'muted', text: x.label }), ' ', badge(badges[x.name] || '', '')]);
      })),
      el('div', { cls: 'app-dialog-b' }, [cancel, go])
    ]);
    document.body.appendChild(dialog);
    function close() { dialog.close(); if (opener && opener.focus) opener.focus(); }
    cancel.addEventListener('click', function () { close(); you('Not now'); offer('What now?', [{ label: 'Create these items…', primary: true, act: function () { askConfirm(v); } }, { label: 'Back to Decide', arguments: { workspace: state.workspace, source: state.source, schema: state.schema, step: 'decide' } }]); });
    dialog.addEventListener('cancel', function () { setTimeout(function () { if (opener && opener.focus) opener.focus(); }, 0); });
    go.addEventListener('click', function () { dialog.close(); input.dataset.focus = '1'; you('Yes, create ' + items.map(function (x) { return x.name; }).join(', ')); create(v, items); });
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
    h.focus();
  }

  function create(v, items) {
    setBusy(true);
    api({ action: 'confirm', token: v.token, names: items.map(function (x) { return x.name; }) }).then(function (got) {
      if (got.error) { setBusy(false); failed(got, dryRun); return; }
      var rows = {};
      var status = el('p', { cls: 'app-status', role: 'status', text: 'Starting.' });
      var list = el('ol', { cls: 'app-items' }, got.items.map(function (x) {
        rows[x.kind] = el('li', { cls: 'app-item a-wait' }, [el('div', { cls: 'app-item-h' }, [el('strong', { text: x.name }), el('span', { cls: 'muted', text: x.label }), badge('Waiting', 'wait')])]);
        return rows[x.kind];
      }));
      say('builder', ['Creating, one item after the other, as you.', status, list]);
      var results = [];
      var i = 0;
      function next() {
        if (i >= got.items.length) { status.textContent = 'Done: ' + got.items.length + ' of ' + got.items.length + ' sent.'; done(results); return; }
        var x = got.items[i];
        status.textContent = (i + 1) + ' of ' + got.items.length + ': creating ' + x.label.toLowerCase() + ' ' + x.name + '…';
        rows[x.kind].replaceChildren(el('div', { cls: 'app-item-h' }, [el('strong', { text: x.name }), el('span', { cls: 'muted', text: x.label }), badge('Creating…', 'busy')]));
        api({ action: 'create', run: got.run, kind: x.kind }).then(function (op) {
          if (op.error) { finish(x, { kind: x.kind, name: x.name, label: x.label, action: 'error', badge: 'Not written', words: [op.error, op.hint].filter(Boolean).join(' ') }); return; }
          poll(x, op.operation_id);
        });
      }
      function poll(x, id) {
        setTimeout(function () {
          api({ action: 'state', operation_id: id }).then(function (s) {
            if (s.error && s.kind !== 'rate_limited') { finish(x, { kind: x.kind, name: x.name, label: x.label, action: 'error', badge: 'Not known', words: s.error }); return; }
            if (s.status === 'done' && s.item) { finish(x, Object.assign({ name: x.name, label: x.label }, s.item)); return; }
            if (s.status === 'lost') { finish(x, { kind: x.kind, name: x.name, label: x.label, action: 'started', badge: 'Started', words: s.words || '' }); return; }
            if (s.words) status.textContent = (i + 1) + ' of ' + got.items.length + ': ' + s.words;
            poll(x, id);
          });
        }, 1500);
      }
      function finish(x, card) {
        results.push(card);
        rows[x.kind].replaceWith(rows[x.kind] = itemRow(card));
        i += 1;
        next();
      }
      next();
    });
  }

  function done(results) {
    var made = results.filter(function (r) { return r.action === 'create' || r.action === 'update' || r.action === 'skip'; }).length;
    say('builder', [made + ' of ' + results.length + ' item' + (results.length === 1 ? '' : 's') + ' in Fabric. ' + (made ? 'Now I check what was built against the dry run.' : '')]);
    if (!made) { setBusy(false); offer('What now?', [{ label: 'Dry run again', act: dryRun }, { label: 'Start over', arguments: { step: 'workspace' } }]); return; }
    verify();
  }

  // ---------------------------------------------------------------- AP2: verify_build ------------------------------
  function verify() {
    var reading = say('thinker', [el('p', { cls: 'app-busy', text: 'Reading back what was built' })]);
    setBusy(true);
    api({ action: 'verify' }).then(function (v) {
      reading.querySelector('.app-busy').classList.remove('app-busy');
      setBusy(false);
      if (v.error) { failed(v, verify); return; }
      var c = v.counts || {};
      var tiles = el('ul', { cls: 'check-kpis', 'aria-label': 'What was built, checked' }, [
        [c.items, 'items read back', ''], [c.verified, 'match the dry run', 'ok'], [c.differs, 'differ', c.differs ? 'bad' : 'ok'], [c.not_checked, 'not checked', '']
      ].filter(function (x) { return x[0] !== undefined && x[0] !== null; }).map(function (x) {
        return el('li', { cls: x[2] }, [el('span', { cls: 'check-kpi-v', text: String(x[0]) }), el('span', { cls: 'check-kpi-l', text: x[1] })]);
      }));
      var parts = [el('h3', { cls: 'app-verify-h', text: v.title }), el('p', { text: v.summary }), tiles];
      if (v.lines && v.lines.length) {
        parts.push(el('details', null, [el('summary', { text: 'Item by item' }), el('ul', null, v.lines.map(function (x) {
          return el('li', null, [el('strong', { text: x.item || '' }), ' ', el('span', { text: [x.state, x.said].filter(Boolean).join(': ') })].concat(
            (x.figures || []).length ? [el('ul', null, x.figures.map(function (f) { return el('li', { text: f }); }))] : []));
        }))]));
      }
      if (v.next_steps && v.next_steps.length) {
        parts.push(el('p', { cls: 'app-line', text: 'Next steps' }));
        parts.push(el('ol', null, v.next_steps.map(function (s) { return el('li', null, [el('strong', { text: s.label || '' }), s.why ? ' ' + s.why : '']); })));
      }
      parts.push(el('p', { cls: 'muted', text: v.note }));
      say('thinker', parts, 'verify');
      var next = [{ label: 'Dry run again', act: dryRun }, { label: 'Start over', arguments: { step: 'workspace' } }];
      // AP3b: the proposed refresh only refreshes: the caretaker's preview, confirm dialog naming the model, one token
      if (v.refresh && v.refresh.product) next.unshift({ label: v.refresh.label, hint: 'A preview first', primary: true,
        act: function () { careDo({ product: { id: v.refresh.product } }, { act: 'refresh_model', label: v.refresh.label }); } });
      offer('What now?', next);
    });
  }

  // ---------------------------------------------------------------- AP3: the caretaker -----------------------------
  // AP3b: no fetch waits forever. A report has a budget of 40 s on the server (guided_care.CARE_SECONDS); the page
  // waits a little longer and then says so; every other care call gets CARE_WAIT_MS.
  var REPORT_WAIT_MS = 50000;
  var CARE_WAIT_MS = 90000;
  function careApi(body, waitMs) {
    var ms = waitMs || CARE_WAIT_MS;
    var ctl = window.AbortController ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, ms) : null;
    return fetch('/app/api/care', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      signal: ctl ? ctl.signal : undefined
    }).then(function (r) {
      if (timer) clearTimeout(timer);
      if (r.status === 401) { window.location.assign('/app/login'); return new Promise(function () {}); }
      return r.json().catch(function () { return { error: 'The answer could not be read.' }; });
    }).catch(function (e) {
      if (timer) clearTimeout(timer);
      if (e && e.name === 'AbortError') {
        return { error: 'Krusgraph did not answer within ' + Math.round(ms / 1000) + ' seconds, so the page stopped waiting. Nothing was changed.',
          kind: 'timeout', hint: 'Read it again in a moment.' };
      }
      return { error: 'Krusgraph could not be reached.' };
    });
  }

  var STATE_WORD = { ok: 'Fine', warn: 'Worth a look', bad: 'Needs a look', none: 'Nothing yet', unknown: 'Not read' };
  var care = { reports: [] };

  function careSection(x, again) {
    var sec = el('section', { cls: 'care-sec s-' + x.state, 'aria-label': x.title });
    sec.appendChild(el('div', { cls: 'care-sec-h' }, [el('h4', { text: x.title }), badge(STATE_WORD[x.state] || x.state, 'care-' + x.state)]));
    sec.appendChild(el('p', { cls: 'care-src muted tiny', text: (x.title_note ? x.title_note + ', ' : '') + x.source + '.' }));
    if ((x.lines || []).length) sec.appendChild(el('ul', null, x.lines.map(function (t) { return el('li', { text: t }); })));
    if (x.link) sec.appendChild(el('a', { href: x.link, target: '_blank', rel: 'noopener noreferrer', text: 'Open in Fabric' }));
    if (x.again && again) {
      var b = el('button', { type: 'button', cls: 'app-chip care-again', text: 'Read again' });
      b.addEventListener('click', function () { if (!busy) again(); });
      sec.appendChild(b);
    }
    return sec;
  }

  function careReport(v, again) {
    var p = v.product || {};
    var card = el('article', { cls: 'care-card', 'aria-label': 'Since last time: ' + (p.name || '') }, [
      el('h3', { cls: 'care-name', text: p.name || '' }),
      el('p', { cls: 'muted tiny', text: 'From ' + (p.from || '') + '. Source: ' + (p.source || '') + '.' }),
      el('p', { cls: 'app-line', text: v.say || '' })
    ]);
    (v.sections || []).forEach(function (x) { card.appendChild(careSection(x, again)); });
    if ((v.actions || []).length) {
      card.appendChild(el('p', { cls: 'app-line', text: 'What I propose, by rules' }));
      card.appendChild(el('ol', { cls: 'care-acts' }, v.actions.map(function (a) {
        return el('li', null, [el('strong', { text: a.label }), ' ', el('span', { text: a.why })]);
      })));
    }
    card.appendChild(el('p', { cls: 'muted tiny', text: v.note || '' }));
    return card;
  }

  function careStart() {
    careApi({ action: 'products' }).then(function (v) {
      var list = (v && v.products) || [];
      if (v.error || !list.length) { run({}); return; }   // AP2b: show() greets once, unless the start tool already does
      say('onto', [LINES.since || 'Since last time.']);
      care.reports = list.map(function () { return null; });
      careAll(list);
    });
  }

  // AP3b: the products are read two at a time (each report reads its four parts at once on the server)
  var CARE_PARALLEL = 2;
  function careAll(list) {
    var next = 0, left = list.length;
    setBusy(true);
    function one() {
      if (next >= list.length) return;
      var i = next++;
      careRead(list[i], null, function (v) {
        care.reports[i] = v;
        left -= 1;
        if (left === 0) { setBusy(false); care.reports = care.reports.filter(Boolean); careOffer(); } else one();
      });
    }
    for (var k = 0; k < Math.min(CARE_PARALLEL, list.length); k++) one();
  }

  // One product's report: a busy line that names the parts still being read, with a tick for each part done.
  function careRead(p, li, done) {
    var line = el('p', { cls: 'app-busy', text: 'Reading ' + p.name });
    var parts = el('ul', { cls: 'care-parts', 'aria-label': 'Parts of the report' });
    var holder = el('div', { cls: 'care-reading' }, [line, parts]);
    if (li) li.querySelector('.app-bub').replaceChildren(el('span', { cls: 'app-who', text: NAMES.onto }), holder);
    else li = say('onto', [holder]);
    var finished = false;
    function draw(ps) {
      var todo = ps.filter(function (x) { return !x.done; }).map(function (x) { return x.part; });
      line.textContent = 'Reading ' + p.name + (todo.length ? ': ' + todo.join(', ') : '');
      parts.replaceChildren.apply(parts, ps.map(function (x) {
        return el('li', { cls: x.done ? 'done' : '' }, [el('span', { 'aria-hidden': 'true', text: x.done ? '\u2713 ' : '\u2026 ' }),
          x.part + (x.done ? ' (read)' : '')]);
      }));
    }
    draw([{ part: 'pipeline runs' }, { part: 'the health check' }, { part: 'verify_build' }, { part: 'the source' }]);
    function poll() {
      if (finished) return;
      careApi({ action: 'progress', product: p.id }, 8000).then(function (g) {
        if (finished) return;
        if (g && g.parts) draw(g.parts);
        setTimeout(poll, 1500);
      });
    }
    setTimeout(poll, 1000);
    careApi({ action: 'report', product: p.id }, REPORT_WAIT_MS).then(function (v) {
      finished = true;
      var bub = li.querySelector('.app-bub');
      if (v.error) {
        bub.replaceChildren(el('span', { cls: 'app-who', text: NAMES.onto }),
          el('p', { text: p.name + ': ' + v.error + (v.hint ? ' ' + v.hint : '') }), againButton(p, li));
        done(null);
        return;
      }
      bub.replaceChildren(el('span', { cls: 'app-who', text: NAMES.onto }), careReport(v, function () { careAgain(p, li); }));
      done(v);
    });
  }

  function againButton(p, li) {
    var b = el('button', { type: 'button', cls: 'app-chip care-again', text: 'Read again' });
    b.addEventListener('click', function () { if (!busy) careAgain(p, li); });
    return b;
  }

  // "Read again": this one product once more, in its own bubble; the others stay as they are.
  function careAgain(p, li) {
    setBusy(true);
    careRead(p, li, function (v) {
      setBusy(false);
      var pid = (p && p.id) || '';
      var kept = care.reports.filter(function (r) { return r && r.product && r.product.id !== pid; });
      if (v) kept.push(v);
      care.reports = kept;
      careOffer();
    });
  }

  function careOffer() {
    var many = care.reports.length > 1;
    var buttons = [];
    care.reports.forEach(function (v) {
      (v.actions || []).forEach(function (a) {
        buttons.push({ label: a.label + (many ? ' (' + v.product.name + ')' : ''), hint: a.writes ? 'A preview first' : 'Reads only',
          primary: !buttons.length, act: function () { careDo(v, a); } });
      });
    });
    if (care.reports.length) buttons.push({ label: 'Read the report again', act: function () { careStart(); } });
    buttons.push({ label: 'Start something new', act: function () { say('onto', [LINES.fresh || LINES.hello]); run({}); } });
    offer('What now?', buttons);
  }

  function careDo(v, a) {
    var pid = v.product.id;
    if (a.act === 'update_build') {
      var b = a.build || {};
      state = { workspace: b.workspace, source: b.source, schema: b.schema };
      target = b.target || null;
      update = (b.update || []).slice();
      careProduct = b.product || pid;
      dryRun();
      return;
    }
    if (a.act === 'run_manual') {
      var parts = [a.why];
      if ((a.steps || []).length) parts.push(el('ol', null, a.steps.map(function (t) { return el('li', { text: t }); })));
      if (a.link) parts.push(el('a', { href: a.link, target: '_blank', rel: 'noopener noreferrer', text: 'Open ' + a.item + ' in Fabric' }));
      say('onto', parts);
      careOffer();
      return;
    }
    if (a.act === 'recheck_links') {
      var reading = say('thinker', [el('p', { cls: 'app-busy', text: 'Counting the keys and links against the rows again' })]);
      setBusy(true);
      careApi({ action: 'recheck', product: pid }).then(function (r) {
        reading.querySelector('.app-busy').classList.remove('app-busy');
        setBusy(false);
        if (r.error) { say('thinker', [LINES.error || 'That did not work.', r.error, r.hint || ''], 'error'); careOffer(); return; }
        say('thinker', [el('h3', { cls: 'app-verify-h', text: r.title }),
          el('ul', null, (r.lines || []).map(function (t) { return el('li', { text: t }); })), el('p', { cls: 'muted', text: r.note })], 'verify');
        careOffer();
      });
      return;
    }
    setBusy(true);
    careApi({ action: 'preview', product: pid, act: a.act }).then(function (pv) {
      setBusy(false);
      if (pv.error) { say('thinker', [LINES.error || 'That did not work.', pv.error, pv.hint || ''], 'error'); careOffer(); return; }
      say('builder', [el('p', { cls: 'app-line', text: pv.label + ': ' + pv.item }), pv.say, el('p', { cls: 'muted', text: pv.note })]);
      offer('What now?', [{ label: pv.label + '…', primary: true, act: function () { careConfirm(pv); } },
        { label: 'Not now', act: careOffer }]);
    });
  }

  function careConfirm(pv) {
    var opener = document.activeElement;
    if (dialog) dialog.remove();
    var h = el('h2', { id: 'app-confirm-h', tabindex: '-1', text: pv.label + '?' });
    var cancel = el('button', { type: 'button', cls: 'app-chip', text: 'Cancel' });
    var go = el('button', { type: 'button', cls: 'app-chip primary', text: 'Yes, ' + pv.label.charAt(0).toLowerCase() + pv.label.slice(1) });
    dialog = el('dialog', { cls: 'app-dialog', 'aria-labelledby': 'app-confirm-h', 'aria-describedby': 'app-confirm-d' }, [
      h, el('p', { id: 'app-confirm-d', text: pv.say + ' Only this, once; nothing is deleted.' }),
      el('ol', { cls: 'app-confirm-list' }, [el('li', null, [el('strong', { text: pv.item })])]),
      el('div', { cls: 'app-dialog-b' }, [cancel, go])
    ]);
    document.body.appendChild(dialog);
    function close() { dialog.close(); if (opener && opener.focus) opener.focus(); }
    cancel.addEventListener('click', function () { close(); you('Not now'); careOffer(); });
    dialog.addEventListener('cancel', function () { setTimeout(function () { if (opener && opener.focus) opener.focus(); }, 0); });
    go.addEventListener('click', function () {
      dialog.close(); input.dataset.focus = '1'; you('Yes, ' + pv.label.toLowerCase() + ': ' + pv.item);
      var status = el('p', { cls: 'app-status', role: 'status', text: 'Sending.' });
      say('builder', [status]);
      setBusy(true);
      careApi({ action: 'confirm', token: pv.token, names: [pv.item] }).then(function (got) {
        if (got.error) { setBusy(false); say('thinker', [LINES.error || 'That did not work.', got.error, got.hint || ''], 'error'); careOffer(); return; }
        if (got.operation_id) { carePoll(got, status); return; }
        setBusy(false);
        status.textContent = got.words || 'Sent.';
        if (got.link) status.parentNode.appendChild(el('a', { href: got.link, target: '_blank', rel: 'noopener noreferrer', text: 'Follow the run in Fabric' }));
        careOffer();
      });
    });
    if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
    h.focus();
  }

  function carePoll(got, status) {
    status.textContent = got.item + ': refreshing once…';
    setTimeout(function () {
      careApi({ action: 'state', operation_id: got.operation_id }).then(function (s) {
        if (s.error && s.kind !== 'rate_limited') { setBusy(false); status.textContent = s.error; careOffer(); return; }
        if (s.status === 'done' || s.status === 'lost') { setBusy(false); status.textContent = got.item + ': ' + (s.words || s.status); careOffer(); return; }
        carePoll(got, status);
      });
    }, 1500);
  }

  function run(args) {
    careProduct = null;
    var reading = null;
    if (args.step === 'check' || args.decide) reading = say('thinker', [el('p', { cls: 'app-busy', text: args.decide ? 'Recording your decision and counting again' : LINES.read })]);
    setBusy(true);
    fetch('/app/api/step', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(args)
    }).then(function (r) {
      if (r.status === 401) { window.location.assign('/app/login'); return null; }
      return r.json().catch(function () { return { error: 'The answer could not be read.' }; });
    }).then(function (v) {
      if (!v) return;
      if (reading) reading.querySelector('.app-busy').classList.remove('app-busy');
      setBusy(false);
      show(v, args);
    }).catch(function () {
      setBusy(false);
      show({ error: 'Krusgraph could not be reached.' }, args);
    });
  }

  // mascots.js is deferred after this file: start once every deferred script has run, so the first bubble has its figure
  var begun = false;
  function begin() { if (begun) return; begun = true; careStart(); }
  if (window.Mascots || document.readyState === 'complete') begin();
  else { document.addEventListener('DOMContentLoaded', begin); window.addEventListener('load', begin); }
})();
