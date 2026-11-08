// n170: a card's pictures in Chromium under a fake host. Usage:
//   node mcp_apps_pictures_browser.js <card.html> <result.json> <tool> <light|dark> [screenshot.png] [width]
// result.json: the CallToolResult's structuredContent (the host sends it with the text content, as Claude does).
// Prints JSON {errors, nodes, edges, labels, list, products, productButtons, keyMarks, noKeyTags, text, overlaps}.
const { chromium } = require('playwright');
const fs = require('fs');
const [cardPath, resultPath, tool, theme, shot, width] = process.argv.slice(2);
const card = fs.readFileSync(cardPath, 'utf8'), result = JSON.parse(fs.readFileSync(resultPath, 'utf8'));
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ colorScheme: theme === 'dark' ? 'dark' : 'light', viewport: { width: Number(width || 720) + 40, height: 900 }, deviceScaleFactor: shot ? 2 : 1 });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.setContent('<body style="margin:0;background:' + (theme === 'dark' ? '#1b1b1f' : '#fff') + '"><iframe id="f" sandbox="allow-scripts" style="border:0;width:' + (width || 720) + 'px;height:3000px"></iframe></body>');
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
  const frame = page.frame({ url: /about:srcdoc/ }) || page.frames()[1];
  await page.waitForTimeout(1500);
  const fr = page.frames().find(x => x !== page.mainFrame());
  const out = await fr.evaluate(() => {
    const q = (s) => Array.from(document.querySelectorAll(s));
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
    const labels = q('#pictures .kgc-lab').map(g => ({ id: g.getAttribute('data-id'), cls: g.getAttribute('class'), text: Array.from(g.querySelectorAll('text')).map(t => t.textContent), box: box(g.querySelector('rect')) }));
    const nodes = q('#pictures .kgc-n').map(g => ({ table: g.getAttribute('data-table'), cls: g.getAttribute('class'), text: Array.from(g.querySelectorAll('text')).map(t => t.textContent), box: box(g.querySelector('rect')) }));
    // a label that covers a table, or another label
    const meet = (a, b) => a.x < b.x + b.w - 0.5 && b.x < a.x + a.w - 0.5 && a.y < b.y + b.h - 0.5 && b.y < a.y + a.h - 0.5;
    let overlaps = 0;
    labels.forEach((l, i) => { nodes.forEach(n => { if (meet(l.box, n.box)) overlaps++; }); labels.slice(i + 1).forEach(m => { if (meet(l.box, m.box)) overlaps++; }); });
    return {
      nodes: nodes.map(n => ({ table: n.table, cls: n.cls, text: n.text })),
      edges: q('#pictures .kgc-e').map(g => ({ id: g.getAttribute('data-id'), cls: g.getAttribute('class') })),
      labels: labels.map(l => ({ id: l.id, cls: l.cls, text: l.text })),
      list: q('#pictures .kg-list li').map(li => li.textContent),
      products: q('.kg-product').map(c => ({ slug: c.getAttribute('data-product'), text: c.innerText })),
      productButtons: q('.kg-product button').map(b => b.textContent),
      keyMarks: q('#pictures .kgc-key').length, noKeyTags: q('#pictures .kgc-nk').length,
      svgLabel: (document.querySelector('#pictures svg') || { getAttribute: () => '' }).getAttribute('aria-label'),
      svgWidth: (document.querySelector('#pictures svg') || { getBoundingClientRect: () => ({ width: 0 }) }).getBoundingClientRect().width,
      text: document.querySelector('main').innerText, overlaps,
    };
  });
  if (shot) {
    await fr.evaluate(() => document.querySelectorAll('details.kg-more').forEach(d => { d.open = false; }));
    await page.waitForTimeout(200);
    await page.locator('#f').screenshot({ path: shot });
    await page.frameLocator('#f').locator('#pictures').screenshot({ path: shot.replace(/\.png$/, '_pictures.png') });
  }
  out.errors = errors;
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
