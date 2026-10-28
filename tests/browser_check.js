// Browser checks for the site, run by tests/test_browser.py when Playwright's Chromium is available.
// Usage: node tests/browser_check.js <base url> [chromium path]
// Prints one JSON object: { errors: [...], facts: {...} }. Every check is a fact the Python test asserts on.
const { chromium } = require('playwright');
const base = process.argv[2];
const exe = process.argv[3];
const pages = ['/', '/demo', '/explore', '/start', '/support', '/partners', '/partners/workspace', '/docs', '/privacy', '/lovable', '/mascots', '/use-cases'];
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
  for (const [vname, width, scheme] of [['1440-light', 1440, 'light'], ['1440-dark', 1440, 'dark'], ['1280-light', 1280, 'light'], ['768-light', 768, 'light'], ['375-light', 375, 'light']]) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: scheme });
    for (const path of pages) {
      const page = await ctx.newPage(); const label = `${path}@${vname}`; watch(page, label);
      await page.goto(base + path, { waitUntil: 'networkidle' });
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      if (sw > width) errors.push(`${label}: horizontal overflow ${sw} > ${width}`);
      const fonts = await page.evaluate(() => Promise.all([document.fonts.check('600 20px Fredoka'), document.fonts.check('400 16px Nunito')]));
      if (!fonts.every(Boolean)) errors.push(`${label}: self-hosted fonts not loaded`);
      if (path === '/explore') {
        // "What you can build automatically from this plan": every disclosure open, still no horizontal scroll, each card inside the screen
        facts[`build@${vname}`] = await page.evaluate(() => {
          document.querySelectorAll('#build details, #plan-text').forEach(d => { d.open = true; });
          const cards = [...document.querySelectorAll('#build .build-card')];
          const steps = [...document.querySelectorAll('#build .path-steps li')];
          const out = el => { const r = el.getBoundingClientRect(); return r.left < 0 || r.right > window.innerWidth; };
          return { cards: cards.length, outside: cards.filter(out).length, steps: steps.length, stepsOutside: steps.filter(out).length,
                   stepsInRow: new Set(steps.map(s => Math.round(s.getBoundingClientRect().top))).size,
                   scrollWidth: document.documentElement.scrollWidth };
        });
      }
      if (path === '/demo') {
        // the relationship list is the graph's alternative on a phone: visible, and every row reachable
        facts[`demoList@${vname}`] = await page.evaluate(() => {
          const l = document.querySelector('.rel-list'); const r = l && l.getBoundingClientRect();
          return !!r && r.width > 0 && r.height > 0 && getComputedStyle(l).visibility !== 'hidden' && l.querySelectorAll('a[data-edge]').length;
        });
      }
      if (path === '/') {
        facts[`homeCtas@${vname}`] = await page.evaluate(() => [...document.querySelectorAll('.hero .ctas a')].map(a => a.getAttribute('href')));
        // the hub under the hero: every card and the product inside the screen, none on top of another, no name cut
        // off, the text version for screen readers in the page (visually hidden, not display:none), and the layout:
        // three columns side by side on a wide screen, stacked with the product in the middle on a narrow one
        facts[`hub@${vname}`] = await page.evaluate(() => {
          const q = s => document.querySelector(s), box = e => e.getBoundingClientRect();
          const cards = [...document.querySelectorAll('.hub .hub-group, .hub .c-hub')], rs = cards.map(box);
          const outside = rs.filter(r => r.left < 0 || r.right > window.innerWidth).length;
          let overlaps = 0;
          for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
            const a = rs[i], b = rs[j];
            if (a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1) overlaps++;
          }
          const items = [...document.querySelectorAll('.hub .hub-group li')];
          const cut = items.filter(li => {                                     // no name or tag runs out of its card
            const g = box(li.closest('.hub-group')), rg = document.createRange(); rg.selectNodeContents(li); const r = rg.getBoundingClientRect();
            return r.left < g.left - 0.5 || r.right > g.right + 0.5;
          }).length;
          const [src, build, mid, where] = ['.hub-src', '.hub-build', '.hub-mid', '.hub-where'].map(s => box(q(s)));
          const sideBySide = src.right <= mid.left && mid.right <= where.left && build.right <= mid.left;
          const stacked = src.bottom <= build.top && build.bottom <= mid.top && mid.bottom <= where.top;
          const sr = q('.connects .visually-hidden');
          return { cards: cards.length, items: items.length, outside, overlaps, cut, sideBySide, stacked,
                   lines: [...document.querySelectorAll('.hub .hub-link')].filter(e => getComputedStyle(e).display !== 'none').length,
                   srText: sr && getComputedStyle(sr).display !== 'none' ? sr.textContent.length : 0 };
        });
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
  // the guided demo's graph on /demo: one relationship selected from the start, a decision by mouse and by keyboard,
  // reduced motion
  const hc = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const hp = await hc.newPage(); watch(hp, '/demo interactions');
  await hp.goto(base + '/demo', { waitUntil: 'networkidle' });
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
  // /explore's build cards with reduced motion: no transition or animation anywhere in the section
  const bp = await hc.newPage(); watch(bp, '/explore reduced motion');
  await bp.goto(base + '/explore', { waitUntil: 'networkidle' });
  facts.buildMotion = await bp.evaluate(() => [...document.querySelectorAll('#build, #build *')].filter(el => {
    const cs = getComputedStyle(el); return parseFloat(cs.transitionDuration) > 0 || (cs.animationName && cs.animationName !== 'none');
  }).length);
  // a visible focus ring on the start page's CTAs
  await hp.goto(base + '/', { waitUntil: 'networkidle' });
  await hp.focus('.hero .ctas a');
  facts.ctaFocusOutline = await hp.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  await hc.close();
  // the guided example on /demo (round 1 of 27 October 2026): steps, keyboard, the decision on the graph, reset
  const gc = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const gp = await gc.newPage(); watch(gp, '/demo guide');
  await gp.goto(base + '/demo', { waitUntil: 'networkidle' });
  const visible = () => gp.evaluate(() => [...document.querySelectorAll('.guide-pane')].filter(p => !p.hidden).map(p => p.dataset.pane));
  const card = () => gp.evaluate(() => [...document.querySelectorAll('.result-card')].filter(c => !c.hidden).map(c => c.dataset.variant)[0]);
  const shipTo = '.g-edge[data-id="orders.ship_to_id>addresses"]';
  facts.guideVisiblePanes = await visible();
  facts.guideStatus = await gp.textContent('.guide-status');
  await gp.click('[data-guide=next]');
  facts.guideAfterNext = await visible();
  await gp.focus('[data-guide=next]'); await gp.keyboard.press('Enter');
  facts.guideAfterKeyboardNext = await visible();
  await gp.click('[data-guide=back]');
  facts.guideAfterBack = await visible();
  await gp.click('[data-guide=next]');
  await gp.click('[data-guide-decide=accept]');
  facts.guideAcceptPressed = await gp.getAttribute('[data-guide-decide=accept]', 'aria-pressed');
  facts.guideEdgeClass = await gp.getAttribute(shipTo, 'class');
  await gp.click('[data-guide=next]');
  facts.guideCardShown = await card();
  facts.guideCardText = await gp.textContent('.result-card[data-variant=accepted]');
  await gp.click('[data-guide=reset]');
  facts.guideAfterReset = await visible();
  facts.guideEdgeAfterReset = await gp.getAttribute(shipTo, 'class');
  facts.guideCardAfterReset = await card();
  await gp.click('.rel-list a[data-edge="orders.ship_to_id>addresses"]'); await gp.click('#home-why [data-decide="accept"]');
  facts.guideFromGraph = await card();
  await gc.close();
  const g3 = await browser.newContext({ viewport: { width: 375, height: 900 } });
  const g3p = await g3.newPage(); watch(g3p, '/demo guide@375');
  await g3p.goto(base + '/demo', { waitUntil: 'networkidle' });
  facts.guideOverflow375 = await g3p.evaluate(() => [...document.querySelectorAll('#guide *')].filter(e => {
    const r = e.getBoundingClientRect(); return r.width > 0 && r.right > window.innerWidth + 1 && !e.closest('.table-wrap');
  }).map(e => e.tagName + '.' + e.className).slice(0, 5));
  facts.guidePreviewFits375 = await g3p.evaluate(() => [...document.querySelectorAll('#guide .order-preview .table-wrap')]
    .filter(w => w.getBoundingClientRect().width > 0).map(w => w.scrollWidth <= w.clientWidth + 1));
  facts.guideStepTargets375 = await g3p.evaluate(() => Math.min(...[...document.querySelectorAll('.guide-step, .guide-nav .btn, [data-guide-decide]')]
    .filter(b => b.getBoundingClientRect().height > 0).map(b => b.getBoundingClientRect().height)));
  await g3.close();
  // round n17: the start page's way in to /demo is at most half a screen on a small phone and a laptop, and the demo's
  // old anchors on the start page go on to the same anchor on /demo
  for (const [w, h] of [[375, 667], [1280, 800]]) {
    const ec = await browser.newContext({ viewport: { width: w, height: h } });
    const ep = await ec.newPage(); watch(ep, `/ entry@${w}x${h}`);
    await ep.goto(base + '/', { waitUntil: 'networkidle' });
    facts[`homeEntry@${w}x${h}`] = await ep.evaluate(() => document.getElementById('demo').getBoundingClientRect().height / window.innerHeight);
    await ec.close();
  }
  const ac = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  for (const hash of ['#guide', '#demo', '#guide-h3']) {
    const ap = await ac.newPage(); watch(ap, `/${hash}`);
    await ap.goto(base + '/' + hash);
    await ap.waitForURL(u => new URL(u).pathname === '/demo', { timeout: 5000 }).catch(() => {});
    await ap.waitForLoadState('networkidle');
    facts[`oldAnchor${hash}`] = await ap.evaluate(() => location.pathname + location.hash + (document.querySelector(location.hash) ? '' : ' (no target)'));
    await ap.close();
  }
  await ac.close();
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
