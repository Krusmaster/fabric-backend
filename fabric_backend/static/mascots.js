/* Krusgraph mascots — three soft stones, drawn as layered inline SVG.
   Layers per figure: shadow, body (with matte shade), arms, eyes. Poses are data-pose attributes styled in site.css;
   the body shapes and the small behaviours (gaze, follower, builder sequence) live here.
   Respects prefers-reduced-motion (stills) and a visible off switch stored in localStorage (try/catch). */
(function () {
  'use strict';
  var KINDS = {
    onto: { // the guide: upright, leaning forward. Taller bean.
      fill: '#F2735C', dark: '#D9573F', light: '#FFA48F', name: 'Onto, the coral guide',
      body: 'M60 12 C84 12 97 36 95 64 C93 92 79 110 58 110 C36 110 23 92 25 64 C27 36 38 12 60 12 Z',
      shade: 'M30 76 C36 100 50 110 60 110 C78 110 92 96 95 70 C88 92 76 100 60 100 C46 100 36 90 30 76 Z',
      eyes: [[50, 50], [69, 48]], armL: 'M38 70 Q24 76 22 90', armR: 'M86 66 Q98 72 100 86', shadow: [60, 110, 27, 5]
    },
    thinker: { // the thinker: wider, settled.
      fill: '#9DB8A0', dark: '#7E9C82', light: '#C5DAC7', name: 'The thinker, the sage one',
      body: 'M60 26 C92 24 110 46 108 72 C106 98 86 110 60 110 C34 110 12 98 12 72 C12 46 30 24 60 26 Z',
      shade: 'M16 82 C26 102 44 110 60 110 C80 110 98 100 106 80 C94 96 78 102 60 102 C42 102 26 96 16 82 Z',
      eyes: [[48, 58], [72, 58]], armL: 'M26 80 Q14 86 12 98', armR: 'M94 80 Q106 86 108 98', shadow: [60, 111, 34, 5]
    },
    builder: { // the maker: slightly tapered, tilted.
      fill: '#A99AD8', dark: '#8C7CC4', light: '#CDC3EC', name: 'The builder, the lavender one',
      body: 'M60 16 C78 16 88 34 91 60 C95 90 80 110 58 110 C34 110 23 90 27 60 C30 34 42 16 60 16 Z',
      shade: 'M30 80 C38 102 48 110 58 110 C78 110 90 96 91 72 C84 92 74 100 60 100 C46 100 36 92 30 80 Z',
      eyes: [[51, 50], [69, 50]], armL: 'M36 74 Q24 80 22 92', armR: 'M86 72 Q98 78 100 90', shadow: [60, 110, 26, 5]
    }
  };

  function svg(kind, opts) {
    opts = opts || {};
    var k = KINDS[kind] || KINDS.onto;
    var pose = opts.pose || 'rest';
    var label = opts.label || k.name;
    var idle = opts.idle ? ' data-idle="' + opts.idle + '"' : '';
    var gaze = opts.gaze === false ? '' : ' data-gaze';
    var cls = 'mascot ' + kind + (opts.className ? ' ' + opts.className : '');
    var eyes = k.eyes.map(function (e) {
      return '<circle class="m-eye" cx="' + e[0] + '" cy="' + e[1] + '" r="4.2"/>' +
             '<circle class="m-glint" cx="' + (e[0] + 1.4) + '" cy="' + (e[1] - 1.4) + '" r="1.1"/>';
    }).join('');
    return '<svg class="' + cls + '" data-kind="' + kind + '" data-pose="' + pose + '"' + idle + gaze +
      ' viewBox="0 0 120 120" role="img" aria-label="' + label + '" focusable="false">' +
      '<ellipse class="m-shadow" cx="' + k.shadow[0] + '" cy="' + k.shadow[1] + '" rx="' + k.shadow[2] + '" ry="' + k.shadow[3] + '"/>' +
      '<g class="m-figure">' +
        '<g class="m-confetti" aria-hidden="true">' +
          '<circle cx="30" cy="22" r="3" fill="#F2735C"/><circle cx="60" cy="8" r="3" fill="#9DB8A0"/><circle cx="92" cy="20" r="3" fill="#A99AD8"/>' +
          '<circle cx="44" cy="6" r="2" fill="#A99AD8"/><circle cx="78" cy="4" r="2" fill="#F2735C"/></g>' +
        '<g class="m-body"><path d="' + k.body + '" fill="' + k.fill + '"/><path d="' + k.shade + '" fill="' + k.dark + '" opacity=".55"/>' +
          '<ellipse cx="46" cy="34" rx="10" ry="5" fill="' + k.light + '" opacity=".35" transform="rotate(-25 46 34)"/></g>' +
        '<g class="m-arm m-arm-l"><path d="' + k.armL + '" fill="none" stroke="' + k.dark + '" stroke-width="9" stroke-linecap="round"/></g>' +
        '<g class="m-arm m-arm-r"><path d="' + k.armR + '" fill="none" stroke="' + k.dark + '" stroke-width="9" stroke-linecap="round"/>' +
          '<g class="m-tool" aria-hidden="true"><rect x="94" y="78" width="16" height="7" rx="2" fill="#1B1B1F" opacity=".8" transform="rotate(-20 100 82)"/></g></g>' +
        '<g class="m-heart" aria-hidden="true"><path d="M60 92 C52 84 44 80 44 72 C44 66 50 63 54 66 C57 68 60 72 60 72 C60 72 63 68 66 66 C70 63 76 66 76 72 C76 80 68 84 60 92 Z" fill="#F2735C" stroke="#fff" stroke-width="2.5"/></g>' +
        '<g class="m-eyes">' + eyes + '</g>' +
      '</g></svg>';
  }

  var root = document.documentElement;
  var KEY = 'krusgraph.mascots';
  function readPref() { try { return localStorage.getItem(KEY); } catch (e) { return null; } }
  function writePref(v) { try { localStorage.setItem(KEY, v); } catch (e) { /* private mode etc. */ } }
  function enabled() { return root.getAttribute('data-mascots') !== 'off'; }
  function setEnabled(on) {
    root.setAttribute('data-mascots', on ? 'on' : 'off');
    writePref(on ? 'on' : 'off');
    document.querySelectorAll('[data-mascot-toggle]').forEach(function (b) {
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.textContent = on ? 'Mascots: on' : 'Mascots: off';
    });
    document.dispatchEvent(new CustomEvent('mascots:toggle', { detail: { enabled: on } }));
  }
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  var hoverable = window.matchMedia('(hover: hover) and (pointer: fine)');
  function motionOK() { return !reduced.matches && enabled(); }

  // Upgrade <span data-mascot="onto" data-pose="look" data-idle="breathe" data-label="..."></span> placeholders.
  function mount(scope) {
    (scope || document).querySelectorAll('[data-mascot]').forEach(function (el) {
      if (el.querySelector('svg')) return;
      el.innerHTML = svg(el.getAttribute('data-mascot'), {
        pose: el.getAttribute('data-pose') || 'rest', idle: el.getAttribute('data-idle'),
        label: el.getAttribute('data-label'), gaze: el.getAttribute('data-gaze') !== 'off', className: el.getAttribute('data-class') || ''
      });
    });
  }
  function setPose(el, pose) {
    var s = el.matches && el.matches('svg.mascot') ? el : el.querySelector('svg.mascot');
    if (s) s.setAttribute('data-pose', pose);
    return s;
  }

  // Gaze: eyes drift a few px toward the pointer. Reactive, not an animation; off under reduced motion and on touch.
  var pointer = null, raf = 0;
  function updateGaze() {
    raf = 0;
    if (!pointer) return;
    document.querySelectorAll('svg.mascot[data-gaze]').forEach(function (m) {
      var r = m.getBoundingClientRect();
      if (!r.width) return;
      var dx = pointer.x - (r.left + r.width / 2), dy = pointer.y - (r.top + r.height * 0.45);
      var d = Math.hypot(dx, dy) || 1, a = Math.min(1, d / 240) * 3.2;
      m.style.setProperty('--gx', (dx / d * a).toFixed(2) + 'px');
      m.style.setProperty('--gy', (dy / d * a).toFixed(2) + 'px');
    });
  }
  function onMove(e) {
    if (!motionOK() || !hoverable.matches) return;
    pointer = { x: e.clientX, y: e.clientY };
    if (!raf) raf = requestAnimationFrame(updateGaze);
  }

  // Speech bubble next to an element (inside a positioned container).
  function say(container, el, text, opts) {
    opts = opts || {};
    var b = container.querySelector('.bubble.live');
    if (!b) { b = document.createElement('div'); b.className = 'bubble live'; b.setAttribute('role', 'status'); container.appendChild(b); }
    if (!text) { b.classList.remove('show'); return b; }
    b.textContent = text;
    var cr = container.getBoundingClientRect(), er = el.getBoundingClientRect();
    var left = er.left - cr.left + (opts.dx || 0), top = er.top - cr.top - 38 + (opts.dy || 0);
    b.style.left = Math.max(6, Math.min(left, cr.width - 170)) + 'px';
    b.style.top = Math.max(6, top) + 'px';
    b.classList.add('show');
    return b;
  }

  /* Onto follows the pointer in a graph area, at a distance, never covering anything (pointer-events: none).
     States: rest → notice → follow → pause (over a table) → explain (bubble) → aside (after a click). */
  function follower(area, opts) {
    opts = opts || {};
    if (!hoverable.matches) return null;           // mobile: a still figure helps on tap instead (page code)
    var wrap = document.createElement('div');
    wrap.className = 'g-follower';
    wrap.setAttribute('aria-hidden', 'true');
    wrap.innerHTML = svg('onto', { pose: 'rest', gaze: false, label: '' });
    area.appendChild(wrap);
    var fig = wrap.firstChild, target = null, pos = null, state = 'rest', hoverNode = null, pauseTimer = 0, animating = 0;
    var bubbleText = opts.text || 'Explore this table.';
    function step() {
      animating = 0;
      if (!target || !pos) return;
      pos.x += (target.x - pos.x) * 0.12; pos.y += (target.y - pos.y) * 0.12;
      wrap.style.transform = 'translate(' + pos.x.toFixed(1) + 'px,' + pos.y.toFixed(1) + 'px)';
      if (Math.abs(target.x - pos.x) + Math.abs(target.y - pos.y) > 0.6) animating = requestAnimationFrame(step);
    }
    function go(x, y) { target = { x: x, y: y }; if (!pos) pos = { x: x, y: y }; if (!animating) animating = requestAnimationFrame(step); }
    function setState(s) {
      if (state === s) return;
      state = s;
      fig.setAttribute('data-pose', s === 'notice' ? 'notice' : s === 'explain' ? 'explain' : s === 'aside' ? 'aside' : s === 'pause' ? 'look' : 'rest');
      if (opts.onState) opts.onState(s);
    }
    area.addEventListener('pointerenter', function (e) {
      if (!motionOK()) return;
      wrap.classList.add('visible'); setState('notice');
      var r = area.getBoundingClientRect(); go(e.clientX - r.left + 28, e.clientY - r.top + 28);
      setTimeout(function () { if (state === 'notice') setState('follow'); }, 350);
    });
    area.addEventListener('pointermove', function (e) {
      if (!motionOK()) { wrap.classList.remove('visible'); return; }
      wrap.classList.add('visible');
      var r = area.getBoundingClientRect();
      var node = e.target.closest && e.target.closest('.g-node');
      if (state === 'aside') return;                 // stepped aside after a click; stays until the pointer leaves
      var x, y;
      if (node) {                                     // beside the hovered card, never on it: right of it, else left
        var nr = node.getBoundingClientRect(), nx = nr.left - r.left, ny = nr.top - r.top;
        x = nx + nr.width + 10; if (x + 52 > r.width) x = nx - 60;
        y = ny + nr.height - 44;
      } else {                                        // follow at a distance: below-right of the pointer
        x = e.clientX - r.left + 34; y = e.clientY - r.top + 34;
      }
      x = Math.max(0, Math.min(x, r.width - 52)); y = Math.max(0, Math.min(y, r.height - 56));
      go(x, y);
      if (node !== hoverNode) {
        hoverNode = node; clearTimeout(pauseTimer); say(area, wrap, '');
        if (node) {
          setState('pause');
          pauseTimer = setTimeout(function () {   // the bubble sits above the card, not over its text
            if (hoverNode === node && state !== 'aside') { setState('explain'); say(area, node, bubbleText.replace('{table}', node.getAttribute('data-table') || 'this table'), { dx: 0, dy: -4 }); }
          }, 650);
        } else setState('follow');
      }
    });
    area.addEventListener('pointerdown', function () { if (!motionOK()) return; clearTimeout(pauseTimer); say(area, wrap, ''); setState('aside'); var r = area.getBoundingClientRect(); go(r.width - 60, r.height - 72); });
    area.addEventListener('pointerleave', function () { clearTimeout(pauseTimer); say(area, wrap, ''); wrap.classList.remove('visible'); hoverNode = null; setState('rest'); });
    return { element: wrap, figure: fig, setState: setState };
  }

  /* Builder: ready → (you start) → working → success | failure → calm. The caller owns the real status text;
     the figure only reacts. There is no celebration on failure. */
  function build(fig, outcome, hooks) {
    hooks = hooks || {};
    var s = fig.matches('svg.mascot') ? fig : fig.querySelector('svg.mascot');
    var quick = !motionOK();
    s.setAttribute('data-pose', 'working'); if (hooks.onState) hooks.onState('working');
    var t1 = quick ? 0 : 1400, t2 = quick ? 0 : 2200;
    var timer = setTimeout(function () {
      s.setAttribute('data-pose', outcome === 'success' ? 'celebrate' : 'failure');
      if (hooks.onState) hooks.onState(outcome);
      setTimeout(function () { s.setAttribute('data-pose', 'calm'); if (hooks.onState) hooks.onState('calm'); }, t2);
    }, t1);
    return function cancel() { clearTimeout(timer); };
  }

  function init() {
    var pref = readPref();
    root.setAttribute('data-mascots', pref === 'off' ? 'off' : 'on');
    if (!reduced.matches) root.classList.add('motion');
    reduced.addEventListener && reduced.addEventListener('change', function () { root.classList.toggle('motion', !reduced.matches); });
    mount(document);
    document.querySelectorAll('[data-mascot-toggle]').forEach(function (b) {
      b.setAttribute('aria-pressed', enabled() ? 'true' : 'false');
      b.textContent = enabled() ? 'Mascots: on' : 'Mascots: off';
      b.addEventListener('click', function () { setEnabled(!enabled()); });
    });
    window.addEventListener('pointermove', onMove, { passive: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();

  window.Mascots = { svg: svg, mount: mount, setPose: setPose, say: say, follower: follower, build: build,
                     enabled: enabled, setEnabled: setEnabled, motionOK: motionOK, hoverable: function () { return hoverable.matches; }, KINDS: KINDS };
})();
