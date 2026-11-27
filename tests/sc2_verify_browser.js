// SC2: the verify card in Chromium under a fake host (the same host as wb13_card_browser.js), its picture read back.
// Usage: node sc2_verify_browser.js <card.html> <data.json>; data.json: {result, width, scheme}
// Prints JSON {vf: {state, pill, rows, labels, fits, summaries, keyboard, opened}, overflow, text, errors}.
const { chromium } = require('playwright');
const fs = require('fs');
const card = fs.readFileSync(process.argv[2], 'utf8');
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const browser = await chromium.launch();
  const width = data.width || 375;
  const page = await browser.newPage({ colorScheme: data.scheme || 'light', viewport: { width: width + 20, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.setContent(`<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:${width}px;height:3000px"></iframe></body>`);
  await page.evaluate(([card, data]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data, reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: {}, hostContext: { theme: data.scheme || 'light' } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: {} } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: data.result }, '*');
      }
    });
    f.srcdoc = card;
  }, [card, data]);
  const fr = page.frameLocator('#f');
  await fr.locator('.vf').waitFor({ timeout: 10000 });
  const frame = page.frames().find(x => x !== page.mainFrame());
  const read = () => frame.evaluate(() => {
    const vf = document.querySelector('.vf'), de = document.documentElement;
    return {
      state: vf.getAttribute('data-state'),
      pill: vf.querySelector('.vf-p').innerText.trim(),
      rows: Array.from(vf.querySelectorAll('.vf-r')).map(r => [r.querySelector('.vf-n').textContent, r.getAttribute('data-state')]),
      labels: Array.from(vf.querySelectorAll('svg:not([aria-hidden])')).map(s => s.getAttribute('role') === 'img' ? s.getAttribute('aria-label') : ''),
      fits: Array.from(vf.querySelectorAll('*')).every(e => e.getBoundingClientRect().right <= de.clientWidth + 1),
      summaries: Array.from(vf.querySelectorAll('.vf-r summary')).map(s => s.textContent.trim()),
    };
  });
  const vf = await read();
  if (vf.summaries.length) {
    await fr.locator('.vf-r summary').first().focus();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(150);
    vf.keyboard = await frame.evaluate(() => document.querySelector('.vf-r details').open);
    const n = await fr.locator('.vf-r summary').count();
    for (let i = 1; i < n; i++) await fr.locator('.vf-r summary').nth(i).click();
    await page.waitForTimeout(200);
    vf.opened = await frame.evaluate(() => ({ edges: document.querySelectorAll('.vf .vf-e').length, dashed: document.querySelectorAll('.vf .vf-e.vf-off').length }));
    vf.fits = (await read()).fits;
  }
  const info = await frame.evaluate(() => ({ overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
                                             text: document.querySelector('main').innerText }));
  await browser.close();
  process.stdout.write(JSON.stringify({ vf, ...info, errors }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
