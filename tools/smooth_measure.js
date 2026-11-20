// Round SM1: measure the guided path the way docs/SMOOTH/AUDIT.md reports it. One Start Krusgraph card under a fake
// host (the same seams as tests/wb15_click_through.js); every tools/call goes to the real hosted tools on the synthetic
// SAP demo, answered by tools/smooth_measure.py over HTTP on 127.0.0.1. Nothing reaches Fabric.
//
// Two paths, each at one viewport:
//   careful: the WB15 click list (tap the choices, run the check, decide the link, find doubled totals, three dry runs)
//   lazy:    only the primary button of each step (Next), then the three dry runs
// Per step it records: seconds since the card opened, taps so far, the words a person sees (closed folds excluded,
// button labels counted apart), the number of visible buttons, and whether the step scrolls.
//
// Usage: node smooth_measure.js <card.html> <port> <width> <height> <path: careful|lazy> <shots dir or "">
const { chromium } = require('playwright');
const fs = require('fs');
const http = require('http');
const [card, port, W, H, which, shots] = [fs.readFileSync(process.argv[2], 'utf8'), Number(process.argv[3]),
  Number(process.argv[4]), Number(process.argv[5]), process.argv[6] || 'careful', process.argv[7] || ''];

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

(async () => {
  const browser = await chromium.launch();
  const t0 = Date.now();
  const first = await hostCall('start', {});
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: shots ? 2 : 1 });
  const calls = [];
  await page.exposeFunction('hostCall', async (name, args) => {
    const s = Date.now(); const r = await hostCall(name, args);
    calls.push({ name, step: (args || {}).step || '', ms: Date.now() - s }); return r;
  });
  await page.setContent(`<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:${W}px;height:${H}px"></iframe></body>`);
  await page.evaluate(([card, first]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', async e => {
      const m = e.data;
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: { serverTools: {} }, hostContext: {} });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: {} } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: first }, '*');
      } else if (m.method === 'tools/call') reply(await window.hostCall(m.params.name, m.params.arguments));
      else if (m.method === 'ui/message') reply({});
    });
    f.srcdoc = card;
  }, [card, first]);
  const fr = page.frameLocator('#f');
  await fr.locator('main').waitFor({ timeout: 15000 });
  const frame = page.frames().find(x => x !== page.mainFrame());
  let taps = 0;
  const steps = [];
  const idle = async () => {
    await frame.waitForFunction(() => document.documentElement.getAttribute('data-busy') !== '1' && !document.querySelector('.wait'), null, { timeout: 60000 });
    await page.waitForTimeout(120);
  };
  const tap = async (css, text) => {
    const loc = text ? fr.locator(css, { hasText: text }) : fr.locator(css);
    await loc.first().waitFor({ state: 'visible', timeout: 20000 });
    await frame.waitForFunction(([css, text]) => {
      const b = Array.from(document.querySelectorAll(css)).find(x => !text || x.textContent.includes(text));
      return b && !b.disabled;
    }, [css, text], { timeout: 30000 });
    await loc.first().click({ timeout: 10000 });
    taps += 1;
    await idle();
  };
  const record = async (key) => {
    await idle();
    const s = await frame.evaluate(() => {
      const main = document.querySelector('main');
      const words = t => (t.match(/[\p{L}\p{N}][\p{L}\p{N}'’.+_\-→>]*/gu) || []).length;
      const btns = Array.from(main.querySelectorAll('button')).filter(b => b.offsetParent !== null);
      const btnWords = btns.reduce((n, b) => n + words(b.innerText), 0);
      return { title: document.getElementById('title').textContent.trim(),
               line: ((document.querySelector('#coach .st-line') || {}).textContent || '').trim(),
               words: words(main.innerText) - btnWords, buttonWords: btnWords, buttons: btns.length,
               bottom: Math.ceil(main.getBoundingClientRect().bottom) };
    });
    s.key = key; s.taps = taps; s.seconds = +((Date.now() - t0) / 1000).toFixed(2); s.scroll = s.bottom > H;
    steps.push(s);
    if (shots) await page.screenshot({ path: `${shots}/${which}-${W}-${String(steps.length).padStart(2, '0')}-${key}.png` });
  };
  await record('workspace');
  if (which === 'shop') {
    // the synthetic shop sample: tap the sample button, then the primary button of each step, every dry run on the way
    await tap('button[data-kind="sample"]');
    for (let i = 0; i < 12; i++) {
      const key = await frame.evaluate(() => document.getElementById('title').textContent.trim());
      await record(key.replace(/^Step \d+ of \d+: /, '').replace(/ \(sample\)$/, '').toLowerCase().replace(/\W+/g, '_'));
      const dry = await frame.evaluate(() => Array.from(document.querySelectorAll('button[data-kind="dry_run"]')).map(b => b.textContent.trim()));
      for (const label of dry) await tap('button[data-kind="dry_run"]', label);
      if (dry.length) await record('dry_runs_done');
      const next = await frame.evaluate(() => { const b = document.querySelector('button[data-kind="next"]'); return !!(b && !b.disabled && b.offsetParent); });
      if (!next) break;
      await tap('button[data-kind="next"]');
    }
    await browser.close();
    process.stdout.write(JSON.stringify({ path: which, width: W, steps, calls }));
    return;
  }
  if (which === 'careful') {
    await tap('button[data-kind="choose"]', 'demo'); await record('source');
    await tap('button[data-kind="choose"]', 'demo_lh'); await record('schema');
    await tap('button[data-kind="next"]', 'Next'); await record('map');
    await tap('button[data-kind="next"]', 'Next'); await record('check');
    await tap('button[data-tool="validate_plan"]', 'Check');
    await tap('button[data-kind="next"]', 'Next'); await record('decide');
    await tap('button[data-kind="decide"]', 'Accept');
    await tap('button[data-kind="next"]', 'Next'); await record('totals');
    await tap('button[data-tool="validate_plan"]', 'Find doubled totals');
    await tap('button[data-kind="next"]', 'Next'); await record('dry_run');
  } else {
    for (const key of ['source', 'schema', 'map', 'check', 'decide', 'totals', 'dry_run']) {
      await tap('button[data-kind="next"]', 'Next'); await record(key);
    }
  }
  for (const label of ['Dry run: silver and gold', 'Dry run: semantic model', 'Dry run: data agent']) {
    await tap('button[data-kind="dry_run"]', label);
  }
  await record('dry_runs_done');
  if (shots) await page.screenshot({ path: `${shots}/${which}-${W}-dry-runs-full.png`, fullPage: true });
  await tap('button[data-kind="next"]', 'Next'); await record('create');
  await tap('button[data-kind="confirm"]', 'Confirm'); await record('confirmed');
  await browser.close();
  process.stdout.write(JSON.stringify({ path: which, width: W, steps, calls }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
