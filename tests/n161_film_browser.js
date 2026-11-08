// n161: which film the browser picks. At 375 px the first <source> (media="(max-width: 640px)", the 4:5 version), at 1280 px
// the 16:9 one; on the home page and on /docs. preload="none" loads nothing until play, so the test asks the element to run
// its source selection (load()) and reads currentSrc. Usage: node tests/n161_film_browser.js <base url> [chromium path].
const { chromium } = require('playwright');
const base = process.argv[2], exe = process.argv[3];
(async () => {
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const out = { errors: [] };
  for (const width of [375, 1280]) {
    for (const path of ['/', '/docs']) {
      const page = await browser.newPage({ viewport: { width, height: 900 } });
      page.on('pageerror', (e) => out.errors.push(`${width} ${path}: ${e.message}`));
      const external = [];
      page.on('request', (r) => { if (!r.url().startsWith(base)) external.push(r.url()); });
      await page.goto(base + path, { waitUntil: 'networkidle' });
      out[`${width} ${path}`] = await page.evaluate(async () => {
        const v = document.querySelector('#film video'), r = v.getBoundingClientRect();
        v.load(); await new Promise((ok) => setTimeout(ok, 600));
        return { src: new URL(v.currentSrc, location.href).pathname, ratio: +(r.width / r.height).toFixed(2),
                 overflow: document.documentElement.scrollWidth > window.innerWidth };
      });
      out[`${width} ${path}`].external = external.length;
      await page.close();
    }
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
