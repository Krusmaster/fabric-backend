/* AP1: the guided chat at /app (fabric_backend/guided_app.py). Every answer is the start tool's, read with the person's
   own sign-in through POST /app/api/step; this file only draws it: a mascot's bubble per answer, the person's choice as
   their own bubble, the choices as buttons. No model, no free-form reply: a typed name is sent as `text` and matched on
   the server by fixed rules. Text from the server is set with textContent, never as markup. New bubbles are announced
   by the log's aria-live; after a tap the focus moves to the next buttons so the path works from the keyboard. */
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
    run(b.arguments || {});
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
    tables.forEach(function (t) { kb.appendChild(el('tr', null, [el('td', { text: t.name }), el('td', { text: (t.key || []).join(' + ') }), el('td', { text: t.rule || '' })])); });
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
      say('builder', [v.next || LINES.next, LINES.nothing]);
      offer('What now?', [{ label: 'Check another schema', arguments: { workspace: state.workspace, source: state.source, step: 'schema' } },
        { label: 'Start over', arguments: { step: 'workspace' } }]);
      return;
    } else {
      var p = [v.say];
      if (v.line) p.push(el('p', { cls: 'app-line', text: v.line }));
      if (v.choices_error) p.push(v.choices_error);
      say(v.who, p);
    }
    var buttons = (v.choices || []).concat(v.buttons || []);
    if (!buttons.length) buttons = [{ label: 'Start over', arguments: { step: 'workspace' } }];
    var legend = v.stage === 'workspace' ? 'Choose a workspace' : v.stage === 'source' ? 'Choose a source' :
      v.stage === 'schema' ? 'Choose a schema' : 'Your answer';
    var typed = (v.choices && v.choices.length) ? Object.assign({}, state, { step: v.stage }) : null;
    offer(legend, buttons, typed);
  }

  function run(args) {
    var reading = null;
    if (args.step === 'check') reading = say('thinker', [el('p', { cls: 'app-busy', text: LINES.read })]);
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
  function begin() { if (begun) return; begun = true; say('onto', [LINES.hello]); run({}); }
  if (window.Mascots || document.readyState === 'complete') begin();
  else { document.addEventListener('DOMContentLoaded', begin); window.addEventListener('load', begin); }
})();
