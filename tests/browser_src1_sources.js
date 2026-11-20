// SRC1: /sources and its two source pages at 390 x 844 (touch, mobile), light and dark: no page error, no sideways
// scroll, no element reaching past the right edge. Usage: node browser_src1_sources.js <base> [chromium]
const { chromium } = require('playwright');
const [base, exe] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const errors = [], pages = {};
  for (const path of ['/sources', '/sources/salesforce', '/sources/dynamics365']) {
    for (const scheme of ['light', 'dark']) {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, colorScheme: scheme });
      const page = await ctx.newPage();
      page.on('pageerror', (e) => errors.push(`${path} ${scheme}: ${e.message}`));
      page.on('console', (m) => { if (m.type() === 'error') errors.push(`${path} ${scheme}: ${m.text()}`); });
      await page.goto(base + path, { waitUntil: 'load' });
      await page.waitForTimeout(300);
      pages[`${path} ${scheme}`] = await page.evaluate(() => ({
        width: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        wide: [...document.querySelectorAll('main *, [data-page] *')].filter((el) => el.getBoundingClientRect().right > innerWidth + 1)
          .slice(0, 5).map((el) => el.tagName + ' ' + (el.textContent || '').trim().slice(0, 40)),
      }));
      await ctx.close();
    }
  }
  await browser.close();
  console.log(JSON.stringify({ errors, pages }));
})();
