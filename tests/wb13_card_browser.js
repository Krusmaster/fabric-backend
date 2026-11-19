// WB13: a card in Chromium under a fake host, in a frame much taller than its content (4000 px) (Gustav's phone test of 19 Nov
// 2026: a full phone screen of blank space under the cards, issue #89). After the answer is drawn and after each click
// (a details opened or closed, a button), it records the last height the card reported with
// ui/notifications/size-changed next to where its content ends (main's bottom edge).
// Usage: node wb13_card_browser.js <card.html> <data.json>
// data.json: {result, caps, reply, width, scheme, frame (the frame's height, default 4000), clicks: [{css, nth?, text?}], shot?}
// Prints JSON {phases: [{reported, content, frame}], overflow, text, buttons, order, errors, log, background}.
const { chromium } = require('playwright');
const fs = require('fs');
const card = fs.readFileSync(process.argv[2], 'utf8');
const data = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
(async () => {
  const browser = await chromium.launch();
  const width = data.width || 390;
  const page = await browser.newPage({ colorScheme: data.scheme || 'light', viewport: { width: width + 20, height: data.viewport || 900 } });
  const log = [], errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.exposeFunction('logMsg', m => log.push(m));
  await page.setContent(`<body style="margin:0"><iframe id="f" sandbox="allow-scripts" style="border:0;width:${width}px;height:${data.frame || 4000}px"></iframe></body>`);
  await page.evaluate(([card, data]) => {
    const f = document.getElementById('f');
    window.addEventListener('message', e => {
      const m = e.data; window.logMsg(m);
      const reply = r => f.contentWindow.postMessage({ jsonrpc: '2.0', id: m.id, result: r }, '*');
      if (m.method === 'ui/initialize') reply({ protocolVersion: '2026-01-26', hostCapabilities: data.caps || {}, hostContext: { theme: data.scheme || 'light' } });
      else if (m.method === 'ui/notifications/initialized') {
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-input', params: { arguments: data.args || {} } }, '*');
        f.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: data.result }, '*');
      } else if (m.method === 'tools/call') setTimeout(() => reply(data.reply || { content: [{ type: 'text', text: '{"summary": "done"}' }] }), 20);
      else if (m.method === 'ui/message') reply({});
    });
    f.srcdoc = card;
  }, [card, data]);
  const fr = page.frameLocator('#f');
  await fr.locator('main').waitFor({ timeout: 10000 });
  await page.waitForTimeout(500);
  const frame = page.frames().find(x => x !== page.mainFrame());
  const sizes = () => log.filter(m => m.method === 'ui/notifications/size-changed').map(m => m.params);
  const measure = async () => {
    const m = await frame.evaluate(() => {
      const main = document.querySelector('main');
      return { content: Math.ceil(main.getBoundingClientRect().bottom + window.scrollY), frame: window.innerHeight };
    });
    const s = sizes();
    return { ...m, reported: s.length ? s[s.length - 1].height : null, reports: s.length };
  };
  const phases = [await measure()];
  for (const c of data.clicks || []) {
    const loc = c.text ? fr.locator(c.css || 'button', { hasText: c.text }) : fr.locator(c.css);
    await loc.nth(c.nth || 0).click({ timeout: 10000 });
    await page.waitForTimeout(350);
    phases.push({ ...(await measure()), click: c.css || c.text });
  }
  const info = await frame.evaluate(() => {
    const m = document.querySelector('main'), de = document.documentElement;
    const top = el => el ? Math.round(el.getBoundingClientRect().top) : null;
    const firstButton = Array.from(m.querySelectorAll('button')).find(b => b.offsetParent !== null && !b.closest('.kg-head') && !b.closest('.kg-say') && !/mascot|Hide|Show Onto/i.test(b.textContent));
    const big = Array.from(m.querySelectorAll('svg.kgc-svg, figure.onto-fig, table.ck-table, .res-file')).filter(x => x.offsetParent !== null)[0];
    return {
      overflow: de.scrollWidth > de.clientWidth + 1,
      background: getComputedStyle(document.body).backgroundColor,
      text: m.innerText,
      buttons: Array.from(m.querySelectorAll('button')).filter(b => b.offsetParent !== null)
        .map(b => ({ text: b.textContent.trim(), primary: b.getAttribute('data-primary') === 'true', kind: b.getAttribute('data-kind') || '' })),
      order: { firstButton: firstButton ? firstButton.textContent.trim() : null, firstButtonTop: top(firstButton), bigTop: top(big) },
      details: Array.from(m.querySelectorAll('details > summary')).filter(s => s.offsetParent !== null).map(s => s.textContent.trim()),
      pre: Array.from(m.querySelectorAll('pre.res-file-pre')).map(p => ({ open: !!p.closest('details[open]'), ws: getComputedStyle(p).whiteSpace, scroll: p.scrollWidth > p.clientWidth })),
    };
  });
  if (data.shot) await page.screenshot({ path: data.shot, clip: { x: 0, y: 0, width, height: Math.min(4000, phases[phases.length - 1].content + 20) } });
  await browser.close();
  process.stdout.write(JSON.stringify({ phases, ...info, errors, log: log.filter(m => m.method !== 'ui/notifications/size-changed') }));
})().catch(e => { process.stderr.write(String(e && e.stack || e)); process.exit(1); });
