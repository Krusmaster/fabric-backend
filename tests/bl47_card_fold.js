// BL47 (issue #104, second part): an older Start Krusgraph card folds when the path moved on in a newer card that the
// user opened by typing, without the BroadcastChannel (each card here is in its own page, so no channel is shared).
// Same fake host as wb15_click_through.js; every tools/call goes to the real hosted tools on the synthetic SAP demo
// (tests/test_bl47_card_fold.py answers them over HTTP on 127.0.0.1).
//
// Usage: node bl47_card_fold.js <card.html> <port> <scheme>
// Prints JSON {live, typed, reloaded, own, noTools, sample}: per card whether it folded, its text, the start calls it
// made and the last height it reported.
const { chromium } = require('playwright');
const fs = require('fs');
const http = require('http');
const card = fs.readFileSync(process.argv[2], 'utf8');
const port = Number(process.argv[3]);
const scheme = process.argv[4] || 'light';
const W = 390, H = 800;
const B = { workspace: 'demo', source: 'demo_lh', schema: 'dbo' };

function hostCall(name, args) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ name, arguments: args });
    const req = http.request({ host: '127.0.0.1', port, path: '/call', method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) } }, res => {
      let data = ''; res.on('data', c => { data += c; }); res.on('end', () => resolve(JSON.parse(data)));
    });
    req.on('error', reject); req.end(body);
  });
}

async function openCard(browser, caps, first) {
  const page = await browser.newPage({ colorScheme: scheme, viewport: { width: W, height: H } });
  const log = { messages: [], calls: [], errors: [], sizes: [] };
  page.on('pageerror', e => log.errors.push(e.message));
  await page.exposeFunction('hostCall', async (name, args) => { log.calls.push({ name, args }); return hostCall(name, args); });
  await page.exposeFunction('logMsg', m => {
    if (m.method === 'ui/message') log.messages.push(m.params);
    if (m.method === 'ui/notifications/size-changed') log.sizes.push(m.params.height);
  });
  // the card, then a conversation's worth of space under it, so the card can scroll out of view and back
  await page.setContent(`<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:${W}px;height:${H}px"></iframe><div style="height:4000px"></div></body>`);
  await page.evaluate(([card, caps, first]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', async e => {
      const m = e.data; window.logMsg(m);
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: caps, hostContext: {} });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: {} } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: first }, '*');
      } else if (m.method === 'tools/call') {
        if (!caps.serverTools) { f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, error: { code: -32601, message: 'no' } }, '*'); return; }
        reply(await window.hostCall(m.params.name, m.params.arguments));
      } else if (m.method === 'ui/message') reply({});
    });
    f.srcdoc = card;
  }, [card, caps, first]);
  await page.frameLocator('#f').locator('main').waitFor({ timeout: 15000 });
  const frame = page.frames().find(x => x !== page.mainFrame());
  return { page, frame, log };
}

async function state(c) {
  const s = await c.frame.evaluate(() => {
    const main = document.querySelector('main'), moved = document.getElementById('moved');
    return { moved: moved.hidden ? '' : moved.textContent, title: document.getElementById('title').textContent,
             visible: Array.from(main.children).filter(x => !x.hidden).length,
             bottom: Math.ceil(main.getBoundingClientRect().bottom) };
  });
  s.latestCalls = c.log.calls.filter(x => x.name === 'start' && (x.args || {}).step === 'latest').map(x => x.args);
  s.startCalls = c.log.calls.filter(x => x.name === 'start').length;
  s.reported = c.log.sizes.length ? c.log.sizes[c.log.sizes.length - 1] : null;
  s.errors = c.log.errors;
  s.messages = c.log.messages.length;
  return s;
}

async function scrollAwayAndBack(c) {
  await c.page.evaluate(() => window.scrollTo(0, 3500));
  await c.page.waitForTimeout(400);
  await c.page.evaluate(() => window.scrollTo(0, 0));
  await c.page.waitForTimeout(1200);
}

(async () => {
  const browser = await chromium.launch();
  const out = {};
  // 1. A live card on Check: its own check on the first answer finds it is the latest, so it stays as it is
  const check = await hostCall('start', { ...B, step: 'check' });
  const a = await openCard(browser, { serverTools: {} }, check);
  await a.page.waitForTimeout(2500);
  out.live = await state(a);
  // 2. The user types; Claude's start call opens a newer card (a separate frame: no channel reaches card A).
  //    Card A comes back into view and folds to one line.
  const decide = await hostCall('start', { ...B, step: 'decide' });
  await a.page.waitForTimeout(2500);                                 // past CHECK_GAP since the first check
  await scrollAwayAndBack(a);
  out.typed = await state(a);
  await a.page.close();
  // 3. A reloaded conversation draws the old Check card again: it folds when its first answer is drawn
  const r = await openCard(browser, { serverTools: {} }, check);
  await r.page.waitForTimeout(2500);
  out.reloaded = await state(r);
  await r.page.close();
  // 4. The newest card's own taps never fold it: Next inside the card, then out of view and back
  const n = await openCard(browser, { serverTools: {} }, decide);
  await n.page.waitForTimeout(1600);
  await n.frame.waitForFunction(() => { const b = document.querySelector('button[data-kind="next"]'); return b && !b.disabled; }, null, { timeout: 30000 });
  await n.frame.click('button[data-kind="next"]');
  await n.frame.waitForFunction(() => document.documentElement.getAttribute('data-busy') !== '1' && !document.querySelector('.wait'), null, { timeout: 60000 });
  await n.page.waitForTimeout(4500);
  await scrollAwayAndBack(n);
  out.own = await state(n);
  await n.page.close();
  // 5. A host that runs no tool from the card: no check is sent, and the stale card stays as before this round
  const t = await openCard(browser, {}, check);
  await t.page.waitForTimeout(2000);
  await scrollAwayAndBack(t);
  out.noTools = await state(t);
  await t.page.close();
  // 6. The synthetic shop sample keeps no flow: no check is sent
  const sample = await hostCall('start', { sample: true });
  const s = await openCard(browser, { serverTools: {} }, sample);
  await s.page.waitForTimeout(2000);
  out.sample = await state(s);
  await s.page.close();
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
