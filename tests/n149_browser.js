// n149: /check at 375 px puts the drop area and the "read in this browser" line above the example cards; the home page
// has no horizontal scroll at 375 px (n154: and has the floating "Try a demo" button again; n196: the film under the buttons).
// Usage: node tests/n149_browser.js <base url> [chromium path]. Prints one JSON object the Python test asserts on.
const { chromium } = require('playwright');
const base = process.argv[2], exe = process.argv[3];
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  for (const width of [375, 1280]) {
    const page = await browser.newPage({ viewport: { width, height: 800 } });
    page.on('pageerror', (e) => out.errors.push(`${width}: ${e.message}`));
    await page.goto(base + '/check', { waitUntil: 'domcontentloaded' });
    out['check' + width] = await page.evaluate(() => {
      const top = (s) => document.querySelector(s).getBoundingClientRect().top;
      const cards = [...document.querySelectorAll('.check-ex[data-example]')].map((e) => e.getBoundingClientRect());
      return { drop: top('#check-drop'), priv: top('#check-private'), examples: top('.check-examples'),
               columns: new Set(cards.map((r) => Math.round(r.left))).size, wide: document.documentElement.scrollWidth };
    });
    await page.goto(base + '/', { waitUntil: 'load' });
    out['home' + width] = await page.evaluate(() => ({
      pill: !!document.querySelector('.kgc-launch'), wide: document.documentElement.scrollWidth,
      film: (() => { const m = document.querySelector('#film'), c = document.querySelector('.hero-ctas');   // n196: the film, not the chip
                     return m && c ? m.getBoundingClientRect().top >= c.getBoundingClientRect().bottom : false; })() }));
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
