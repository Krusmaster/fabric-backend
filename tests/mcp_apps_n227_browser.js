// n227: a card in Chromium under a fake host, at a phone's width. Usage: node mcp_apps_n227_browser.js <card.html> <data.json>
// data.json: {width (default 375), args, result, caps, toolInfo, reducedMotion,
//             replies: {<tool>: [CallToolResult, ...]}   the host's answers to tools/call per tool, in order (last repeats),
//             fail: {<tool>: {code, message}}            the host answers that tool's tools/call with a JSON-RPC error,
//             delay: ms before the host answers a tools/call (default 20),
//             clicks: [{text?, css?, nth?, wait?}]        wait: ms after the click (default 250); a snapshot follows each,
//             query: {<name>: css}}                       for each: the text of every match that is not hidden
// Prints JSON {log, text, snaps, errors, requests, overflow: [scrollWidth, clientWidth], found, spin}.
const { chromium } = require('playwright');
const fs = require('fs');
const card = fs.readFileSync(process.argv[2], 'utf8');
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const width = data.width || 375;
  const browser = await chromium.launch();
  const page = await browser.newPage({ colorScheme: data.scheme || 'light', viewport: { width: width, height: 900 },
                                       reducedMotion: data.reducedMotion ? 'reduce' : 'no-preference' });
  const log = [], errors = [], requests = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => { if (!r.url().startsWith('about:') && !r.url().startsWith('data:')) requests.push(r.url()); });
  await page.exposeFunction('logMsg', m => log.push(m));
  await page.setContent('<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:' + width + 'px;height:2600px"></iframe></body>');
  await page.evaluate(([card, data]) => {
    const f = document.getElementById('f'), seen = {};
    window.addEventListener('message', e => {
      const m = e.data; window.logMsg(m);
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      const fail = (code, message) => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, error: { code, message } }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: data.caps || {},
                                                hostContext: { theme: data.scheme || 'light', toolInfo: data.toolInfo } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: data.args } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: data.result }, '*');
      } else if (m.method === 'tools/call') {
        const name = m.params.name, bad = (data.fail || {})[name], list = (data.replies || {})[name] || [];
        const n = seen[name] = (seen[name] || 0) + 1;
        const r = list.length ? list[Math.min(n, list.length) - 1] : { content: [{ type: 'text', text: '{"summary": "done"}' }] };
        setTimeout(() => { if (bad) fail(bad.code, bad.message); else reply(r); }, data.delay == null ? 20 : data.delay);
      }
      else if (m.method === 'ui/message') { if ((data.caps || {}).refuseMessages) fail(-32601, 'Method not found'); else reply({}); }
      else if (m.method === 'ui/open-link') reply({});
    });
    f.srcdoc = card;
  }, [card, data]);
  const fr = page.frameLocator('#f');
  await fr.locator('main').waitFor({ timeout: 10000 });
  await page.waitForTimeout(300);
  const snaps = [];
  let spin = null;
  for (const c of data.clicks || []) {
    const loc = c.css ? fr.locator(c.css) : fr.locator('button', { hasText: c.text });
    await loc.nth(c.nth || 0).click({ timeout: 10000 });
    await page.waitForTimeout(c.wait == null ? 250 : c.wait);
    snaps.push(await fr.locator('main').innerText());
    if (spin === null && await fr.locator('.wait').count())
      spin = await fr.locator('.wait').first().evaluate(e => [e.getAttribute('data-motion'), e.querySelector('.wait-dots').getAttribute('data-on'),
                                                              getComputedStyle(e.querySelector('.wait-dots i')).animationName]);
  }
  const text = await fr.locator('main').innerText();
  const overflow = await fr.locator('html').evaluate(e => [e.scrollWidth, e.clientWidth]);
  const found = {};
  for (const k of Object.keys(data.query || {}))
    found[k] = await fr.locator(data.query[k]).evaluateAll(es => es.filter(e => !e.closest('[hidden]')).map(e => (e.textContent || '').trim()));
  await browser.close();
  process.stdout.write(JSON.stringify({ log: log.filter(m => m.method !== 'ui/notifications/size-changed'), text, snaps, errors, requests, overflow, found, spin }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
