// CO1: a card in Chromium under a fake host at a phone's width (390 px), light or dark: what the coach shows on the first
// view (the stage line, the one mascot line, the buttons), what is visible outside a closed details, and the same after
// Mascots: off. Usage: node co1_card_browser.js <card.html> <data.json>
// data.json: {result, args, caps, width, scheme}
// Prints JSON {stage, line, who, figure, figureAfterToggle, lineAfterToggle, buttons, primary, visible, overflow,
// background, ink, errors}.
const { chromium } = require('playwright');
const fs = require('fs');
const card = fs.readFileSync(process.argv[2], 'utf8');
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const browser = await chromium.launch();
  const width = data.width || 390;
  const page = await browser.newPage({ colorScheme: data.scheme || 'light', viewport: { width: width + 20, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.setContent(`<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:${width}px;height:2400px"></iframe></body>`);
  await page.evaluate(([card, data]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data;
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: data.caps || {}, hostContext: { theme: data.scheme || 'light' } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: data.args || {} } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: data.result }, '*');
      } else if (m.id != null) reply({});
    });
    f.srcdoc = card;
  }, [card, data]);
  const fr = page.frameLocator('#f');
  await fr.locator('main').waitFor({ timeout: 10000 });
  await page.waitForTimeout(600);
  const frame = page.frames().find(x => x !== page.mainFrame());
  const read = () => frame.evaluate(() => {
    const vis = e => !!e && !e.closest('[hidden]') && !(e.closest('details:not([open])') && !e.closest('summary')) &&
      getComputedStyle(e).display !== 'none' && e.getClientRects().length > 0;
    const c = document.querySelector('.nx-coach');
    const fig = c && c.querySelector('.kg-fig svg');
    const buttons = Array.from(document.querySelectorAll('.nx-b, .st-acts button')).filter(vis);
    const walker = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT);
    const parts = [];
    while (walker.nextNode()) { const n = walker.currentNode; if (n.textContent.trim() && vis(n.parentElement)) parts.push(n.textContent.trim()); }
    const cs = getComputedStyle(document.body);
    return {
      stage: c ? c.querySelector('.nx-stage').textContent : null,
      line: c ? c.querySelector('.nx-line').textContent : null,
      who: c ? c.querySelector('.kg-who').textContent : null,
      lineShown: !!c && vis(c.querySelector('.nx-line')),
      figure: !!fig && vis(fig),
      firstAfterHead: c ? c.previousElementSibling && c.previousElementSibling.classList.contains('kg-head') : false,
      oldFigures: Array.from(document.querySelectorAll('#kg-mascots .kg-say')).filter(vis).length,
      buttons: buttons.map(b => b.textContent.trim()),
      primary: buttons.filter(b => b.classList.contains('nx-primary') || b.getAttribute('data-primary') === 'true').map(b => b.textContent.trim()),
      visible: parts.join(' '),
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      background: cs.backgroundColor, ink: cs.color,
    };
  });
  const before = await read();
  await fr.locator('#kg-toggle').click({ timeout: 10000 });
  await page.waitForTimeout(200);
  const after = await read();
  console.log(JSON.stringify({ ...before, figureAfterToggle: after.figure, lineAfterToggle: after.lineShown, errors }));
  await browser.close();
})().catch(e => { console.error(e && e.stack || e); process.exit(1); });
