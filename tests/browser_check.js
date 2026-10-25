// Browser checks for the site, run by tests/test_browser.py when Playwright's Chromium is available.
// Usage: node tests/browser_check.js <base url> [chromium path]
// Prints one JSON object: { errors: [...], facts: {...} }. Every check is a fact the Python test asserts on.
const { chromium } = require('playwright');
const base = process.argv[2];
const exe = process.argv[3];
const pages = ['/', '/explore', '/start', '/support', '/partners', '/partners/workspace', '/docs', '/privacy', '/mascots'];
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const errors = [], facts = {};
  const watch = (page, label) => {
    page.on('pageerror', e => errors.push(`${label}: pageerror ${e.message}`));
    page.on('console', m => { if (m.type() === 'error') errors.push(`${label}: console ${m.text()}`); });
    page.on('requestfailed', r => errors.push(`${label}: request failed ${r.url()}`));
    page.on('request', r => { if (!r.url().startsWith(base)) errors.push(`${label}: external request ${r.url()}`); });
  };
  for (const [vname, width, scheme] of [['1280-light', 1280, 'light'], ['1280-dark', 1280, 'dark'], ['390-light', 390, 'light']]) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
    for (const path of pages) {
      const page = await ctx.newPage(); const label = `${path}@${vname}`; watch(page, label);
      await page.goto(base + path, { waitUntil: 'networkidle' });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (sw > width) errors.push(`${label}: horizontal overflow ${sw} > ${width}`);
      const fonts = await page.evaluate(() => Promise.all([document.fonts.check('600 20px Fredoka'), document.fonts.check('400 16px Nunito')]));
      if (!fonts.every(Boolean)) errors.push(`${label}: self-hosted fonts not loaded`);
      await page.close();
    }
    await ctx.close();
  }
  // interactions on /explore
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage(); watch(page, '/explore interactions');
  await page.goto(base + '/explore#table=orders', { waitUntil: 'networkidle' });
  facts.deepLinkSelected = await page.evaluate(() => (document.querySelector('.g-node.selected') || {}).dataset ? document.querySelector('.g-node.selected').dataset.table : null);
  facts.nodeCount = await page.locator('.g-node').count();
  facts.edgeCount = await page.locator('.g-edge').count();
  await page.click('.g-edge[data-id="orders.customer_id>customers"]');
  facts.whyText = await page.textContent('#why');
  facts.hashAfterEdge = await page.evaluate(() => location.hash);
  await page.click('.g-edge.suggested'); await page.click('#acc');
  facts.acceptedClass = await page.getAttribute('.g-edge.suggested', 'class');
  await page.click('#btn-reset');
  facts.afterResetClass = await page.getAttribute('.g-edge.suggested', 'class');
  await page.click('#btn-fields');
  facts.fieldsShown = await page.evaluate(() => getComputedStyle(document.querySelector('.g-node-cols')).display);
  // keyboard: the first Tab stops inside the graph are tables, not wires
  await page.click('#btn-reset'); await page.keyboard.press('Tab'); await page.keyboard.press('Tab'); await page.keyboard.press('Tab');
  facts.firstGraphFocus = await page.evaluate(() => document.activeElement.className.baseVal !== undefined ? 'svg' : document.activeElement.className);
  // mascot toggle persists
  await page.click('[data-mascot-toggle]');
  await page.reload({ waitUntil: 'networkidle' });
  facts.mascotsAfterReload = await page.evaluate(() => document.documentElement.getAttribute('data-mascots'));
  await page.click('[data-mascot-toggle]');
  facts.mascotsAfterToggleBack = await page.evaluate(() => document.documentElement.getAttribute('data-mascots'));
  await ctx.close();
  // builder on /mascots: failure keeps its status, no celebrate pose
  const m = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
  const mp = await m.newPage(); watch(mp, '/mascots builder');
  await mp.goto(base + '/mascots', { waitUntil: 'networkidle' });
  const poses = [];
  await mp.exposeFunction('notePose', p => poses.push(p));
  await mp.evaluate(() => { const s = document.querySelector('#m-build svg'); new MutationObserver(() => window.notePose(s.getAttribute('data-pose'))).observe(s, { attributes: true }); });
  await mp.click('#m-sim-err'); await mp.waitForTimeout(400);
  facts.builderPoses = poses; facts.builderErrorShown = await mp.evaluate(() => document.getElementById('m-err').classList.contains('show'));
  facts.motionClassUnderReducedMotion = await mp.evaluate(() => document.documentElement.classList.contains('motion'));
  await m.close();
  await browser.close();
  console.log(JSON.stringify({ errors, facts }));
})().catch(e => { console.log(JSON.stringify({ errors: ['script failed: ' + e.message], facts: {} })); process.exit(0); });
