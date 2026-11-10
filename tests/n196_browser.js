// n196: the film directly under the home page's headline and buttons. At 375, 768, 1280 and 1440 px, light and dark:
// where the headline, the buttons and the film sit in the first viewport, whether it plays, and no horizontal scroll.
// Then reduced motion: the poster stays and nothing plays; the Pause/Play button works by keyboard.
// Usage: node tests/n196_browser.js <base url>
const { chromium } = require('playwright');
const base = process.argv[2];
const SIZES = [[375, 812], [768, 1024], [1280, 720], [1440, 900]];
(async () => {
  const browser = await chromium.launch();
  const out = { errors: [], sizes: {} };
  const measure = () => {
    const q = (s) => document.querySelector(s), box = (s) => q(s).getBoundingClientRect();
    const v = q('#film video'), h1 = box('h1'), ctas = box('.hero-ctas'), f = v.getBoundingClientRect();
    const b = q('.film-toggle');
    const inView = (r) => r.top >= 0 && r.bottom <= innerHeight;
    return { vh: innerHeight, h1InView: inView(h1), ctasInView: inView(ctas), ctasBottom: ctas.bottom, filmTop: f.top, filmHeight: f.height,
             filmWidth: f.width, filmCentre: Math.abs((f.left + f.right) / 2 - innerWidth / 2),
             visibleFraction: Math.max(0, Math.min(innerHeight, f.bottom) - f.top) / f.height,
             filmAfterButtons: f.top >= ctas.bottom, gapAfterButtons: f.top - ctas.bottom,
             paused: v.paused, muted: v.muted, loop: v.loop, playsinline: v.playsInline, preload: v.preload,
             autoplayAttr: v.hasAttribute('autoplay'), button: b && !b.hidden ? b.textContent.trim() : null,
             buttonVisible: !!b && !b.hidden && b.getBoundingClientRect().width > 0,
             overflow: document.documentElement.scrollWidth > innerWidth,
             films: document.querySelectorAll('video').length,
             theme: getComputedStyle(document.body).backgroundColor };
  };
  for (const scheme of ['light', 'dark']) {
    for (const [width, height] of SIZES) {
      const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: scheme });
      const page = await ctx.newPage();
      page.on('pageerror', (e) => out.errors.push(`${scheme} ${width}: ${e.message}`));
      await page.goto(base + '/', { waitUntil: 'load' });
      await page.waitForFunction(() => { const v = document.querySelector('#film video'); return v && !v.paused; }, null, { timeout: 8000 }).catch(() => {});
      out.sizes[`${scheme} ${width}`] = await page.evaluate(measure);
      await ctx.close();
    }
  }
  // reduced motion: the poster, no play; then the button by keyboard plays and pauses
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 }, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => out.errors.push(`reduced: ${e.message}`));
  await page.goto(base + '/', { waitUntil: 'load' });
  await page.waitForTimeout(1500);
  const still = await page.evaluate(() => { const v = document.querySelector('#film video');
    return { paused: v.paused, time: v.currentTime, poster: v.getAttribute('poster'), button: document.querySelector('.film-toggle').textContent.trim() }; });
  await page.focus('.film-toggle');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => !document.querySelector('#film video').paused, null, { timeout: 8000 }).catch(() => {});
  const afterEnter = await page.evaluate(() => ({ paused: document.querySelector('#film video').paused,
    button: document.querySelector('.film-toggle').textContent.trim(), focused: document.activeElement.classList.contains('film-toggle') }));
  await page.keyboard.press('Space');
  await page.waitForTimeout(300);
  const afterSpace = await page.evaluate(() => ({ paused: document.querySelector('#film video').paused,
    button: document.querySelector('.film-toggle').textContent.trim() }));
  const name = await page.evaluate(() => { const b = document.querySelector('.film-toggle'), v = document.querySelector('#film video');
    return { button: b.textContent.trim(), video: v.getAttribute('aria-label'), tag: b.tagName, type: b.type }; });
  out.reduced = { still, afterEnter, afterSpace, name };
  await ctx.close();
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
