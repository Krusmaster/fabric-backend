// Round n52: where a first-time visitor's ways in sit on the screen. Prints JSON with the top and bottom (px from the
// top of the page) of the start page's hero buttons and of /check's examples, at 1280 x 800 and 375 x 812, light and
// dark, with and without reduced motion, plus what Tab reaches first on the start page.
const { chromium } = require('playwright');
(async () => {
  const [base, exe] = process.argv.slice(2);
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = {};
  for (const [w, h] of [[1280, 800], [375, 812]]) {
    for (const scheme of ['light', 'dark']) {
      for (const motion of ['no-preference', 'reduce']) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme, reducedMotion: motion });
        const page = await ctx.newPage();
        const v = `${w}x${h}-${scheme}-${motion}`;
        await page.goto(base + '/', { waitUntil: 'load' });
        out[`hero@${v}`] = await page.evaluate(() => [...document.querySelectorAll('.hero-ctas a')].map(a => {
          const r = a.getBoundingClientRect(); return { href: a.getAttribute('href'), text: a.textContent.trim(), top: r.top + scrollY, bottom: r.bottom + scrollY };
        }));
        if (v.endsWith('light-no-preference')) {
          const seen = [];
          for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); seen.push(await page.evaluate(() => document.activeElement.getAttribute('href'))); }
          out[`tab@${w}`] = seen;
        }
        await page.goto(base + '/check', { waitUntil: 'load' });
        out[`examples@${v}`] = await page.evaluate(() => {
          const r = (s) => { const b = document.querySelector(s).getBoundingClientRect(); return { top: b.top + scrollY, bottom: b.bottom + scrollY }; };
          return { heading: r('#check-ex-h'), buttons: [...document.querySelectorAll('.check-examples .check-ex')].map(b => { const x = b.getBoundingClientRect(); return { top: x.top + scrollY, bottom: x.bottom + scrollY }; }),
                   drop: r('#check-drop'), privacy: r('#check-private') };
        });
        await ctx.close();
      }
    }
  }
  await browser.close();
  console.log(JSON.stringify(out));
})();
