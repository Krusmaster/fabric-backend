// n224: the data flow in the Try-a-demo chat (moved from the home page's replay card), at 375, 768, 1280 and 1440 px,
// light and dark, with and without reduced motion: the chat starts with clickable suggestions, "See the data flow" is
// offered after the scan, its boxes are the engine's and stay inside the chat's bubble, a box opens its code, the page
// has no horizontal scroll and no console error, and the home page's replay card has no flow.
// n233: left to right. The columns sit side by side (each box right of the one it reads, lines between them), scroll
// sideways inside the card (the hint shows when they do, the arrow keys scroll), "Open larger" shows the same boxes over
// the page with no sideways scroll at 1280 px and up, Esc returns the focus, and the screen-reader list says the flow
// in order.
// Usage: node tests/n224_chat_flow_browser.js <base url>
const { chromium } = require('playwright');
const { open } = require('./browser_nav');
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
    await open(page, base + '/', '[data-page="home"]');
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
    await until(page, () => !!document.querySelector('.kgc-log .kgd.kgc-flow'), null, 'flow');
    await until(page, () => document.querySelectorAll('.kgc-picks .kgc-pick').length > 0, null, 'next picks');
    s.afterNext = (await picks(page)).length > 0;
    Object.assign(s, await page.evaluate(() => {
      const f = document.querySelector('.kgc-log .kgd.kgc-flow'), bub = f.closest('.kgc-bub').getBoundingClientRect();
      const sc = f.querySelector('.kgd-scroll'), scr = sc.getBoundingClientRect();
      const boxes = [...f.querySelectorAll('.kgd-box')];
      const x = (id) => f.querySelector(`[data-node="${id}"]`).getBoundingClientRect();
      const mid = (r) => (r.top + r.bottom) / 2;
      const bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g).map(Number);
      return { heads: [...f.querySelectorAll('.kgd-h')].map((h) => h.textContent),
               boxes: boxes.map((b) => b.querySelector('.kgd-n').textContent),
               // the scrolling part stays inside the bubble; the boxes scroll inside it
               inBubble: scr.left >= bub.left - 1 && scr.right <= bub.right + 1,
               // left to right: each column right of the one before, a silver box level with the bronze one it reads
               ltr: x('bronze:orders').right < x('silver:orders').left && x('silver:orders').right < x('gold:gold.orders').left &&
                    x('gold:gold.orders').right < x('item:semantic_model').left && Math.abs(mid(x('bronze:orders')) - mid(x('silver:orders'))) < 2,
               lines: f.querySelectorAll('svg.kgd-lines path.kgd-e').length,
               scrolls: sc.scrollWidth > sc.clientWidth,
               hint: !f.querySelector('.kgd-hint').hidden,
               sr: [...f.querySelectorAll('ol.visually-hidden li')].map((l) => l.textContent),
               overflow: document.documentElement.scrollWidth - innerWidth, dark: (bg[0] + bg[1] + bg[2]) / 3 < 80 };
    }));
    // the arrow keys scroll the columns when the diagram has the focus
    await page.focus('.kgc-flow .kgd-scroll');
    for (let i = 0; i < 4; i++) await page.keyboard.press('ArrowRight');
    await wait(motion === 'reduce' ? 50 : 700);
    s.keyScroll = await page.evaluate(() => document.querySelector('.kgc-flow .kgd-scroll').scrollLeft);
    await page.evaluate(() => { document.querySelector('.kgc-flow .kgd-scroll').scrollLeft = 0; });
    const silver = await page.evaluateHandle(() => [...document.querySelectorAll('.kgc-flow button.kgd-box')].find((b) => /^silver\./.test(b.textContent)));
    await silver.asElement().click();
    Object.assign(s, await page.evaluate(() => {
      const b = [...document.querySelectorAll('.kgc-flow button.kgd-box')].find((x) => x.getAttribute('aria-expanded') === 'true');
      const p = b && document.getElementById(b.getAttribute('aria-controls'));
      return { opened: !!(p && !p.hidden), openedCode: p ? p.textContent : '', overflow2: document.documentElement.scrollWidth - innerWidth };
    }));
    s.overflow = Math.max(s.overflow, s.overflow2); delete s.overflow2;
    // Open larger: the same boxes over the page; Esc closes it and gives the focus back to the button
    await page.click('.kgc-flow .kgd-larger');
    await until(page, () => !!document.querySelector('.kgd-big .kgd-box'), null, 'larger');
    await wait(100);
    Object.assign(s, await page.evaluate(() => {
      const g = document.querySelector('.kgd-big'), sc = g.querySelector('.kgd-scroll');
      return { bigBoxes: [...g.querySelectorAll('.kgd-box .kgd-n')].map((n) => n.textContent),
               bigFits: sc.scrollWidth <= sc.clientWidth + 1, bigFocus: document.activeElement.textContent,
               bigLines: g.querySelectorAll('path.kgd-e').length, overflow3: document.documentElement.scrollWidth - innerWidth };
    }));
    s.overflow = Math.max(s.overflow, s.overflow3); delete s.overflow3;
    await page.click('.kgd-big button.kgd-box[data-node="gold:gold.orders"]');
    s.bigOpened = await page.evaluate(() => { const p = document.querySelector('.kgd-big .kgd-code'); return !p.hidden && /CREATE MATERIALIZED LAKE VIEW/.test(p.textContent); });
    await page.keyboard.press('Escape');
    await wait(100);
    Object.assign(s, await page.evaluate(() => ({ bigClosed: !document.querySelector('.kgd-big') && !document.getElementById('kgcBox').hidden,
                                                  backTo: document.activeElement.textContent })));
    out.sizes[key] = s;
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
