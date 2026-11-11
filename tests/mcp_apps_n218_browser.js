// n218: a card in Chromium under a fake host. Usage: node mcp_apps_n218_browser.js <card.html> <data.json>
// data.json: {args, result, caps, reply, clicks: [{text?, css?, nth?}], scheme}. The host answers tools/call with
// `reply` (or {} when none) and ui/message with {} unless caps.refuseMessages. Prints JSON {log, text, errors, sql, pressed}.
const { chromium } = require('playwright');
const fs = require('fs');
const card = fs.readFileSync(process.argv[2], 'utf8');
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ colorScheme: data.scheme || 'light' });
  const log = [], errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!r.url().startsWith('about:') && !r.url().startsWith('data:')) requests.push(r.url()); });
  await page.exposeFunction('logMsg', m => log.push(m));
  await page.setContent('<iframe id="f" sandbox="allow-scripts" style="width:720px;height:1800px"></iframe>');
  await page.evaluate(([card, data]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data; window.logMsg(m);
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      const fail = (code, message) => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, error: { code, message } }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: data.caps || {}, hostContext: { theme: data.scheme || 'light' } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: data.args } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: data.result }, '*');
      } else if (m.method === 'tools/call') setTimeout(() => reply(data.reply || { content: [{ type: 'text', text: '{"summary": "done"}' }] }), 20);
      else if (m.method === 'ui/message') { if ((data.caps || {}).refuseMessages) fail(-32601, 'Method not found'); else reply({}); }
    });
    f.srcdoc = card;
  }, [card, data]);
  const fr = page.frameLocator('#f');
  await fr.locator('main').waitFor({ timeout: 10000 });
  await page.waitForTimeout(300);
  for (const c of data.clicks || []) {
    const loc = c.css ? fr.locator(c.css) : fr.locator('button', { hasText: c.text });
    if (c.key) { await loc.nth(c.nth || 0).focus(); await page.keyboard.press(c.key); }
    else await loc.nth(c.nth || 0).click({ timeout: 10000 });
    await page.waitForTimeout(250);
  }
  const text = await fr.locator('main').innerText();
  const sql = await fr.locator('pre.ck-sql').evaluateAll(ps => ps.filter(p => !p.hidden).map(p => p.textContent));
  const pressed = await fr.locator('button[aria-pressed="true"]').evaluateAll(bs => bs.map(b => b.getAttribute('data-item') + ':' + b.getAttribute('data-review')));
  const pills = await fr.locator('.ck-table tr[data-check]').evaluateAll(rs => rs.map(r => [r.getAttribute('data-check'), r.querySelector('.pill:not(.pill-rule)').textContent]));
  await browser.close();
  process.stdout.write(JSON.stringify({ log: log.filter(m => m.method !== 'ui/notifications/size-changed'), text, errors, requests, sql, pressed, pills }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
