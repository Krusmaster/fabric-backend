// WB15: the guided path clicked through end to end, only with the card's own buttons, the way Gustav used it on his
// phone on 19 November 2026 (claude.ai Android, about 390 px, light and dark). One Start Krusgraph card in a frame under
// a fake host; every tools/call the card makes goes to the real hosted tools on the synthetic SAP demo (the Python side
// of tests/test_wb15_click_through.py answers them over HTTP on 127.0.0.1).
//
// Usage: node wb15_click_through.js <card.html> <port> <scheme> <shots dir or "">
// Prints JSON {steps: [{n, of, title, key, mascot, bottom, scroll}], messages, errors, finalState, dryRuns, confirm, handoff}.
const { chromium } = require('playwright');
const fs = require('fs');
const http = require('http');
const card = fs.readFileSync(process.argv[2], 'utf8');
const port = Number(process.argv[3]);
const scheme = process.argv[4] || 'light';
const shots = process.argv[5] || '';
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

async function openCard(browser, caps, first) {
  const page = await browser.newPage({ colorScheme: scheme, viewport: { width: W, height: H } });
  const log = { messages: [], calls: [], errors: [], sizes: [] };
  page.on('pageerror', e => log.errors.push(e.message));
  await page.exposeFunction('hostCall', async (name, args) => { log.calls.push({ name, args }); return hostCall(name, args); });
  await page.exposeFunction('logMsg', m => {
    if (m.method === 'ui/message') log.messages.push(m.params);
    if (m.method === 'ui/notifications/size-changed') log.sizes.push(m.params.height);
  });
  await page.setContent(`<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:${W}px;height:${H}px"></iframe></body>`);
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
  const fr = page.frameLocator('#f');
  await fr.locator('main').waitFor({ timeout: 15000 });
  await page.waitForTimeout(300);
  const frame = page.frames().find(x => x !== page.mainFrame());
  return { page, fr, frame, log };
}

// What the card shows now: the step in the title, the mascot's size and whether it is visible, where main ends
async function look(c) {
  return c.frame.evaluate(() => {
    const t = document.getElementById('title').textContent.trim();
    const m = /^Step (\d+) of (\d+): (.+?)( \(sample\))?$/.exec(t);
    const fig = document.querySelector('#coach .kg-fig svg');
    const r = fig ? fig.getBoundingClientRect() : null;
    const cs = fig ? getComputedStyle(fig) : null;
    const main = document.querySelector('main');
    return {
      title: t, n: m ? Number(m[1]) : null, of: m ? Number(m[2]) : null, short: m ? m[3] : null,
      mascot: !!(r && r.width >= 60 && r.height >= 60 && cs.visibility !== 'hidden' && !document.getElementById('coach').hidden),
      line: (document.querySelector('#coach .st-line') || {}).textContent || '',
      bottom: Math.ceil(main.getBoundingClientRect().bottom),
      decisions: document.querySelectorAll('.st-decision').length,
      doubled: !!document.querySelector('#answer .res-box ul'),
      dryButtons: Array.from(document.querySelectorAll('#next button[data-kind="dry_run_all"], #next button[data-kind="dry_run"]')).filter(b => b.offsetParent).map(b => b.textContent.trim()),
      chosen: (document.querySelector('.st-chosen') || {}).textContent || '',
      buttons: Array.from(document.querySelectorAll('main button')).filter(b => b.offsetParent && b.innerText.trim()).map(b => b.innerText.trim()),
      confirm: !!document.querySelector('button[data-kind="confirm"]'),
      creates: Array.from(document.querySelectorAll('button.st-create')).map(b => b.textContent.trim()),
      choices: document.querySelectorAll('button[data-kind="choose"]').length,
      map: !!(document.querySelector('#pic-map svg') && !document.getElementById('details').contains(document.getElementById('pictures'))
              && document.querySelector('#pic-map svg').getBoundingClientRect().height > 50),
      text: main.innerText,
    };
  });
}

async function idle(c) {
  await c.frame.waitForFunction(() => document.documentElement.getAttribute('data-busy') !== '1' && !document.querySelector('.wait'), null, { timeout: 60000 });
  await c.page.waitForTimeout(150);
}
async function tap(c, css, text) {
  const loc = text ? c.fr.locator(css, { hasText: text }) : c.fr.locator(css);
  await loc.first().waitFor({ state: 'visible', timeout: 20000 });
  await c.frame.waitForFunction(([css, text]) => {
    const b = Array.from(document.querySelectorAll(css)).find(x => !text || x.textContent.includes(text));
    return b && !b.disabled;
  }, [css, text], { timeout: 30000 });
  await loc.first().click({ timeout: 10000 });
}

(async () => {
  const browser = await chromium.launch();
  const out = { steps: [], errors: [], messages: [] };
  const first = await hostCall('start', {});
  // ---- 1. the host runs tools from the card: the whole path inside ONE card ----
  const c = await openCard(browser, { serverTools: {} }, first);
  const record = async (key) => {
    await idle(c);
    const s = await look(c);
    s.key = key; s.scroll = s.bottom > H;
    out.steps.push(s);
    if (shots) await c.page.screenshot({ path: `${shots}/step-${String(out.steps.length).padStart(2, '0')}-${key}-${scheme}.png`, fullPage: false });
    return s;
  };
  // SM2: five steps. The workspace, the source and the schema each have one usable option, so the first card is
  // "Your data: demo › demo_lh › dbo ✓"; the map, the row check and the doubled totals have run on their own on Check.
  await record('data');
  await tap(c, 'button[data-kind="next"]', 'Next');
  await record('check');
  out.checkText = (await look(c)).text;
  await tap(c, 'button[data-kind="next"]', 'Next');
  await record('decide');
  // Bug E: Accept, Reject, Accept, Reject as fast as the card lets: each tap as soon as its button is back
  const taps = [['Accept'], ['Change to Reject'], ['Change to Accept'], ['Change to Reject']];
  out.tapStates = [];
  for (const [label] of taps) {
    await tap(c, 'button[data-kind="decide"]', label);
    // a second tap on the same place while the call runs: the buttons are off, so it is not sent
    const extra = await c.frame.evaluate(() => Array.from(document.querySelectorAll('button[data-kind="decide"]')).every(b => b.disabled));
    out.tapStates.push({ label, offWhileRunning: extra });
    await idle(c);
  }
  out.decisionShown = await c.frame.evaluate(() => (document.querySelector('.st-decision') || {}).getAttribute('data-state'));
  await tap(c, 'button[data-kind="next"]', 'Next');
  await record('dry_run');
  out.dryDetails = await c.frame.evaluate(() => document.getElementById('more').textContent);
  await tap(c, 'button[data-kind="dry_run_all"]', 'Dry run everything');
  await idle(c);
  out.dryLines = await c.frame.evaluate(() => Array.from(document.querySelectorAll('#next .st-lines p')).map(p => p.textContent.trim()));
  out.dryRuns = await c.frame.evaluate(() => {
    const o = {};
    for (const [tool, label] of [['create_pipeline', 'Dry run: silver and gold'], ['create_semantic_model', 'Dry run: semantic model'], ['create_data_agent', 'Dry run: data agent']]) {
      const sec = document.querySelector(`#more section.st-dryout[data-tool="${tool}"]`);
      o[label] = sec ? sec.textContent : '';
    }
    return o;
  });
  const after = await look(c);
  after.key = 'dry_runs_done'; after.scroll = after.bottom > H; out.steps.push(after);
  if (shots) await c.page.screenshot({ path: `${shots}/dry-runs-${scheme}.png`, fullPage: false });
  await tap(c, 'button[data-kind="next"]', 'Next');
  await record('create');
  await tap(c, 'button[data-kind="confirm"]', 'Confirm');
  await record('confirmed');
  await tap(c, 'button[data-kind="next"]', 'Next');
  await record('done');
  out.calls = c.log.calls.map(x => ({ name: x.name, step: (x.args || {}).step || '', dry_run: (x.args || {}).dry_run }));
  out.messages = c.log.messages;
  out.errors = c.log.errors;
  await c.page.close();

  // ---- 2. a host that runs no tool from the card: plain words to the chat, and the card folds to one line ----
  const h = await openCard(browser, {}, first);
  await tap(h, 'button[data-kind="next"]', 'Next');
  await h.page.waitForTimeout(400);
  const folded = await h.frame.evaluate(() => {
    const main = document.querySelector('main'), moved = document.getElementById('moved');
    return { moved: !moved.hidden ? moved.textContent : '', bottom: Math.ceil(main.getBoundingClientRect().bottom),
             visible: Array.from(main.children).filter(x => !x.hidden).length };
  });
  folded.reported = h.log.sizes.length ? h.log.sizes[h.log.sizes.length - 1] : null;
  folded.messages = h.log.messages;
  folded.errors = h.log.errors;
  await h.page.close();
  // every other kind of button on a host without tools: what it would put in the chat
  const said = [];
  for (const args of [{ workspace: 'demo', source: 'demo_lh', schema: 'dbo', step: 'decide' },
                      { workspace: 'demo', source: 'demo_lh', schema: 'dbo', step: 'done' },
                      { workspace: 'demo', source: 'demo_lh', schema: 'dbo', step: 'dry_run' },
                      { workspace: 'demo', source: 'demo_lh', schema: 'dbo', step: 'create' }]) {
    const r = await hostCall('start', args);
    const k = await openCard(browser, {}, r);
    const n = await k.frame.evaluate(() => document.querySelectorAll('main button[data-tool]').length);
    for (let i = 0; i < n; i++) {
      const k2 = i === 0 ? k : await openCard(browser, {}, r);
      const b = k2.fr.locator('main button[data-tool]').nth(i);
      if (await b.isVisible() && await b.isEnabled()) { await b.click(); await k2.page.waitForTimeout(250); }
      said.push(...k2.log.messages.map(m => (m.content && m.content[0] && m.content[0].text) || ''));
      said.push(...(await k2.frame.evaluate(() => Array.from(document.querySelectorAll('.out')).map(o => o.textContent))));
      await k2.page.close();
    }
  }
  out.handoff = { ...folded, said };
  await browser.close();
  process.stdout.write(JSON.stringify(out));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
