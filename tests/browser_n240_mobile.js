// n240: /check on a phone, as a paid campaign's visitor sees it. At 375 x 812 and 390 x 844 (touch, mobile): no
// sideways scroll, the one-tap sample button wholly on the first screen and at least 44 px high, the stand-alone tap
// targets at least 44 px, the text box at 16 px; one tap on the sample shows the run's three figures; the events carry
// the campaign; the layout shift stays small. Usage: node browser_n240_mobile.js <base> [chromium]
// Prints JSON {errors, sizes: {"375x812": {...}, ...}}.
const { chromium } = require('playwright');
const [base, exe] = process.argv.slice(2);
const CAMPAIGN = '/check?utm_source=tiktok&utm_medium=paid&utm_campaign=fabric_see_this_test1';

(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const errors = [], sizes = {};
  for (const [w, h] of [[375, 812], [390, 844]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errors.push(`${w}: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`${w}: ${m.text()}`); });
    const events = [];
    page.on('request', (r) => { if (r.url().includes('/check/event')) events.push(r.url().replace(base, '')); });
    await page.addInitScript(() => {
      window.__cls = 0;
      new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: 'layout-shift', buffered: true });
    });
    await page.goto(base + CAMPAIGN, { waitUntil: 'load' });
    const s = await page.evaluate(([w, h]) => {
      const box = (el) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, width: r.width, height: r.height }; };
      const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
      // stand-alone targets: buttons, summaries, and links that are not a phrase inside running text
      const inline = (el) => el.tagName === 'A' && el.parentElement && ['P', 'LI', 'SPAN', 'SMALL'].includes(el.parentElement.tagName)
        && el.parentElement.textContent.trim().length > el.textContent.trim().length + 2 && !el.parentElement.matches('.footer-links,.ctas');
      const small = [...document.querySelectorAll('button,summary,a,input:not([type=file]),textarea,select')]
        .filter((el) => shown(el) && !el.matches('.visually-hidden') && !inline(el))
        .map((el) => ({ what: el.tagName + (el.id ? '#' + el.id : '') + ' ' + (el.textContent || '').trim().slice(0, 30), ...box(el) }))
        .filter((b) => b.height < 44 - 0.5);
      return { scrollWidth: document.documentElement.scrollWidth, width: w, height: h, tryBtn: box(document.getElementById('check-try')),
               tryText: document.getElementById('check-try').textContent.trim(), small,
               textarea: parseFloat(getComputedStyle(document.getElementById('check-columns')).fontSize),
               dropTop: document.getElementById('check-drop').getBoundingClientRect().top };
    }, [w, h]);
    await page.tap('#check-try');
    await page.waitForSelector('#check-headline', { timeout: 180000 });
    await page.waitForTimeout(600);
    s.tiles = await page.$$eval('#check-headline li', (l) => l.map((x) => x.textContent.replace(/\s+/g, ' ').trim()));
    s.headlineTop = await page.evaluate(() => document.getElementById('check-headline').getBoundingClientRect().top);
    s.scrollWidthAfter = await page.evaluate(() => document.documentElement.scrollWidth);
    s.cls = await page.evaluate(() => window.__cls);
    s.events = events;
    sizes[`${w}x${h}`] = s;
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify({ errors, sizes }));
})().catch((e) => { console.error(e); process.exit(1); });
