// n154: the replay back in the home page's hero (n165: turn 1 plays from 0 s, with four dots for where it is), and the chat's button on
// every page without covering the sticky header or /check's drop area; on /check the chat opens on the plan in the page.
// Usage: node tests/n154_browser.js <base url> [chromium path]. Prints one JSON object the Python test asserts on.
const { chromium } = require('playwright');
const base = process.argv[2], exe = process.argv[3];
const PAGES = ['/', '/check', '/start', '/pricing', '/docs/reference/tools', '/blog/fabric-totals-double-after-join', '/lovable', '/it'];
const overlap = (a, b) => !!a && !!b && a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
// n162: wait for n results in the chat by polling page.evaluate: CI's Playwright evaluates a waitForFunction predicate as a
// string, which the pages' policy (no 'unsafe-eval') refuses
async function wins(page, n) {
  for (let i = 0; i < 300; i++) {
    if (await page.evaluate((k) => document.querySelectorAll('.kgc-msg.win').length >= k, n)) return;
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error('timeout: ' + n + ' results in the chat');
}

(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  for (const width of [375, 1280]) {
    const ctx = await browser.newContext({ viewport: { width, height: 800 } });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => out.errors.push(`${width}: ${e.message}`));
    const requests = [];
    page.on('request', (r) => requests.push(new URL(r.url()).pathname));
    // n165: the hero, sampled 0.5 s and 2.5 s after the page's load event: turn 1 plays from 0 s, so its question is typing
    // at 0.5 s and its answer is in by 2.5 s. `at` is the time since load (performance.now() counts from navigation start)
    await page.goto(base + '/', { waitUntil: 'load' });
    const loaded = await page.evaluate(() => performance.getEntriesByType('navigation')[0].loadEventEnd);
    const until = async (ms) => { const now = await page.evaluate(() => performance.now()); if (now < loaded + ms) await page.waitForTimeout(loaded + ms - now); };
    const sample = () => page.evaluate(() => {
      const r = (s) => { const e = document.querySelector(s); return e ? e.getBoundingClientRect().toJSON() : null; };
      const op = (e) => +getComputedStyle(e).opacity;
      const turn = document.querySelector('.session-turn:first-child');
      const sent = turn.querySelector('.session-sent'), text = turn.querySelector('.session-text');
      const clip = getComputedStyle(text).clipPath, right = /inset\(\S+ (\S+)/.exec(clip);
      const shown = [...document.querySelectorAll('.session-turn')].filter((t) => op(t) > 0.5).length;
      // the question is on screen: its turn and its text are opaque, and the typing clip (none on a phone) shows some of it
      const questionShown = op(turn) > 0.5 && op(text) > 0.5 && (!right || parseFloat(right[1]) < 95);
      const dots = [...document.querySelectorAll('.session-dots span')].map((d) => getComputedStyle(d).backgroundColor !== 'rgba(0, 0, 0, 0)');
      return { at: Math.round(performance.now() - performance.getEntriesByType('navigation')[0].loadEventEnd), clip, questionShown, ctas: r('.hero-ctas'), session: r('figure.session'), head: r('.session-head'),
               sent: sent.getBoundingClientRect().toJSON(), sentOpacity: op(sent), answerOpacity: op(turn.querySelector('.session-answer')),
               turnsShown: shown, dots, film: r('#film'), h1: r('h1'),   // n196: the film between the buttons and the replay
               caption: document.querySelector('#session-cap').textContent.trim().slice(0, 40), inHero: !!document.querySelector('.hero figure.session') };
    });
    await until(500);
    out['hero' + width] = await sample();
    await until(2500);
    out['hero' + width].late = await sample();
    await until(7600);                                  // the second turn has taken over: the replay goes on as before (n203: turn 1 stays until turn 2's question is sent at 7.26 s)
    out['later' + width] = await page.evaluate(() => ({
      turns: [...document.querySelectorAll('.session-turn')].map((t) => +(+getComputedStyle(t).opacity).toFixed(2)),
      dots: [...document.querySelectorAll('.session-dots span')].map((d) => getComputedStyle(d).backgroundColor !== 'rgba(0, 0, 0, 0)') }));
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
    // n162: both are steps; on /check they run on the plan in the page, still without a request
    await page.click('.kgc-pick[data-pick="Fix data issues"]');
    await page.waitForSelector('.kgc-pick[data-pick="Draft a dbt project"]', { timeout: 15000 });
    await page.click('.kgc-pick[data-pick="Draft a dbt project"]');
    await wins(page, 3);
    out['checkChat' + width].results = await page.evaluate(() => [...document.querySelectorAll('.kgc-msg.win h3')].map((h) => h.textContent));
    out['checkChat' + width].requests = requests.filter((p) => !p.startsWith('/static/chat-demo.'));
    // a deep page, in a fresh tab state: n162: Fix data issues runs there (no navigation; until n162 a link to the docs)
    await page.evaluate(() => sessionStorage.clear());
    await page.goto(base + '/docs/reference/tools', { waitUntil: 'load' });
    await page.click('#kgcLaunch');
    await page.waitForSelector('#kgcBox:not([hidden]) .kgc-pick[data-pick="Check the tables"]', { timeout: 10000 });
    await page.click('.kgc-pick[data-pick="Check the tables"]');
    await page.waitForSelector('.kgc-pick[data-pick="Yes, add the link"]', { timeout: 15000 });
    await page.click('.kgc-pick[data-pick="Yes, add the link"]');
    await page.waitForSelector('.kgc-pick[data-pick="Fix data issues"]', { timeout: 15000 });
    await page.click('.kgc-pick[data-pick="Fix data issues"]');
    await wins(page, 2);
    out['deepLink' + width] = { path: new URL(page.url()).pathname,
      result: await page.evaluate(() => { const h = document.querySelectorAll('.kgc-msg.win h3'); return h[h.length - 1].textContent; }) };
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
