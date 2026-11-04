// n86a: the docs' sub-pages in Chromium under the pages' own policy: 375 and 1280 px, light and dark; no sideways scroll,
// no console error or policy violation, the phone menu opens by mouse, by keyboard and without JavaScript, old
// /docs#anchors land on the right page and heading. Prints one JSON line; SHOTS=<dir> saves screenshots.
const { chromium } = require('playwright');
const base = process.argv[2], exe = process.argv[3];
const PAGES = JSON.parse(process.env.DOCS_PAGES || '["/docs"]');
const SHOTS = process.env.SHOTS || '';
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { overflow: [], errors: [], runs: {} };
  for (const width of [375, 1280]) for (const scheme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
    const page = await ctx.newPage();
    page.on('console', m => { if (m.type() === 'error') out.errors.push(`${width}-${scheme} ${page.url()} ${m.text()}`); });
    page.on('pageerror', e => out.errors.push(`${width}-${scheme} ${page.url()} ${e.message}`));
    const run = {};
    for (const p of PAGES) {
      await page.goto(base + p, { waitUntil: 'load' });
      const w = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
      if (w[0] > w[1]) out.overflow.push(`${width}-${scheme} ${p} ${w}`);
    }
    await page.goto(base + '/docs/get-started/connect', { waitUntil: 'load' });
    run.menuWide = await page.locator('nav.docs-menu').isVisible();
    run.menuPhone = await page.locator('details.docs-menu-m').isVisible();
    run.otp = await page.locator('aside.docs-otp').count() ? await page.locator('aside.docs-otp').isVisible() : null;
    run.bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/connect-${width}-${scheme}.png`, fullPage: false });
    if (width === 375) {
      run.closedLinkVisible = await page.locator('details.docs-menu-m a[href="/docs/reference/tools"]').isVisible();
      // keyboard: Tab to the summary, Enter opens, Tab reaches the first link
      await page.locator('details.docs-menu-m > summary').focus();
      await page.keyboard.press('Enter');
      run.openByKey = await page.locator('details.docs-menu-m').evaluate(d => d.open);
      await page.keyboard.press('Tab');
      run.focusAfter = await page.evaluate(() => document.activeElement && document.activeElement.getAttribute('href'));
      const w = await page.evaluate(() => [document.documentElement.scrollWidth, innerWidth]);
      run.openOverflow = w[0] > w[1];
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/menu-open-375-${scheme}.png`, fullPage: false });
      await page.locator('details.docs-menu-m > summary').click();
      run.closedByClick = !(await page.locator('details.docs-menu-m').evaluate(d => d.open));
    }
    // old anchors, on load and by a hash change on /docs
    await page.goto(base + '/docs#test-status', { waitUntil: 'load' });
    await page.waitForURL(/\/docs\/reference\/test-status#test-status$/, { timeout: 5000 }).catch(() => {});
    run.oldAnchor = page.url().replace(base, '');
    run.headingInView = await page.locator('#test-status').evaluate(h => { const r = h.getBoundingClientRect(); return r.top >= -2 && r.top < innerHeight; });
    await page.goto(base + '/docs', { waitUntil: 'load' });
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/overview-${width}-${scheme}.png`, fullPage: false });
    await page.evaluate(() => { location.hash = 'first-time-errors'; });
    await page.waitForURL(/get-started\/first-time-errors#first-time-errors$/, { timeout: 5000 }).catch(() => {});
    run.hashChange = page.url().replace(base, '');
    await page.goto(base + '/docs#why-krusgraph', { waitUntil: 'load' });
    run.ownAnchor = page.url().replace(base, '');
    await page.goto(base + '/docs/reference/tools', { waitUntil: 'load' });
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/tools-${width}-${scheme}.png`, fullPage: false });
    out.runs[`${width}-${scheme}`] = run;
    await ctx.close();
  }
  // without JavaScript: /docs is the overview with links to everything; the phone menu still opens
  const ctx = await browser.newContext({ viewport: { width: 375, height: 900 }, javaScriptEnabled: false });
  const page = await ctx.newPage();
  await page.goto(base + '/docs#test-status', { waitUntil: 'load' });
  out.noJs = { url: page.url().replace(base, ''), links: await page.locator('nav.docs-children a').count() };
  await page.locator('details.docs-menu-m > summary').click();
  out.noJs.opens = await page.locator('details.docs-menu-m a[href="/docs/reference/tools"]').isVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/nojs-375.png`, fullPage: false });
  await ctx.close();
  await browser.close();
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
