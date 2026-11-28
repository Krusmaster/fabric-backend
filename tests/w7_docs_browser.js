// W7: the docs menu keeps its place, and the SAP film on the docs' "SAP on Fabric" page.
// At 1280 x 800, light and dark: open a docs page, scroll the menu down, click a link near its bottom; on the new page
// the current page's link must be inside the menu's visible part and on screen, and the window must not have scrolled.
// A #hash still lands on its heading. At 390 x 844 the menu is the closed "Docs menu" and nothing scrolls sideways.
// The SAP page of the docs carries the film. Screenshots go to the directory in W7_SHOTS when it is set.
// Usage: node tests/w7_docs_browser.js <base url>
const { chromium } = require('playwright');
const path = require('path');
const base = process.argv[2];
const shots = process.env.W7_SHOTS || '';
const SAP = '/docs/concepts/sap-on-fabric';                  // DS1: in "How it works"
const HASH = '/docs/why/vision#how-it-keeps-itself-up-to-date';   // DS1: a part of Vision
(async () => {
  const browser = await chromium.launch();
  const out = { errors: [], wide: {}, phone: {}, hash: {}, sap: {} };
  const current = () => {
    const m = document.querySelector('nav.docs-menu'), a = m.querySelector('a[aria-current=page]');
    const mr = m.getBoundingClientRect(), ar = a.getBoundingClientRect();
    const bottom = Math.min(mr.bottom, innerHeight);
    return { href: a.getAttribute('href'), menuScroll: m.scrollTop, menuScrolls: m.scrollHeight > m.clientHeight,
             sticky: getComputedStyle(m).position, overflowY: getComputedStyle(m).overflowY,
             inMenu: ar.top >= mr.top - 1 && ar.bottom <= bottom + 1, linkTop: ar.top, linkBottom: ar.bottom,
             menuTop: mr.top, menuBottom: bottom, windowY: scrollY, overflow: document.documentElement.scrollWidth > innerWidth };
  };
  for (const scheme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, colorScheme: scheme });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => out.errors.push(String(e)));
    await page.goto(base + '/docs/get-started/connect', { waitUntil: 'load' });
    const first = await page.evaluate(current);
    // a link near the bottom of the menu's own pages (the last one before the "more" list), brought into view by
    // scrolling the menu as a reader would
    const target = await page.evaluate(() => {
      const links = [...document.querySelectorAll('nav.docs-menu ul.docs-tree:not(.docs-more) a')];
      const a = links[links.length - 2];
      const m = document.querySelector('nav.docs-menu');
      m.scrollTop = m.scrollHeight;
      return { href: a.getAttribute('href'), index: links.length - 2, of: links.length, scrolledTo: m.scrollTop };
    });
    await Promise.all([page.waitForNavigation({ waitUntil: 'load' }),
                       page.click(`nav.docs-menu a[href="${target.href}"]`)]);
    const after = await page.evaluate(current);
    after.bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    if (shots) await page.screenshot({ path: path.join(shots, `w7-docs-sidebar-after-click-${scheme}.png`) });
    // a #hash: the heading lands at the top and the menu still shows the current link
    const hashPage = HASH;
    let hash = null;
    if (hashPage) {
      await page.goto(base + hashPage, { waitUntil: 'load' });
      await page.waitForTimeout(1500);                                   // html has scroll-behavior:smooth
      hash = await page.evaluate(current);
      hash.url = hashPage;
      hash.headingTop = await page.evaluate(() => document.getElementById(decodeURIComponent(location.hash.slice(1))).getBoundingClientRect().top);
    }
    out.wide[scheme] = { first, target, after };
    out.hash[scheme] = hash;
    // the SAP page of the docs: the film, and a screenshot of it
    await page.goto(base + SAP, { waitUntil: 'load' });
    const sap = await page.evaluate(() => {
      const v = document.querySelector('#sap-film video'), t = v && v.querySelector('track');
      const r = v ? v.getBoundingClientRect() : null;
      return v ? { preload: v.preload, poster: v.getAttribute('poster'), controls: v.controls, autoplay: v.hasAttribute('autoplay'),
                   src: v.querySelector('source').getAttribute('src'), track: t && { kind: t.kind, srclang: t.srclang, def: t.default, src: t.getAttribute('src') },
                   width: r.width, height: r.height, ratio: r.width / r.height, link: !!document.querySelector('#sap-film a[href="/sap"]'),
                   overflow: document.documentElement.scrollWidth > innerWidth,
                   active: document.querySelector('nav.docs-menu a[aria-current=page]').getAttribute('href') } : null;
    });
    if (shots) {
      await page.evaluate(() => { const h = document.querySelector('article.prose h1'); window.scrollTo(0, h.getBoundingClientRect().top + scrollY - 20); });
      await page.waitForTimeout(150);
      await page.screenshot({ path: path.join(shots, `w7-docs-sap-film-${scheme}.png`) });
    }
    out.sap[scheme] = sap;
    await ctx.close();
  }
  // a phone: the menu is the closed "Docs menu" above the text, as before
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => out.errors.push(String(e)));
  await page.goto(base + '/docs/support', { waitUntil: 'load' });
  out.phone.docs = await page.evaluate(() => ({
    wideMenuShown: getComputedStyle(document.querySelector('nav.docs-menu')).display !== 'none',
    details: !!document.querySelector('details.docs-menu-m'), open: document.querySelector('details.docs-menu-m').open,
    windowY: scrollY, overflow: document.documentElement.scrollWidth > innerWidth }));
  await page.goto(base + SAP, { waitUntil: 'load' });
  out.phone.sap = await page.evaluate(() => {
    const r = document.querySelector('#sap-film video').getBoundingClientRect();
    return { width: r.width, ratio: r.width / r.height, left: r.left, right: r.right, vw: innerWidth,
             overflow: document.documentElement.scrollWidth > innerWidth };
  });
  if (shots) {
    await page.evaluate(() => document.getElementById('sap-film').scrollIntoView({ block: 'center' }));
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(shots, 'w7-docs-sap-film-390.png') });
  }
  await ctx.close();
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
