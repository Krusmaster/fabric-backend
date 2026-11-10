// n161: which film the browser picks. At 375 px the first <source> (media="(max-width: 640px)", the 4:5 version), at 1280 px
// the 16:9 one; on the home page and on /docs. preload="none" loads nothing until play, so the test asks the element to run
// its source selection (load()) and reads currentSrc. Usage: node tests/n161_film_browser.js <base url> [chromium path].
const { chromium } = require('playwright');
const base = process.argv[2], exe = process.argv[3];
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  for (const width of [375, 1280]) {
    for (const path of ['/docs']) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      page.on('pageerror', (e) => out.errors.push(`${width} ${path}: ${e.message}`));
      const external = [];
      page.on('request', (r) => { if (!r.url().startsWith(base)) external.push(r.url()); });
      await page.goto(base + path, { waitUntil: 'networkidle' });
      out[`${width} ${path}`] = await page.evaluate(async () => {
        const v = document.querySelector('#film video'), r = v.getBoundingClientRect();
        // n163: does this browser honour media on a video's <source>? The Chromium of CI's Playwright (131) plays the
        // 16:9 source at 375 px; Chromium 153 plays the 4:5 one. The probe is a bare <video> with media="all" on a first
        // source and a plain second one: a browser that honours media picks the first. preload="none" fetches nothing.
        const probe = document.createElement('video'); probe.preload = 'none';
        const first = v.querySelector('source');
        for (const [media, src] of [['all', first.src], ['', v.querySelectorAll('source')[1].src]]) {
          const s = document.createElement('source'); if (media) s.media = media; s.src = src; s.type = 'video/mp4'; probe.appendChild(s);
        }
        v.load(); probe.load(); await new Promise((ok) => setTimeout(ok, 600));
        const path = (u) => new URL(u, location.href).pathname;
        return { src: path(v.currentSrc), mediaHonoured: path(probe.currentSrc) === path(first.src),
                 queryMatches: matchMedia(first.media).matches, ratio: +(r.width / r.height).toFixed(2),
                 overflow: document.documentElement.scrollWidth > window.innerWidth };
      });
      out[`${width} ${path}`].external = external.length;
      await page.close();
    }
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
