// Browser checks for the site, run by tests/test_browser.py when Playwright's Chromium is available.
// Usage: node tests/browser_check.js <base url> [chromium path]
// Prints one JSON object: { errors: [...], facts: {...} }. Every check is a fact the Python test asserts on.
const { chromium } = require('playwright');
const base = process.argv[2];
const exe = process.argv[3];
const pages = ['/', '/start', '/support', '/partners', '/partners/workspace', '/docs', '/privacy', '/lovable', '/mascots', '/use-cases', '/use-cases/build'];
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const errors = [], facts = {};
  const watch = (page, label) => {
    page.on('pageerror', e => errors.push(`${label}: pageerror ${e.message}`));
    page.on('console', m => { if (m.type() === 'error') errors.push(`${label}: console ${m.text()}`); });
    // n163: a page that navigates on load (the old anchors on / go on to /check) cancels what it was still fetching; a
    // same-origin media file cancelled that way (the film's captions track) is not a failure. Anything else still is.
    page.on('requestfailed', r => {
      const aborted = ((r.failure() || {}).errorText || '') === 'net::ERR_ABORTED';
      if (aborted && r.url().startsWith(base + '/static/media/')) return;
      errors.push(`${label}: request failed ${r.url()}`);
    });
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
      // the mascot toggle and the mascots go together (n36): the button shows only where a mascot does
      const pair = await page.evaluate(() => new Promise(r => setTimeout(() => {
        const shown = e => { const b = e.getBoundingClientRect(), s = getComputedStyle(e); return b.width > 0 && b.height > 0 && s.visibility !== 'hidden'; };
        r({ toggle: [...document.querySelectorAll('[data-mascot-toggle]')].some(shown), mascots: [...document.querySelectorAll('svg.mascot')].filter(shown).length });
      }, 300)));
      if (pair.toggle !== pair.mascots > 0) errors.push(`${label}: mascot toggle ${pair.toggle ? 'shown' : 'hidden'} with ${pair.mascots} mascots visible`);
      if (path === '/use-cases') {
        // n59: each example's map drawn by map.js: tables, lines with rule names, no map wider than the screen
        facts[`ucMaps@${vname}`] = await page.evaluate(() => [...document.querySelectorAll('.uc-map')].map(f => {
          const r = f.getBoundingClientRect();
          return { nodes: f.querySelectorAll('.m-node').length, lines: f.querySelectorAll('.m-edge').length, rules: f.querySelectorAll('.m-rule').length,
                   dashed: f.querySelectorAll('.m-sug').length, inside: r.left >= 0 && r.right <= window.innerWidth };
        }));
      }
      if (path === '/use-cases/build') {
        // n55: "What you can build automatically from a plan", on /use-cases/build since n59: every disclosure open, still no horizontal scroll, each card inside the screen
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
      if (path === '/') {
        facts[`homeCtas@${vname}`] = await page.evaluate(() => [...document.querySelectorAll('.hero .ctas a')].map(a => a.getAttribute('href')));
        // n190: the hub left the home page (tests/n190_browser.js covers the new sections)
        // n68: the Connect chooser (n149: on /start, step 3, "Choose your client"; the home page links there): opened by keyboard, its
        // panel on the screen, its links the clients' install links, Escape closes it and returns the focus; no horizontal scroll
        facts[`connect@${vname}`] = await (async () => {
          const out = {};
          // its own tab: leaving the home page would cut off its prefetch of /check's engine (a failed request)
          const page = await ctx.newPage(); watch(page, `/start#step-3@${vname}`);
          await page.goto(base + '/start#step-3', { waitUntil: 'load' });
          for (const where of ['.start-pane[data-pane="3"]']) {
            await page.focus(where + ' summary'); await page.keyboard.press('Enter'); await page.waitForTimeout(150);
            out[where] = await page.evaluate((w) => {
              const d = document.querySelector(w + ' details'), r = d.querySelector('.connect-panel').getBoundingClientRect();
              return { open: d.open, inside: r.left >= 0 && r.right <= window.innerWidth, wide: document.documentElement.scrollWidth,
                       links: [...d.querySelectorAll('a')].map(a => (a.getAttribute('href') || '').split('?')[0].split('#')[0]),
                       copies: [...d.querySelectorAll('[data-copy-text]')].map(b => b.getAttribute('data-copy-text')) };
            }, where);
            await page.keyboard.press('Escape');
            out[where].afterEscape = await page.evaluate((w) => ({ open: document.querySelector(w + ' details').open, focus: document.activeElement === document.querySelector(w + ' summary') }), where);
          }
          await page.close();
          return out;
        })();
      }
      await page.close();
    }
    await ctx.close();
  }
  // n55: the mascot toggle on /use-cases (it was tried on /explore, now a redirect to /check)
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage(); watch(page, '/use-cases mascots');
  await page.goto(base + '/use-cases', { waitUntil: 'networkidle' });
  // mascot toggle persists
  await page.click('[data-mascot-toggle]');
  await page.reload({ waitUntil: 'networkidle' });
  facts.mascotsAfterReload = await page.evaluate(() => document.documentElement.getAttribute('data-mascots'));
  await page.click('[data-mascot-toggle]');
  facts.mascotsAfterToggleBack = await page.evaluate(() => document.documentElement.getAttribute('data-mascots'));
  await ctx.close();
  // n55: the theme button: the system's choice first, a click (and Enter) switches, the choice survives a reload
  const tc = await browser.newContext({ viewport: { width: 375, height: 800 }, colorScheme: 'light' });
  const tp = await tc.newPage(); watch(tp, '/ theme');
  await tp.goto(base + '/', { waitUntil: 'networkidle' });
  const themeState = () => tp.evaluate(() => ({ theme: document.documentElement.dataset.theme || null,
    pressed: document.querySelector('[data-theme-toggle]').getAttribute('aria-pressed'),
    bg: getComputedStyle(document.body).backgroundColor, meta: document.querySelector('meta[name=theme-color]').content }));
  facts.themeFirst = await themeState();
  await tp.click('[data-theme-toggle]');
  facts.themeAfterClick = await themeState();
  await tp.reload({ waitUntil: 'networkidle' });
  facts.themeAfterReload = await themeState();
  await tp.focus('[data-theme-toggle]'); await tp.keyboard.press('Enter');
  facts.themeAfterEnter = await themeState();
  await tc.close();
  const hc = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const hp = await hc.newPage(); watch(hp, '/ focus');
  // n59: the maps on /use-cases with reduced motion: drawn at once, nothing animates in
  const ucp = await hc.newPage(); watch(ucp, '/use-cases maps reduced motion');
  await ucp.goto(base + '/use-cases', { waitUntil: 'networkidle' });
  facts.ucMapMotion = await ucp.evaluate(() => ({ drawn: document.querySelectorAll('.uc-map .m-edge').length,
    moving: [...document.querySelectorAll('.uc-map *')].filter(el => { const cs = getComputedStyle(el); return cs.animationName && cs.animationName !== 'none'; }).length }));
  // the build cards (on /use-cases/build since n59) with reduced motion: no transition or animation anywhere in the section
  const bp = await hc.newPage(); watch(bp, '/use-cases reduced motion');
  await bp.goto(base + '/use-cases/build', { waitUntil: 'networkidle' });
  facts.buildMotion = await bp.evaluate(() => [...document.querySelectorAll('#build, #build *')].filter(el => {
    const cs = getComputedStyle(el); return parseFloat(cs.transitionDuration) > 0 || (cs.animationName && cs.animationName !== 'none');
  }).length);
  // a visible focus ring on the start page's CTAs
  await hp.goto(base + '/', { waitUntil: 'networkidle' });
  await hp.focus('.hero .ctas a');
  facts.ctaFocusOutline = await hp.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  await hc.close();
  // round n17: the start page's way in to /demo is at most half a screen on a small phone and a laptop, and the demo's
  // old anchors on the start page go on to the same anchor on /demo
  for (const [w, h] of [[375, 667], [1280, 800]]) {
    const ec = await browser.newContext({ viewport: { width: w, height: h } });
    const ep = await ec.newPage(); watch(ep, `/ entry@${w}x${h}`);
    await ep.goto(base + '/', { waitUntil: 'networkidle' });
    // n190: the way in is the hero's demo button: its bottom within the first screen
    facts[`homeEntry@${w}x${h}`] = await ep.evaluate(() => document.querySelector('.hero-ctas a[data-cta="demo"]').getBoundingClientRect().bottom / window.innerHeight);
    await ec.close();
  }
  const ac = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  for (const hash of ['#guide', '#demo', '#guide-h3']) {
    const ap = await ac.newPage(); watch(ap, `/${hash}`);
    await ap.goto(base + '/' + hash);
    await ap.waitForURL(u => new URL(u).pathname === '/check', { timeout: 5000 }).catch(() => {});
    facts[`oldAnchor${hash}`] = await ap.evaluate(() => location.pathname + location.search);
    await ap.close();
  }
  await ac.close();
  // /docs: the groups and the 'on this page' list; /use-cases: an industry's details open by keyboard
  const dc = await browser.newContext({ viewport: { width: 375, height: 900 } });
  const dp = await dc.newPage(); watch(dp, '/use-cases details');
  await dp.goto(base + '/use-cases', { waitUntil: 'networkidle' });
  facts.useCaseTasks = await dp.locator('.uc-task').count();
  // n59: a finding under a map is marked on it by keyboard, as on /check, and unmarked by a second Enter
  await dp.focus('#try-retail [data-finding]'); await dp.keyboard.press('Enter');
  facts.useCaseMarked = await dp.evaluate(() => ({ pressed: document.querySelector('#try-retail [data-finding]').getAttribute('aria-pressed'),
    lit: document.querySelectorAll('#try-retail .m-hl').length }));
  await dp.keyboard.press('Enter');
  facts.useCaseUnmarked = await dp.evaluate(() => document.querySelectorAll('#try-retail .m-hl').length);
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
