// n206: the tidied home page at 375, 768, 1280 and 1440 px, light and dark: no horizontal scroll and no element wider
// than the page, one diagram (no hub), the sources as rendered, no heading left alone at the end of its section, the room
// between sections, and on a phone every button inside the page without overlapping another.
// Usage: node tests/n206_browser.js <base url>
const { chromium } = require('playwright');
const base = process.argv[2];
const SIZES = [[375, 812], [768, 1024], [1280, 720], [1440, 900]];
(async () => {
  const browser = await chromium.launch();
  const out = { errors: [], sizes: {} };
  for (const [width, height] of SIZES) for (const scheme of ['light', 'dark']) {
    const ctx = await browser.newContext({ viewport: { width, height }, colorScheme: scheme, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => out.errors.push(`${width}-${scheme}: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') out.errors.push(`${width}-${scheme}: ${m.text()}`); });
    await page.goto(base + '/', { waitUntil: 'networkidle' });
    out.sizes[`${width}-${scheme}`] = await page.evaluate((scheme) => {
      const W = document.documentElement.clientWidth;
      const main = document.querySelector('[data-page="home"]');
      const visible = (e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e);
        return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !e.closest('details:not([open]) > :not(summary)'); };
      const wide = [...main.querySelectorAll('*')].filter((e) => visible(e) && !e.closest('.table-wrap, .session-links'))
        .filter((e) => { const r = e.getBoundingClientRect(); return r.right > W + 1 || r.left < -1; })
        .map((e) => e.tagName + '.' + e.className).slice(0, 10);
      // the visual room between consecutive sections: the top of one's content minus the bottom of the previous one's
      const sections = [...main.children].filter(visible);
      const content = (s) => { const rs = [...s.children].filter(visible).map((c) => c.getBoundingClientRect());
        return { top: Math.min(...rs.map((r) => r.top)), bottom: Math.max(...rs.map((r) => r.bottom)) }; };
      const gaps = sections.slice(1).map((s, i) => Math.round(content(s).top - content(sections[i]).bottom));
      // a heading with nothing visible after it in its section
      const orphans = [...main.querySelectorAll('h1, h2, h3')].filter(visible).filter((h) => {
        const sec = h.closest('section, .card, li') || main;
        const after = [...sec.querySelectorAll('*')].filter((e) => visible(e) && (h.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING) && !h.contains(e));
        return after.length === 0;
      }).map((h) => h.textContent.trim());
      const btns = [...main.querySelectorAll('.btn')].filter(visible);
      const buttonsClipped = btns.filter((b) => { const r = b.getBoundingClientRect(); return r.left < 0 || r.right > W || b.scrollWidth > b.clientWidth + 1; })
        .map((b) => b.textContent.trim());
      const rects = btns.map((b) => [b.textContent.trim(), b.getBoundingClientRect()]);
      const buttonsOverlap = [];
      for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) {
        const [a, ra] = rects[i], [b, rb] = rects[j];
        if (ra.left < rb.right - 1 && rb.left < ra.right - 1 && ra.top < rb.bottom - 1 && rb.top < ra.bottom - 1) buttonsOverlap.push(a + ' / ' + b);
      }
      const bg = getComputedStyle(document.body).backgroundColor.match(/\d+/g).map(Number);
      const lum = (bg[0] + bg[1] + bg[2]) / 3;
      return { overflow: document.documentElement.scrollWidth - innerWidth, wide, gaps, orphans, buttonsClipped, buttonsOverlap,
               figures: main.querySelectorAll('figure.off-fig').length, hubs: main.querySelectorAll('.hub').length,
               sources: [...main.querySelectorAll('.off-src li')].map((l) => l.innerText.trim()),
               themed: scheme === 'dark' ? lum < 80 : lum > 200 };
    }, scheme);
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
