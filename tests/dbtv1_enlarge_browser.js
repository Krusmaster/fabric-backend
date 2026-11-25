// DBTV1: every picture in the Try-a-demo chat opens larger, the dbt project's flow too (the founder, 21 November 2026).
// The chat is restored with every step done (the plan, the model, the data flow, the ontology, the data products, the
// fixes and the dbt project); then each "Larger picture" / "Open larger" is opened and closed in turn, at 390 px (light
// and dark) and at 1280 px: it opens (the focus on Back to the chat), the page has no sideways scroll, the overlay stays
// inside the window, Esc and Back each close it and gives the focus back to the button. Every picture has its button.
// Usage: node tests/dbtv1_enlarge_browser.js <base url>
const { chromium } = require('playwright');
const { open } = require('./browser_nav');
const base = process.argv[2];
const RUNS = [[390, 844, 'light'], [390, 844, 'dark'], [1280, 800, 'light']];
const STEPS = ['scan', 'no', 'model', 'flow', 'ontology', 'domains', 'fixes', 'dbt'];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(page, fn, arg, what) {
  for (let i = 0; i < 300; i++) { if (await page.evaluate(fn, arg)) return; await wait(50); }
  throw new Error('timeout: ' + (what || arg));
}
(async () => {
  const browser = await chromium.launch();
  const out = { errors: [], runs: {} };
  for (const [width, height, scheme] of RUNS) {
    const key = `${width}-${scheme}`;
    const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, reducedMotion: 'reduce' });
    await ctx.addInitScript((steps) => {
      try { sessionStorage.setItem('krusgraph.chat', JSON.stringify({ open: true, steps })); } catch (e) { /* none */ }
    }, STEPS);
    const page = await ctx.newPage();
    page.on('pageerror', (e) => out.errors.push(`${key}: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(`${key}: ${m.text()}`); });
    await open(page, base + '/', '[data-page="home"]');
    // under 560 px a restored chat waits for its button; a click opens it with the stored steps
    await until(page, () => { const b = document.getElementById('kgcLaunch'); return b && (!b.hidden || document.querySelector('.kgc-log .kgf')); }, null, 'launch');
    if (await page.evaluate(() => !document.querySelector('.kgc-log .kgf'))) await page.click('#kgcLaunch');
    await until(page, () => !!document.querySelector('#kgcBox:not([hidden]) .kgc-log .kgf'), null, 'restored dbt flow');
    await wait(200);
    const r = await page.evaluate(() => {
      const log = document.querySelector('.kgc-log');
      // every picture: an SVG picture, the data flow, the dbt flow; and whether its own enlarge button is beside it
      const pics = [...log.querySelectorAll('figure.kgc-pic > svg.kgc-svg, .kgd.kgc-flow, .kgf')].map((p) => {
        const holder = p.closest('figure.kgc-pic') || p.closest('.kgf-slot') || p;
        return { kind: p.matches('.kgf') ? 'dbt' : p.matches('.kgd') ? 'flow' : 'svg', button: !!holder.querySelector('.kgc-zoom') };
      });
      const bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g).map(Number);
      return { pics, buttons: log.querySelectorAll('.kgc-zoom').length, dark: (bg[0] + bg[1] + bg[2]) / 3 < 80,
               overflow: document.documentElement.scrollWidth - innerWidth };
    });
    r.opened = [];
    for (let i = 0; i < r.buttons; i++) for (const how of ['escape', 'back']) {
      await page.evaluate((n) => { const b = document.querySelectorAll('.kgc-log .kgc-zoom')[n]; b.scrollIntoView({ block: 'center' }); }, i);
      const inertBefore = await page.evaluate(() => document.querySelectorAll('[inert]').length);
      await page.locator('.kgc-log .kgc-zoom').nth(i).click();
      await until(page, () => !!document.querySelector('.kgc-big, .kgd-big'), null, 'overlay ' + i);
      await wait(150);
      const o = await page.evaluate(() => {
        const g = document.querySelector('.kgc-big, .kgd-big'), gr = g.getBoundingClientRect();
        const inside = [...g.querySelectorAll('*')].filter((e) => !e.closest('.kgd-scroll')).every((e) => {
          const x = e.getBoundingClientRect(); return !x.width || (x.left >= -1 && x.right <= innerWidth + 1);
        });
        return { kind: g.querySelector('.kgf') ? 'dbt' : g.querySelector('.kgd') ? 'flow' : 'svg',
                 cls: g.className, role: g.getAttribute('role'), label: g.getAttribute('aria-label'),
                 title: g.querySelector('.kgc-big-head p').textContent, focus: document.activeElement.textContent,
                 inWindow: gr.left >= -1 && gr.right <= innerWidth + 1 && gr.top >= -1 && gr.bottom <= innerHeight + 1, inside,
                 overflow: document.documentElement.scrollWidth - innerWidth };
      });
      if (o.kind === 'dbt') {
        // a box in the larger flow still opens its SQL or YAML
        await page.locator('.kgd-big button.kgf-box').first().click();
        o.boxOpens = await page.evaluate(() => !!document.querySelector('.kgd-big .kgf-code:not([hidden]) pre'));
        o.bigText = await page.evaluate(() => parseFloat(getComputedStyle(document.querySelector('.kgd-big .kgf-box')).fontSize));
        o.overflow = Math.max(o.overflow, await page.evaluate(() => document.documentElement.scrollWidth - innerWidth));
      }
      if (how === 'escape') await page.keyboard.press('Escape'); else await page.click('.kgc-big .kgc-back, .kgd-big .kgc-back');
      await wait(100);
      o.how = how;
      Object.assign(o, await page.evaluate(([n, before]) => ({
        closed: !document.querySelector('.kgc-big, .kgd-big') && !document.getElementById('kgcBox').hidden,
        backTo: document.activeElement === document.querySelectorAll('.kgc-log .kgc-zoom')[n],
        inertSame: document.querySelectorAll('[inert]').length === before,
      }), [i, inertBefore]));
      r.opened.push(o);
    }
    out.runs[key] = r;
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
