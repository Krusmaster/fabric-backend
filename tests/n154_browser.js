// n154: the replay back in the home page's hero, starting with its first message already shown, and the chat's button on
// every page without covering the sticky header or /check's drop area; on /check the chat opens on the plan in the page.
// Usage: node tests/n154_browser.js <base url> [chromium path]. Prints one JSON object the Python test asserts on.
const { chromium } = require('playwright');
const base = process.argv[2], exe = process.argv[3];
const PAGES = ['/', '/check', '/start', '/pricing', '/docs/reference/tools', '/blog/fabric-totals-double-after-join', '/lovable', '/it'];
const overlap = (a, b) => !!a && !!b && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  for (const width of [375, 1280]) {
    const ctx = await browser.newContext({ viewport: { width, height: 800 } });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => out.errors.push(`${width}: ${e.message}`));
    const requests = [];
    page.on('request', (r) => requests.push(new URL(r.url()).pathname));
    // the hero, measured at once: no waiting for the replay
    await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
    out['hero' + width] = await page.evaluate(() => {
      const r = (s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().toJSON() : null; };
      const sent = document.querySelector('.session-turn:first-child .session-sent');
      const shown = [...document.querySelectorAll('.session-turn')].filter((t) => getComputedStyle(t).opacity > 0.5).length;
      return { ctas: r('.hero-ctas'), session: r('figure.session'), head: r('.session-head'), sent: sent.getBoundingClientRect().toJSON(),
               sentOpacity: +getComputedStyle(sent).opacity, answerOpacity: +getComputedStyle(document.querySelector('.session-turn:first-child .session-answer')).opacity,
               turnsShown: shown, mini: r('.ba-mini'), usp: r('.usp'), h1: r('h1'),
               caption: document.querySelector('#session-cap').textContent.trim().slice(0, 40), inHero: !!document.querySelector('.hero figure.session') };
    });
    await page.waitForTimeout(6600);                    // the second turn has taken over: the replay goes on as before
    out['later' + width] = await page.evaluate(() => [...document.querySelectorAll('.session-turn')].map((t) => +(+getComputedStyle(t).opacity).toFixed(2)));
    for (const path of PAGES) {
      await page.goto(base + path, { waitUntil: 'load' });
      await page.waitForSelector('#kgcLaunch:not([hidden])', { timeout: 5000 }).catch(() => {});
      const f = await page.evaluate(() => {
        const b = document.getElementById('kgcLaunch');
        const r = (s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().toJSON() : null; };
        return { exists: !!b && !b.hidden, shown: !!b && !b.hidden && b.getBoundingClientRect().width > 0 && getComputedStyle(b).visibility === 'visible',
                 pill: b ? b.getBoundingClientRect().toJSON() : null, header: r('.site-header'), drop: r('#check-drop') };
      });
      {
        await page.evaluate(() => window.scrollTo(0, 600));
        await page.waitForTimeout(100);
        f.scrolled = await page.evaluate(() => ({ pill: document.getElementById('kgcLaunch').getBoundingClientRect().toJSON(),
                                                  header: document.querySelector('.site-header').getBoundingClientRect().toJSON() }));
      }
      f.coversHeader = overlap(f.pill, f.header) || overlap(f.scrolled.pill, f.scrolled.header);
      f.coversDrop = f.shown && overlap(f.pill, f.drop);
      // and at the end of the page it is there (on /check, once the drop area has scrolled past)
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.waitForTimeout(150);
      f.shownAtEnd = await page.evaluate(() => getComputedStyle(document.getElementById('kgcLaunch')).visibility === 'visible');
      out[path + '@' + width] = f;
    }
    // on /check the chat opens on the plan in the page and fetches nothing; its links are absolute
    await page.goto(base + '/check', { waitUntil: 'load' });
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(150);
    requests.length = 0;
    await page.click('#kgcLaunch');
    await page.waitForSelector('#kgcBox:not([hidden]) .kgc-pick[data-pick="Check the tables"]', { timeout: 10000 });
    await page.click('.kgc-pick[data-pick="Check the tables"]');
    await page.waitForSelector('.kgc-pick[data-pick="Yes, add the link"]', { timeout: 15000 });
    await page.click('.kgc-pick[data-pick="Yes, add the link"]');
    await page.waitForSelector('.kgc-pick[data-pick="Fix data issues"]', { timeout: 15000 });
    out['checkChat' + width] = await page.evaluate(() => ({
      links: [...document.querySelectorAll('.kgc-pick[data-pick="Fix data issues"], .kgc-pick[data-pick="Draft a dbt project"]')].map((a) => ({
        label: a.getAttribute('data-pick'), tag: a.tagName, href: a.getAttribute('href'), why: (a.querySelector('small') || {}).textContent || '',
        planned: a.classList.contains('planned') })) }));
    out['checkChat' + width].requests = requests.filter((p) => !p.startsWith('/static/chat-demo.'));
    // a deep page, in a fresh tab state: the link goes where it says
    await page.evaluate(() => sessionStorage.clear());
    await page.goto(base + '/docs/reference/tools', { waitUntil: 'load' });
    await page.click('#kgcLaunch');
    await page.waitForSelector('#kgcBox:not([hidden]) .kgc-pick[data-pick="Check the tables"]', { timeout: 10000 });
    await page.click('.kgc-pick[data-pick="Check the tables"]');
    await page.waitForSelector('.kgc-pick[data-pick="Yes, add the link"]', { timeout: 15000 });
    await page.click('.kgc-pick[data-pick="Yes, add the link"]');
    await page.waitForSelector('.kgc-pick[data-pick="Fix data issues"]', { timeout: 15000 });
    await Promise.all([page.waitForNavigation(), page.click('.kgc-pick[data-pick="Fix data issues"]')]);
    out['deepLink' + width] = { path: new URL(page.url()).pathname, h1: await page.evaluate(() => (document.querySelector('h1') || {}).textContent || '') };
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
