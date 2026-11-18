// WB12: the start card in Chromium under a fake host, at a given width and colour scheme, in a frame much taller than
// the content (the blank space of Gustav's chat test, issue #68). Usage: node wb12_card_browser.js <card.html> <data.json>
// data.json: {result, caps, reply, width, scheme, clicks: [{text?, css?}], shot?}. Prints JSON {sizes, mainHeight, frameHeight,
// overflow, buttons, text, errors, log, background}.
const { chromium } = require('playwright');
const fs = require('fs');
const card = fs.readFileSync(process.argv[2], 'utf8');
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const browser = await chromium.launch();
  const width = data.width || 720;
  const page = await browser.newPage({ colorScheme: data.scheme || 'light', viewport: { width: width + 40, height: 900 } });
  const log = [], errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.exposeFunction('logMsg', m => log.push(m));
  await page.setContent(`<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:${width}px;height:1800px"></iframe></body>`);
  await page.evaluate(([card, data]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data; window.logMsg(m);
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: data.caps || {}, hostContext: { theme: data.scheme || 'light' } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: {} } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: data.result }, '*');
      } else if (m.method === 'tools/call') setTimeout(() => reply(data.reply || { content: [{ type: 'text', text: '{"summary": "done"}' }] }), 20);
      else if (m.method === 'ui/message') reply({});
    });
    f.srcdoc = card;
  }, [card, data]);
  const fr = page.frameLocator('#f');
  await fr.locator('main').waitFor({ timeout: 10000 });
  await page.waitForTimeout(400);
  for (const c of data.clicks || []) {
    const loc = c.css ? fr.locator(c.css) : fr.locator('button', { hasText: c.text });
    await loc.nth(c.nth || 0).click({ timeout: 10000 });
    await page.waitForTimeout(300);
  }
  const frame = page.frames().find(x => x !== page.mainFrame());
  const info = await frame.evaluate(() => {
    const m = document.getElementById('main');
    const de = document.documentElement;
    return {
      mainHeight: Math.ceil(m.getBoundingClientRect().height), frameHeight: window.innerHeight,
      overflow: de.scrollWidth > de.clientWidth + 1,
      background: getComputedStyle(document.body).backgroundColor,
      buttons: Array.from(document.querySelectorAll('main button')).filter(b => b.offsetParent !== null || b.closest('details'))
        .map(b => ({ text: b.textContent.trim(), disabled: b.disabled, kind: b.getAttribute('data-kind') || '', cls: b.className })),
      text: m.innerText,
    };
  });
  if (data.shot) await page.screenshot({ path: data.shot, clip: { x: 0, y: 0, width, height: Math.min(1800, info.mainHeight + 20) } });
  await browser.close();
  const sizes = log.filter(m => m.method === 'ui/notifications/size-changed').map(m => m.params);
  process.stdout.write(JSON.stringify({ ...info, sizes, errors, log: log.filter(m => m.method !== 'ui/notifications/size-changed') }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
