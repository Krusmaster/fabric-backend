// Browser checks for the site, run by tests/test_browser.py when Playwright's Chromium is available.
// Usage: node tests/browser_check.js <base url> [chromium path]
// Prints one JSON object: { errors: [...], facts: {...} }. Every check is a fact the Python test asserts on.
const { chromium } = require('playwright');
const base = process.argv[2];
const exe = process.argv[3];
const pages = ['/', '/explore', '/start', '/support', '/partners', '/partners/workspace', '/docs', '/privacy', '/lovable', '/mascots', '/use-cases'];
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const errors = [], facts = {};
  const watch = (page, label) => {
    page.on('pageerror', e => errors.push(`${label}: pageerror ${e.message}`));
    page.on('console', m => { if (m.type() === 'error') errors.push(`${label}: console ${m.text()}`); });
    page.on('requestfailed', r => errors.push(`${label}: request failed ${r.url()}`));
    page.on('request', r => { if (!r.url().startsWith(base)) errors.push(`${label}: external request ${r.url()}`); });
  };
  // the brief of 26 October 2026 asks for 375, 768 and 1440; dark mode at the widest
  for (const [vname, width, scheme] of [['1440-light', 1440, 'light'], ['1440-dark', 1440, 'dark'], ['768-light', 768, 'light'], ['375-light', 375, 'light']]) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
    for (const path of pages) {
      const page = await ctx.newPage(); const label = `${path}@${vname}`; watch(page, label);
      await page.goto(base + path, { waitUntil: 'networkidle' });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (sw > width) errors.push(`${label}: horizontal overflow ${sw} > ${width}`);
      const fonts = await page.evaluate(() => Promise.all([document.fonts.check('600 20px Fredoka'), document.fonts.check('400 16px Nunito')]));
      if (!fonts.every(Boolean)) errors.push(`${label}: self-hosted fonts not loaded`);
      if (path === '/') {
        // the relationship list is the graph's alternative on a phone: visible, and every row reachable
        facts[`homeList@${vname}`] = await page.evaluate(() => {
          const l = document.querySelector('.rel-list'); const r = l && l.getBoundingClientRect();
          return !!r && r.width > 0 && r.height > 0 && getComputedStyle(l).visibility !== 'hidden' && l.querySelectorAll('a[data-edge]').length;
        });
        facts[`homeCtas@${vname}`] = await page.evaluate(() => [...document.querySelectorAll('.hero .ctas a')].map(a => a.getAttribute('href')));
      }
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
  // fields are always on the table cards now (there is no Show fields toggle); the check below still asserts they show
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
  // the home demo: one relationship selected from the start, a decision by mouse and by keyboard, reduced motion
  const hc = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const hp = await hc.newPage(); watch(hp, '/ interactions');
  await hp.goto(base + '/', { waitUntil: 'networkidle' });
  facts.homeDefault = await hp.evaluate(() => { const a = document.querySelector('.rel-list a[aria-current="true"]'); return a ? a.getAttribute('data-edge') : null; });
  facts.homePanelDefault = await hp.textContent('#home-why');
  facts.homeDetailsClosed = await hp.evaluate(() => [...document.querySelectorAll('#home-why details')].every(d => !d.open));
  await hp.click('.rel-list a[data-edge="orders.ship_to_id>addresses"]');
  facts.homeDecisionPanel = await hp.textContent('#home-why');
  facts.homeUrlAfterListClick = await hp.evaluate(() => location.pathname);
  await hp.click('#home-why [data-decide="accept"]');
  facts.homeAfterAccept = await hp.textContent('#home-why');
  facts.homeFocusAfterAccept = await hp.evaluate(() => document.activeElement.getAttribute('data-decide'));
  facts.homeEdgeAccepted = await hp.getAttribute('.g-edge[data-id="orders.ship_to_id>addresses"]', 'class');
  await hp.keyboard.press('Tab'); await hp.keyboard.press('Shift+Tab'); await hp.keyboard.press('Enter');    // the same button, by keyboard
  facts.homeAfterKeyboard = await hp.textContent('#home-why');
  // keyboard on the list: focus a row and press Enter
  await hp.focus('.rel-list a[data-edge="order_items.order_id>orders"]'); await hp.keyboard.press('Enter');
  facts.homeKeyboardSelected = await hp.evaluate(() => { const a = document.querySelector('.rel-list a[aria-current="true"]'); return a ? a.getAttribute('data-edge') : null; });
  facts.homeMotionClass = await hp.evaluate(() => document.documentElement.classList.contains('motion'));
  // a visible focus ring on the list rows and the CTAs
  await hp.focus('.hero .ctas a');
  facts.ctaFocusOutline = await hp.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  await hc.close();
  // /docs: the groups and the 'on this page' list; /use-cases: an industry's details open by keyboard
  const dc = await browser.newContext({ viewport: { width: 375, height: 900 } });
  const dp = await dc.newPage(); watch(dp, '/use-cases details');
  await dp.goto(base + '/use-cases', { waitUntil: 'networkidle' });
  facts.useCaseTasks = await dp.locator('.uc-task').count();
  facts.useCaseDetailsClosed = await dp.evaluate(() => [...document.querySelectorAll('details.uc-more')].every(d => !d.open));
  await dp.focus('details.uc-more summary'); await dp.keyboard.press('Enter');
  facts.useCaseDetailsOpened = await dp.evaluate(() => document.querySelector('details.uc-more').open);
  await dc.close();
  // the two-company sales example (a preview): the question, the definition, the one decision, filters, keyboard,
  // save and reopen, at phone width
  const sc = await browser.newContext({ viewport: { width: 375, height: 900 }, reducedMotion: 'reduce' });
  const sp = await sc.newPage(); watch(sp, '/example/sales-planning');
  const api = async (q) => (await sp.request.get(base + '/example/sales-planning/result.json?' + q)).json();
  const firstTile = async () => parseInt((await sp.textContent('#sp-tiles .sp-tile-value')).replace(/\D/g, ''), 10);
  await sp.goto(base + '/example/sales-planning', { waitUntil: 'networkidle' });
  facts.salesScopeHiddenFirst = await sp.isHidden('#scope');
  await sp.fill('#sp-q', 'What will our margin be next quarter?'); await sp.click('#sp-ask button[type=submit]');
  facts.salesOtherQuestion = await sp.textContent('#sp-ask-note');
  facts.salesScopeHiddenAfterOther = await sp.isHidden('#scope');
  await sp.click('#sp-ask-note button');
  facts.salesScopeShown = await sp.isVisible('#scope');
  await sp.click('[data-def=yes]');
  facts.salesFocusAfterDefinition = await sp.evaluate(() => document.activeElement.id);
  facts.salesOpenTotal = await firstTile();
  facts.salesApiOpenTotal = (await api('company=all&weeks=26')).period.total;
  await Promise.all([sp.waitForResponse(r => r.url().includes('result.json')), sp.check('input[name="link-B-7003"][value="A-103"]')]);
  await sp.waitForTimeout(100);
  facts.salesLinkedTotal = await firstTile();
  facts.salesApiLinkedTotal = (await api('d=B-7003:A-103&company=all&weeks=26')).period.total;
  facts.salesUrlAfterLink = sp.url();
  await Promise.all([sp.waitForResponse(r => r.url().includes('result.json')), sp.selectOption('#sp-company', 'B')]);
  await Promise.all([sp.waitForResponse(r => r.url().includes('result.json')), sp.selectOption('#sp-weeks', '13')]);
  await sp.waitForTimeout(100);
  facts.salesFilteredTotal = await firstTile();
  facts.salesApiFilteredTotal = (await api('d=B-7003:A-103&company=B&weeks=13')).period.total;
  await sp.focus('#sp-chart svg'); await sp.keyboard.press('End');
  facts.salesKeyboardEnd = await sp.textContent('#sp-tip');
  await sp.keyboard.press('Home');
  facts.salesKeyboardHome = await sp.textContent('#sp-tip');
  facts.salesWideOutsideScroll = await sp.evaluate(() => [...document.querySelectorAll('body *')].filter(e => {
    const r = e.getBoundingClientRect(); return r.width > 0 && r.right > window.innerWidth + 1 && !e.closest('.sp-scroll, svg');
  }).map(e => e.tagName + '.' + e.className).slice(0, 5));
  await sp.click('#sp-save');
  const saved = sp.url();
  const sp2 = await sc.newPage(); watch(sp2, '/example/sales-planning reopened');
  await sp2.goto(saved, { waitUntil: 'networkidle' });
  facts.salesReopened = await sp2.isVisible('#sp-reopened') && await sp2.textContent('#sp-reopened');
  facts.salesReopenedTotal = parseInt((await sp2.textContent('#sp-tiles .sp-tile-value')).replace(/\D/g, ''), 10);
  facts.salesSavedList = await sp2.textContent('#sp-saved');
  facts.salesChoiceKept = await sp2.isChecked('input[name="link-B-7003"][value="A-103"]');
  await sc.close();
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
