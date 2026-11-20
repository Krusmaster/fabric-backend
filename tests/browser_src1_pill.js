// SRC2: the chat's "Try a demo" button on /sources and its two source pages at 390, 768, 1280 and 1440 px: scrolled
// from top to bottom, wherever the button is visible its box intersects no card and no table (it steps aside over
// [data-kgc-avoid], site.js, as on /check). Usage: node browser_src1_pill.js <base> [chromium]
const { chromium } = require('playwright');
const [base, exe] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const errors = [], runs = {};
  for (const path of ['/sources', '/sources/salesforce', '/sources/dynamics365']) {
    for (const width of [390, 768, 1280, 1440]) {
      const mobile = width === 390;
      const ctx = await browser.newContext({ viewport: { width, height: mobile ? 844 : 900 }, isMobile: mobile, hasTouch: mobile });
      const page = await ctx.newPage();
      page.on('pageerror', (e) => errors.push(`${path} ${width}: ${e.message}`));
      await page.goto(base + path, { waitUntil: 'load' });
      await page.waitForTimeout(300);
      const run = { pill: false, steps: 0, shown: 0, hits: [] };
      const total = await page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
      for (let y = 0; ; y = Math.min(y + 150, total)) {
        await page.evaluate((top) => window.scrollTo(0, top), y);
        await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
        const r = await page.evaluate(() => {
          const b = document.getElementById('kgcLaunch');
          if (!b || b.hidden) return { pill: false };
          const s = getComputedStyle(b), p = b.getBoundingClientRect();
          if (s.visibility === 'hidden' || s.display === 'none' || s.opacity === '0') return { pill: true, shown: false };
          const hits = [...document.querySelectorAll('[data-page] .card, [data-page] table, [data-page] .table-wrap, [data-page] .src-mod')]
            .filter((el) => el.matches('details') || !el.closest('details:not([open])'))   // a closed <details>' content is not shown
            .filter((el) => { const q = el.getBoundingClientRect();
              return q.width && q.left < p.right && p.left < q.right && q.top < p.bottom && p.top < q.bottom; })
            .map((el) => el.tagName + '.' + el.className + (el.id ? '#' + el.id : ''));
          return { pill: true, shown: true, hits };
        });
        run.steps++;
        if (r.pill) run.pill = true;
        if (r.shown) { run.shown++; if (r.hits.length) run.hits.push({ y, hits: r.hits.slice(0, 3) }); }
        if (y >= total) break;
      }
      runs[`${path} ${width}`] = run;
      await ctx.close();
    }
  }
  await browser.close();
  console.log(JSON.stringify({ errors, runs }));
})();
