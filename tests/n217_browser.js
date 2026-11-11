// n217: the data flow of the replay's fourth answer, in the card under the turns, at 375, 768, 1280 and 1440 px, light and dark, with and without
// reduced motion: no horizontal scroll, no console error, the wide picture from 720 px and the tall one under it, the
// picture inside the replay's card, and its boxes in the engine's order.
// Usage: node tests/n217_browser.js <base url>
const { chromium } = require('playwright');
const base = process.argv[2];
const SIZES = [[375, 812], [768, 1024], [1280, 720], [1440, 900]];
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
    out.sizes[key] = await page.evaluate(() => {
      const W = document.documentElement.clientWidth;
      const card = document.querySelector('figure.session').getBoundingClientRect();
      const flow = document.querySelector('.session-flow');
      const shown = [...flow.querySelectorAll('svg.kgr')].filter((s) => getComputedStyle(s).display !== 'none');
      const svg = shown[0];
      const r = svg.getBoundingClientRect();
      const boxes = [...svg.querySelectorAll('g.kgr-n')];
      const inside = boxes.every((g) => { const b = g.getBoundingClientRect(); return b.left >= card.left - 1 && b.right <= card.right + 1; });
      const css = (sel, p) => getComputedStyle(svg.querySelector(sel))[p];
      const bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g).map(Number);
      return { overflow: document.documentElement.scrollWidth - innerWidth, shown: shown.map((s) => s.getAttribute('class')),
               width: Math.round(r.width), inCard: r.left >= card.left - 1 && r.right <= card.right + 1 && r.right <= W, inside,
               ids: boxes.map((g) => g.getAttribute('data-id')), dashed: boxes.filter((g) => css(`[data-id="${g.getAttribute('data-id')}"] rect`, 'strokeDasharray') !== 'none').map((g) => g.getAttribute('data-id')),
               words: flow.querySelector('.kgr-words').textContent, underTurns: !flow.closest('.session-turn') && !!flow.closest('figure.session'),
               animation: getComputedStyle(svg.querySelector('.kgr-at-silver')).animationName,
               dark: (bg[0] + bg[1] + bg[2]) / 3 < 80 };
    });
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
