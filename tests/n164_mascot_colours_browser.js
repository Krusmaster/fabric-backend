// Round n164: which colour each mascot wears on the rendered site, in Chromium, light and dark. Prints JSON facts for
// tests/test_n164_mascot_colours.py: in the chat demo (opened from the start page's button, then "Check the tables" and
// "Yes, add the link", so Thinker, Onto and Builder all speak) each message's name colour and the figure's body colour;
// on /mascots each heading's pill colour and each figure's body colour; and the site's tokens (--onto, --thinker,
// --builder with their -soft and -ink variants, and the palette they point at) as the page computes them.
// Usage: node n164_mascot_colours_browser.js <base> [<chromium>]
const { chromium } = require('playwright');

const [base, exe] = process.argv.slice(2);
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(page, fn, arg, what) {           // the pages' CSP has no 'unsafe-eval': poll instead of waitForFunction
  for (let i = 0; i < 300; i++) { if (await page.evaluate(fn, arg)) return; await wait(50); }
  throw new Error('timeout: ' + (what || arg));
}
const TOKENS = ['onto', 'thinker', 'builder'].flatMap((k) => ['', '-soft', '-ink'].map((v) => '--' + k + v))
  .concat(['sage', 'lav', 'coral'].flatMap((k) => ['', '-soft', '-ink'].map((v) => '--' + k + v)));
// a colour as the browser computes it: rgb(...) for any CSS colour value
const tokens = (page) => page.evaluate((names) => {
  const probe = document.createElement('span'); document.body.appendChild(probe);
  const out = {};
  for (const n of names) { probe.style.color = 'var(' + n + ')'; out[n] = getComputedStyle(probe).color; }
  probe.remove();
  return out;
}, TOKENS);
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = {};
  for (const scheme of ['light', 'dark']) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, colorScheme: scheme });
    const errors = [];
    page.on('pageerror', (e) => errors.push(String(e)));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

    // ---- the chat demo
    await page.goto(base + '/start');
    await until(page, () => { const b = document.getElementById('kgcLaunch'); return b && !b.hidden; }, null, 'launcher');
    await page.click('#kgcLaunch');
    const pick = async (label) => {
      await until(page, (l) => [...document.querySelectorAll('.kgc-pick')].some((b) => b.getAttribute('data-pick') === l && b.getAttribute('aria-disabled') !== 'true'), label);
      await page.evaluate((l) => [...document.querySelectorAll('.kgc-pick')].filter((b) => b.getAttribute('data-pick') === l).pop().click(), label);
    };
    await pick('Check the tables');
    await pick('Yes, add the link');
    await until(page, () => !!document.querySelector('.kgc-msg.builder'), null, 'builder speaks');
    await wait(400);
    const chat = await page.evaluate(() => {
      const fill = (svg) => {   // the middle stop of a figure's body gradient is its fill (mascots.js)
        const ref = (svg.querySelector('.m-body path').getAttribute('fill') || '').match(/url\(#(.+)\)/);
        if (!ref) return svg.querySelector('.m-body path').getAttribute('fill');
        return svg.querySelector('#' + CSS.escape(ref[1]) + ' stop:nth-child(2)').getAttribute('stop-color');
      };
      return [...document.querySelectorAll('.kgc-msg')].map((m) => ({
        kind: ['onto', 'thinker', 'builder'].find((k) => m.classList.contains(k)),
        who: m.querySelector('.kgc-who').textContent,
        whoColour: getComputedStyle(m.querySelector('.kgc-who')).color,
        figure: m.querySelector('svg.mascot') ? m.querySelector('svg.mascot').getAttribute('data-kind') : null,
        fill: m.querySelector('svg.mascot') ? fill(m.querySelector('svg.mascot')) : null,
        label: m.querySelector('svg.mascot') ? (m.querySelector('svg.mascot').getAttribute('aria-label') || '') : '' }));
    });
    const head = await page.evaluate(() => {
      const fill = (svg) => {   // the middle stop of a figure's body gradient is its fill (mascots.js)
        const ref = (svg.querySelector('.m-body path').getAttribute('fill') || '').match(/url\(#(.+)\)/);
        if (!ref) return svg.querySelector('.m-body path').getAttribute('fill');
        return svg.querySelector('#' + CSS.escape(ref[1]) + ' stop:nth-child(2)').getAttribute('stop-color');
      };
      const s = document.querySelector('.kgc-head svg.mascot');
      return s ? { kind: s.getAttribute('data-kind'), fill: fill(s) } : null;
    });
    const chatTokens = await tokens(page);

    // ---- /mascots
    await page.goto(base + '/mascots');
    await until(page, () => document.querySelectorAll('#grid-builder svg.mascot').length > 0, null, 'mascots grid');
    const review = await page.evaluate(() => {
      const fill = (svg) => {   // the middle stop of a figure's body gradient is its fill (mascots.js)
        const ref = (svg.querySelector('.m-body path').getAttribute('fill') || '').match(/url\(#(.+)\)/);
        if (!ref) return svg.querySelector('.m-body path').getAttribute('fill');
        return svg.querySelector('#' + CSS.escape(ref[1]) + ' stop:nth-child(2)').getAttribute('stop-color');
      };
      const grids = {};
      for (const k of ['onto', 'thinker', 'builder']) {
        const g = document.getElementById('grid-' + k), h = g.previousElementSibling.previousElementSibling;
        grids[k] = { heading: h.textContent.replace(/\s+/g, ' ').trim(), pill: h.querySelector('.pill').className,
                     pillBg: getComputedStyle(h.querySelector('.pill')).backgroundColor,
                     pillInk: getComputedStyle(h.querySelector('.pill')).color,
                     fills: [...new Set([...g.querySelectorAll('svg.mascot')].map(fill))],
                     labels: [...g.querySelectorAll('svg.mascot')].slice(0, 1).map((s) => s.getAttribute('aria-label')) };
      }
      return grids;
    });
    out[scheme] = { chat, head, tokens: chatTokens, review, errors };
    await page.close();
  }
  console.log(JSON.stringify(out));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
