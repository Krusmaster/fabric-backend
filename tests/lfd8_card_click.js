// LFD8: the diff card for propose_change, clicked in Chromium under a fake host (the wb15 pattern: tests/wb15_click_through.js).
// Every tools/call the card makes goes to the Python side over HTTP on 127.0.0.1 (tools/smooth_measure.py, change_run),
// which answers propose_change with the product's own code on the synthetic shop_lfd sample and records apply_change.
// Nothing reaches Fabric.
//
// Usage: node lfd8_card_click.js <card.html> <port> <scheme: light|dark> <states.json> <shots dir or "">
// states.json: [{name, result, clicks: [{kind, text?}], caps?}]. A click taps the first visible button with that
// data-kind (and text), even a disabled one (a disabled button runs nothing), or opens a fold ({kind: "fold", text}).
// Prints JSON [{name, scheme, steps: [measure], calls: [{name, args}], messages: [text], errors}], one measure per state
// the card shows: words outside the buttons (closed folds excluded), buttons, primaries, enabled buttons, the widest
// content against 390 px, and the contrast of the text on the background.
const { chromium } = require('playwright');
const fs = require('fs');
const http = require('http');
const [card, port, scheme, states, shots] = [fs.readFileSync(process.argv[2], 'utf8'), Number(process.argv[3]),
  process.argv[4] || 'light', JSON.parse(fs.readFileSync(process.argv[5], 'utf8')), process.argv[6] || ''];
const W = 390, H = 800;

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

async function open(browser, state) {
  const page = await browser.newPage({ colorScheme: scheme, viewport: { width: W, height: H }, deviceScaleFactor: shots ? 2 : 1 });
  const log = { calls: [], messages: [], errors: [] };
  page.on('pageerror', e => log.errors.push(e.message));
  await page.exposeFunction('hostCall', async (name, args) => { log.calls.push({ name, args }); return hostCall(name, args); });
  await page.exposeFunction('logChat', t => { log.messages.push(t); });
  const caps = state.caps || { serverTools: {} };
  await page.setContent(`<body style="margin:0;background:Canvas"><iframe id="f" sandbox="allow-scripts" style="border:0;width:${W}px;height:${H}px"></iframe></body>`);
  await page.evaluate(([card, caps, first]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', async e => {
      const m = e.data;
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: caps, hostContext: {} });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: {} } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: first }, '*');
      } else if (m.method === 'tools/call') {
        if (!caps.serverTools) { f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, error: { code: -32601, message: 'no' } }, '*'); return; }
        reply(await window.hostCall(m.params.name, m.params.arguments));
      } else if (m.method === 'ui/message') {
        const c = m.params.content; window.logChat(Array.isArray(c) ? c.map(x => x.text).join('') : c.text); reply({});
      }
    });
    f.srcdoc = card;
  }, [card, caps, state.result]);
  await page.frameLocator('#f').locator('main').waitFor({ timeout: 15000 });
  const frame = page.frames().find(x => x !== page.mainFrame());
  await frame.waitForFunction(() => document.getElementById('line').textContent !== 'Waiting for the proposal.', null, { timeout: 15000 });
  return { page, frame, log };
}

async function idle(c) {
  await c.frame.waitForFunction(() => document.documentElement.getAttribute('data-busy') !== '1', null, { timeout: 60000 });
  await c.page.waitForTimeout(150);
}

async function measure(c, key) {
  const s = await c.frame.evaluate(() => {
    const main = document.querySelector('main');
    const words = t => (t.match(/[\p{L}\p{N}][\p{L}\p{N}'’.+_\-→>]*/gu) || []).length;
    const btns = Array.from(main.querySelectorAll('button')).filter(b => b.offsetParent !== null && b.innerText.trim());
    const btnWords = btns.reduce((n, b) => n + words(b.innerText), 0);
    const rgb = s => (s.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
    const lum = c => { const v = c.map(x => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
      return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
    const cs = getComputedStyle(document.body);
    const fg = lum(rgb(cs.color)), bg = lum(rgb(cs.backgroundColor));
    const primary = btns.filter(b => b.getAttribute('data-primary') === 'true');
    return {
      line: document.getElementById('line').textContent.trim(), result: document.documentElement.getAttribute('data-result') || '',
      text: main.innerText, words: words(main.innerText) - btnWords, buttons: btns.map(b => ({ kind: b.getAttribute('data-kind'),
        label: b.innerText.trim(), disabled: b.disabled, primary: b.getAttribute('data-primary') === 'true', title: b.title })),
      primaries: primary.length, enabled: btns.filter(b => !b.disabled).length,
      width: Math.max(document.documentElement.scrollWidth, main.scrollWidth), bottom: Math.ceil(main.getBoundingClientRect().bottom),
      contrast: +((Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05)).toFixed(2), background: cs.backgroundColor, ink: cs.color,
      folds: Array.from(main.querySelectorAll('#body > details > summary')).map(x => x.textContent.trim()),
      out: (document.getElementById('out').hidden ? '' : document.getElementById('out').textContent.trim()),
    };
  });
  s.key = key;
  return s;
}

(async () => {
  const browser = await chromium.launch();
  const out = [];
  for (const state of states) {
    const c = await open(browser, state);
    const run = { name: state.name, scheme, steps: [] };
    await idle(c);
    run.steps.push(await measure(c, 'shown'));
    if (shots && state.shot) await c.page.screenshot({ path: `${shots}/${state.name}-${W}-${scheme}.png` });
    let n = 0;
    for (const click of state.clicks || []) {
      n += 1;
      if (click.kind === 'fold') {
        await c.frame.evaluate(t => { const s = Array.from(document.querySelectorAll('details > summary')).find(x => x.textContent.trim() === t && x.offsetParent);
          if (s) s.parentElement.open = true; }, click.text);
      } else {
        const ok = await c.frame.evaluate(([k, t]) => {
          const b = Array.from(document.querySelectorAll('#buttons button')).find(x => x.getAttribute('data-kind') === k && (!t || x.innerText.includes(t)) && x.offsetParent);
          if (!b) return false; b.click(); return true;
        }, [click.kind, click.text || '']);
        if (!ok) run.steps.push({ key: `missing ${click.kind} ${click.text || ''}`, missing: true });
      }
      await idle(c);
      run.steps.push(await measure(c, `${click.kind}${click.text ? ':' + click.text : ''}`));
      if (shots && click.shot) await c.page.screenshot({ path: `${shots}/${state.name}-${click.shot}-${W}-${scheme}.png`, fullPage: true });
    }
    run.calls = c.log.calls; run.messages = c.log.messages; run.errors = c.log.errors;
    out.push(run);
    await c.page.close();
  }
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
