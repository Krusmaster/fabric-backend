/* Krusgraph mascots — three soft stones, drawn as layered inline SVG.
   Layers per figure: shadow, body (with matte shade), arms, eyes. Poses are data-pose attributes styled in site.css;
   the body shapes and the small behaviours (gaze, follower, builder sequence) live here.
   Respects prefers-reduced-motion (stills) and a visible off switch stored in localStorage (try/catch). */
(function () {
  'use strict';
  /* Shapes live in a 120×120 box with the ground at y=108. Each body is a soft matte stone: a radial gradient (lighter
     top-left, tinted darker lower edge), a faint highlight oval, a blurred contact shadow, short stub arms resting
     against the body (about 30 % of the body height) and small bead eyes with a glint. No legs, fingers, noses or mouths. */
  var KINDS = {
    onto: { // the guide: an upright egg, leaning forward
      fill: '#F2735C', light: '#FBB4A2', dark: '#D8604B', cheek: '#FFD0C4', name: 'Onto, the coral guide', tilt: 6,
      body: 'M60 20 C79 20 92 46 92 72 C92 95 78 108 60 108 C42 108 28 95 28 72 C28 46 41 20 60 20 Z',
      eyes: [[53, 58], [70, 57]], eyeR: 3.6, blush: [[45, 67], [78, 66]],
      armL: [31, 70, -14], armR: [89, 70, 14], armRX: 7.4, armRY: 13, hl: [46, 40, 9, 5.5, -30], shadow: [60, 109, 30, 4.5]
    },
    thinker: { // the thinker: wide, low and settled, like a cushion
      fill: '#9DB8A0', light: '#CFE0D0', dark: '#7D9C82', cheek: '#F6B7A6', name: 'The thinker, the sage one', tilt: 0,
      body: 'M60 50 C88 50 106 58 106 80 C106 100 90 108 60 108 C30 108 14 100 14 80 C14 58 32 50 60 50 Z',
      eyes: [[49, 72], [71, 72]], eyeR: 3.6, blush: [[38, 82], [82, 82]],
      armL: [17, 84, -24], armR: [103, 84, 24], armRX: 7.6, armRY: 11.5, hl: [38, 61, 11, 4.5, -12], shadow: [60, 109, 40, 4.5]
    },
    builder: { // the maker: a tapered drop that leans
      fill: '#A99AD8', light: '#D6CEF2', dark: '#8C7BC4', cheek: '#F4BCD0', name: 'The builder, the lavender one', tilt: 7,
      body: 'M62 16 C68 30 92 54 92 78 C92 97 78 108 60 108 C41 108 28 97 28 78 C28 55 55 32 62 16 Z',
      eyes: [[52, 70], [69, 70]], eyeR: 3.5, blush: [[44, 80], [77, 80]],
      armL: [31, 80, -14], armR: [89, 80, 14], armRX: 7, armRY: 12, hl: [48, 52, 7, 4.5, -40], shadow: [60, 109, 29, 4.5]
    }
  };
  var uid = 0;

  function arm(side, a, k, g) {
    // a = [shoulder x, shoulder y, resting angle]; the stub hangs from the shoulder and lies against the body.
    var x = a[0], y = a[1];
    return '<g class="m-arm m-arm-' + side + '" style="transform-origin:' + x + 'px ' + y + 'px">' +
      '<g transform="rotate(' + a[2] + ' ' + x + ' ' + y + ')">' +
      '<ellipse cx="' + (x + (side === 'l' ? 1.6 : -1.6)) + '" cy="' + (y + k.armRY - 1.5) + '" rx="' + k.armRX + '" ry="' + k.armRY + '" fill="' + k.dark + '" opacity=".75" filter="url(#' + g + 'h)"/>' +
      '<ellipse cx="' + x + '" cy="' + (y + k.armRY - 3) + '" rx="' + k.armRX + '" ry="' + k.armRY + '" fill="url(#' + g + 'a)"/>' +
      '<ellipse cx="' + (x - 1.5) + '" cy="' + (y + 2) + '" rx="2.4" ry="4" fill="#fff" opacity=".18"/></g>' +
      (side === 'r' ? '<g class="m-tool" aria-hidden="true"><rect x="' + (x + 2) + '" y="' + (y + 16) + '" width="15" height="6.5" rx="2.5" fill="#5B4A3A"/><rect x="' + (x + 7) + '" y="' + (y + 20) + '" width="4" height="10" rx="2" fill="#8A6B4F"/></g>' : '') +
      '</g>';
  }

  function svg(kind, opts) {
    opts = opts || {};
    var k = KINDS[kind] || KINDS.onto;
    var pose = opts.pose || 'rest';
    var label = opts.label || k.name;
    var idle = opts.idle ? ' data-idle="' + opts.idle + '"' : '';
    var gaze = opts.gaze === false ? '' : ' data-gaze';
    var cls = 'mascot ' + kind + (opts.className ? ' ' + opts.className : '');
    var g = 'm' + (++uid) + '-';
    var eyes = k.eyes.map(function (e) {
      return '<circle class="m-eye" cx="' + e[0] + '" cy="' + e[1] + '" r="' + k.eyeR + '"/>' +
             '<circle class="m-glint" cx="' + (e[0] + 1.2) + '" cy="' + (e[1] - 1.3) + '" r="1.15"/>';
    }).join('');
    var blush = k.blush.map(function (b) { return '<ellipse cx="' + b[0] + '" cy="' + b[1] + '" rx="5" ry="2.8" fill="' + k.cheek + '" opacity=".55" filter="url(#' + g + 'h)"/>'; }).join('');
    var hl = k.hl;
    var aria = label ? ' role="img" aria-label="' + label + '"' : ' aria-hidden="true"';
    return '<svg class="' + cls + '" data-kind="' + kind + '" data-pose="' + pose + '"' + idle + gaze +
      ' viewBox="0 0 120 120"' + aria + ' focusable="false" style="--tilt:' + k.tilt + 'deg">' +
      '<defs>' +
        '<radialGradient id="' + g + 'b" cx="36%" cy="28%" r="78%" fx="34%" fy="24%">' +
          '<stop offset="0" stop-color="' + k.light + '"/><stop offset=".5" stop-color="' + k.fill + '"/><stop offset="1" stop-color="' + k.dark + '"/></radialGradient>' +
        '<radialGradient id="' + g + 'a" cx="35%" cy="25%" r="85%"><stop offset="0" stop-color="' + k.light + '"/><stop offset=".45" stop-color="' + k.fill + '"/><stop offset="1" stop-color="' + k.dark + '"/></radialGradient>' +
        '<filter id="' + g + 's" x="-30%" y="-200%" width="160%" height="500%"><feGaussianBlur stdDeviation="2.6"/></filter>' +
        '<filter id="' + g + 'h" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.6"/></filter>' +
      '</defs>' +
      '<ellipse class="m-shadow" cx="' + k.shadow[0] + '" cy="' + k.shadow[1] + '" rx="' + k.shadow[2] + '" ry="' + k.shadow[3] + '" fill="' + k.dark + '" filter="url(#' + g + 's)"/>' +
      '<g class="m-figure">' +
        '<g class="m-confetti" aria-hidden="true">' +
          '<circle cx="28" cy="26" r="3" fill="#F2735C"/><circle cx="60" cy="8" r="3" fill="#9DB8A0"/><circle cx="94" cy="22" r="3" fill="#A99AD8"/>' +
          '<circle cx="42" cy="10" r="2" fill="#E3A93B"/><circle cx="80" cy="6" r="2" fill="#F2735C"/></g>' +
        '<g class="m-body"><path d="' + k.body + '" fill="url(#' + g + 'b)"/>' +
          '<ellipse cx="' + hl[0] + '" cy="' + hl[1] + '" rx="' + hl[2] + '" ry="' + hl[3] + '" fill="#fff" opacity=".42" filter="url(#' + g + 'h)" transform="rotate(' + hl[4] + ' ' + hl[0] + ' ' + hl[1] + ')"/>' +
          blush + '</g>' +
        arm('l', k.armL, k, g) + arm('r', k.armR, k, g) +
        '<g class="m-heart" aria-hidden="true"><path d="M60 98 C53 91 46 88 46 81 C46 76 51 73 55 76 C57.5 77.8 60 81 60 81 C60 81 62.5 77.8 65 76 C69 73 74 76 74 81 C74 88 67 91 60 98 Z" fill="#F2735C" stroke="#fff" stroke-width="2.5"/></g>' +
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
    wrap.innerHTML = svg('onto', { pose: 'rest', label: '' });
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
      // follow at a distance: below-right of the pointer, kept inside the area and away from the hovered card
      var x = e.clientX - r.left + 26, y = e.clientY - r.top + 26;
      x = Math.max(0, Math.min(x, r.width - 52)); y = Math.max(0, Math.min(y, r.height - 52));
      go(x, y);
      if (node !== hoverNode) {
        hoverNode = node; clearTimeout(pauseTimer); say(area, wrap, '');
        if (node) {
          setState('pause');
          pauseTimer = setTimeout(function () {
            if (hoverNode === node && state !== 'aside') { setState('explain'); say(area, wrap, bubbleText.replace('{table}', node.getAttribute('data-table') || 'this table'), { dx: 44, dy: 12 }); }
          }, 650);
        } else setState('follow');
      }
    });
    area.addEventListener('pointerdown', function () { if (!motionOK()) return; clearTimeout(pauseTimer); say(area, wrap, ''); setState('aside'); var r = area.getBoundingClientRect(); go(r.width - 60, r.height - 60); });
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
