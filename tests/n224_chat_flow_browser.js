// n224: the data flow in the Try-a-demo chat (moved from the home page's replay card), at 375, 768, 1280 and 1440 px,
// light and dark, with and without reduced motion: the chat starts with clickable suggestions, "See the data flow" is
// offered after the scan, its boxes are the engine's and stay inside the chat's bubble, a box opens its code, the page
// has no horizontal scroll and no console error, and the home page's replay card has no flow.
// Usage: node tests/n224_chat_flow_browser.js <base url>
const { chromium } = require('playwright');
const base = process.argv[2];
const SIZES = [[375, 812], [768, 1024], [1280, 720], [1440, 900]];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(page, fn, arg, what) {
  for (let i = 0; i < 300; i++) { if (await page.evaluate(fn, arg)) return; await wait(50); }
  throw new Error('timeout: ' + (what || arg));
}
const picks = (page) => page.evaluate(() => [...document.querySelectorAll('.kgc-picks .kgc-pick')].map((b) => b.getAttribute('data-pick')));
async function click(page, label) {
  await until(page, (l) => [...document.querySelectorAll('.kgc-picks .kgc-pick')].some((b) => b.getAttribute('data-pick') === l), label);
  await page.evaluate((l) => [...document.querySelectorAll('.kgc-picks .kgc-pick')].find((b) => b.getAttribute('data-pick') === l).click(), label);
}
(async () => {
  const browser = await chromium.launch();
  const out = { errors: [], sizes: {} };
  for (const [width, height] of SIZES) for (const scheme of ['light', 'dark']) for (const motion of ['reduce', 'no-preference']) {
    const key = `${width}-${scheme}-${motion}`;
    const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, reducedMotion: motion });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => out.errors.push(`${key}: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(`${key}: ${m.text()}`); });
    await page.goto(base + '/', { waitUntil: 'networkidle' });
    const s = {};
    s.cardFlow = await page.evaluate(() => document.querySelectorAll('figure.session .session-flow, figure.session svg').length);
    await until(page, () => { const b = document.getElementById('kgcLaunch'); return b && !b.hidden; }, null, 'launch');
    await page.click('#kgcLaunch');
    await until(page, () => document.querySelectorAll('.kgc-picks .kgc-pick').length > 0, null, 'first picks');
    s.firstPicks = await picks(page);
    await click(page, 'Check the tables');
    await click(page, 'No, leave it out');
    await until(page, (l) => [...document.querySelectorAll('.kgc-picks .kgc-pick')].some((b) => b.getAttribute('data-pick') === l), 'See the data flow');
    s.offered = await picks(page);
    await click(page, 'See the data flow');
    await until(page, () => !!document.querySelector('.kgc-log .kgf.kgc-flow'), null, 'flow');
    await until(page, () => document.querySelectorAll('.kgc-picks .kgc-pick').length > 0, null, 'next picks');
    s.afterNext = (await picks(page)).length > 0;
    Object.assign(s, await page.evaluate(() => {
      const f = document.querySelector('.kgc-log .kgf.kgc-flow'), bub = f.closest('.kgc-bub').getBoundingClientRect();
      const boxes = [...f.querySelectorAll('.kgf-box')];
      const bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g).map(Number);
      return { heads: [...f.querySelectorAll('.kgf-h')].map((h) => h.textContent),
               boxes: boxes.map((b) => b.querySelector('.kgf-n').textContent),
               inBubble: boxes.every((b) => { const r = b.getBoundingClientRect(); return r.left >= bub.left - 1 && r.right <= bub.right + 1; }),
               overflow: document.documentElement.scrollWidth - innerWidth, dark: (bg[0] + bg[1] + bg[2]) / 3 < 80 };
    }));
    const silver = await page.evaluateHandle(() => [...document.querySelectorAll('.kgc-flow button.kgf-box')].find((b) => /^silver\./.test(b.textContent)));
    await silver.asElement().click();
    Object.assign(s, await page.evaluate(() => {
      const b = [...document.querySelectorAll('.kgc-flow button.kgf-box')].find((x) => x.getAttribute('aria-expanded') === 'true');
      const p = b && document.getElementById(b.getAttribute('aria-controls'));
      return { opened: !!(p && !p.hidden), openedCode: p ? p.textContent : '', overflow2: document.documentElement.scrollWidth - innerWidth };
    }));
    s.overflow = Math.max(s.overflow, s.overflow2); delete s.overflow2;
    out.sizes[key] = s;
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
