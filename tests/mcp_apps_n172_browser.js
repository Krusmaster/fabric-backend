// n172: a card at Claude's width under a fake host: the map's labels on their edges, nothing overlapping, and what the
// mascots and the card say. Usage:
//   node mcp_apps_n172_browser.js <card.html> <result.json> <tool> <light|dark> <width> [screenshot.png]
// result.json: the CallToolResult's structuredContent, with __args (the call's arguments).
// Prints JSON {errors, nodes, labels, offEdge, outside, overlaps, nodeOverlaps, unlabelled, svgWidth, bubbles, verdict,
// verdictShown, countsShown, title, buttons, more, afterToggle, colours, text}.
const { chromium } = require('playwright');
const fs = require('fs');
const [cardPath, resultPath, tool, theme, width, shot] = process.argv.slice(2);
const card = fs.readFileSync(cardPath, 'utf8'), result = JSON.parse(fs.readFileSync(resultPath, 'utf8'));
const W = Number(width || 680);
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ colorScheme: theme === 'dark' ? 'dark' : 'light', viewport: { width: W + 40, height: 900 }, deviceScaleFactor: shot ? 2 : 1 });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.setContent('<body style="margin:0;background:' + (theme === 'dark' ? '#1b1b1f' : '#fff') + '"><iframe id="f" sandbox="allow-scripts" style="border:0;width:' + W + 'px;height:3000px"></iframe></body>');
  await page.evaluate(([card, result, tool]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data;
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: { serverTools: {} }, hostContext: { toolInfo: { tool: { name: tool } } } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: result.__args || {} } }, '*');
        const sc = Object.assign({}, result); delete sc.__args;
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: { content: [{ type: 'text', text: '{}' }], structuredContent: sc } }, '*');
      } else if (m.method === 'ui/notifications/size-changed') { f.style.height = Math.max(200, m.params.height) + 'px'; }
    });
    f.srcdoc = card;
  }, [card, result, tool]);
  await page.waitForTimeout(1500);
  const fr = page.frames().find(x => x !== page.mainFrame());
  const read = () => fr.evaluate(() => {
    const q = (s) => Array.from(document.querySelectorAll(s));
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
    const svg = document.querySelector('#pictures svg');
    const svgBox = svg ? box(svg) : null;
    const nodes = q('#pictures .kgc-n').map(g => ({ table: g.getAttribute('data-table'), text: Array.from(g.querySelectorAll('text')).map(t => t.textContent), box: box(g.querySelector('rect')) }));
    const labels = q('#pictures .kgc-lab').map(g => ({ id: g.getAttribute('data-id'), cls: g.getAttribute('class'), text: Array.from(g.querySelectorAll('text')).map(t => t.textContent), box: box(g.querySelector('rect')) }));
    const meet = (a, b) => a.x < b.x + b.w - 0.5 && b.x < a.x + a.w - 0.5 && a.y < b.y + b.h - 0.5 && b.y < a.y + a.h - 0.5;
    let overlaps = 0, nodeOverlaps = 0;
    labels.forEach((l, i) => { nodes.forEach(n => { if (meet(l.box, n.box)) overlaps++; }); labels.slice(i + 1).forEach(m => { if (meet(l.box, m.box)) overlaps++; }); });
    nodes.forEach((n, i) => nodes.slice(i + 1).forEach(m => { if (meet(n.box, m.box)) nodeOverlaps++; }));
    // a label is on its edge: the label's centre lies on the drawn line (in screen coordinates, within 1.5 px)
    const offEdge = [], outside = [];
    labels.forEach(l => {
      const line = document.querySelector('#pictures .kgc-e[data-id="' + CSS.escape(l.id) + '"] line');
      if (!line) { offEdge.push(l.id + ': no line'); return; }
      const m = line.getScreenCTM(), pt = (x, y) => { const p = svg.createSVGPoint(); p.x = x; p.y = y; return p.matrixTransform(m); };
      const a = pt(+line.getAttribute('x1'), +line.getAttribute('y1')), b = pt(+line.getAttribute('x2'), +line.getAttribute('y2'));
      const c = { x: l.box.x + l.box.w / 2, y: l.box.y + l.box.h / 2 };
      const dx = b.x - a.x, dy = b.y - a.y, len2 = dx * dx + dy * dy;
      const t = len2 ? Math.max(0, Math.min(1, ((c.x - a.x) * dx + (c.y - a.y) * dy) / len2)) : 0;
      const d = Math.hypot(a.x + t * dx - c.x, a.y + t * dy - c.y);
      if (d > 1.5) offEdge.push(l.id + ': ' + d.toFixed(1) + ' px off its line');
      if (svgBox && (l.box.x < svgBox.x - 0.5 || l.box.y < svgBox.y - 0.5 || l.box.x + l.box.w > svgBox.x + svgBox.w + 0.5 || l.box.y + l.box.h > svgBox.y + svgBox.h + 0.5)) outside.push(l.id);
    });
    const shown = (e) => !!e && e.getClientRects().length > 0 && e.checkVisibility();   // what is drawn, whatever the attributes say
    const bubbles = {};
    q('#kg-mascots .kg-say').forEach(r => { if (shown(r)) bubbles[r.getAttribute('data-mascot')] = r.querySelector('.kg-line').textContent; });
    const verdict = document.getElementById('verdict'), counts = document.getElementById('counts');
    const more = document.getElementById('next');
    const css = (e, p) => e ? getComputedStyle(e)[p] : '';
    return {
      nodes: nodes.map(n => ({ table: n.table, text: n.text })), labels: labels.map(l => ({ id: l.id, cls: l.cls, text: l.text })),
      overlaps, nodeOverlaps, offEdge, outside, unlabelled: svg ? (svg.getAttribute('data-unlabelled') || '') : '',
      svgWidth: svgBox ? svgBox.w : 0, bodyWidth: document.documentElement.scrollWidth,
      bubbles, verdict: verdict ? verdict.textContent : '', verdictShown: shown(verdict), countsShown: shown(counts),
      title: (document.getElementById('title') || document.querySelector('h1')).textContent,
      buttons: q('button').filter(shown).map(b => b.textContent),
      groups: q('.act-who').filter(shown).map(e => e.textContent),
      more: more ? { tag: more.tagName, open: !!more.open, hidden: more.hidden, text: more.textContent } : null,
      colours: { ink: css(document.body, 'color'), bg: css(document.body, 'backgroundColor'), bubble: css(document.querySelector('.kg-bub'), 'backgroundColor'),
                 bubbleInk: css(document.querySelector('.kg-line'), 'color'), label: css(document.querySelector('.kgc-lab text'), 'fill'),
                 labelBg: css(document.querySelector('.kgc-lab rect'), 'fill') },
      text: document.querySelector('main').innerText,
    };
  });
  const out = await read();
  if (shot) {
    await fr.evaluate(() => document.querySelectorAll('details').forEach(d => { d.open = false; }));
    await page.waitForTimeout(200);
    await page.locator('#f').screenshot({ path: shot });
  }
  // the mascots switch: off shows the summary that Onto said; on hides it again
  await fr.click('#kg-toggle');
  await page.waitForTimeout(100);
  const off = await read();
  out.afterToggle = { verdictShown: off.verdictShown, countsShown: off.countsShown, bubbles: off.bubbles };
  out.errors = errors;
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
